from __future__ import annotations
import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
logger = logging.getLogger(__name__)
_CONCERN_PREFIX = re.compile('^(帮我看看|帮我看下|帮我|请问|我想|我要|请|分析|看看|咨询|评估)\\s*')
_CONCERN_SUFFIX = re.compile('(该怎么|怎么办|应该如何|应该怎么|如何|吗|呢|？|\\?|。|，|,)+\\s*$')
_CONCERN_NOISE = re.compile('^(需要|是否需要|是否|能否|要不要|怎么|如何|应该)')
_HEALTH_TOPICS = ('血脂', '胆固醇', '低密度脂蛋白', '高密度脂蛋白', '甘油三酯', '血糖', '糖化血红蛋白', '血压', '尿酸', '脂肪肝', '肝功能', '转氨酶', '肌酐', '体重', 'BMI', '运动', '饮食', '睡眠')

def _parse_health_concerns_from_query(query: str) -> list[dict]:
    q = (query or '').strip()
    if not q:
        return []
    concerns: list[str] = []
    for part in re.split('[,，、;；\\n|/]+', q):
        cleaned = _CONCERN_SUFFIX.sub('', _CONCERN_PREFIX.sub('', part.strip())).strip()
        if 1 < len(cleaned) <= 40 and (not _CONCERN_NOISE.match(cleaned)):
            concerns.append(cleaned)
    if not concerns:
        concerns.extend(re.findall('|'.join(_HEALTH_TOPICS), q))
    if not concerns and len(q) <= 40:
        concerns = [q]
    return [{'name': c, 'concern': c, 'metric_name': c, 'ins': ''} for c in concerns[:20]]
_CONCERN_STATE_KEYS = ('parsed_concerns', 'parsed_metrics')

def _concern_state(concerns: list[dict]) -> dict[str, list[dict]]:
    return {key: concerns for key in _CONCERN_STATE_KEYS}

def _run_vision(images: list[dict]) -> tuple[list[dict], list[dict]]:
    from app.agents.vision_agent import build_vision_agent
    agent = build_vision_agent().compile()
    result = agent.invoke({'trace_id': f'a2a_{uuid4().hex[:8]}', 'task_id': '', 'images': images, 'image_observations': [], **_concern_state([]), 'errors': []})
    observations = result.get('image_observations') or []
    for key in _CONCERN_STATE_KEYS:
        parsed = result.get(key)
        if parsed:
            return (observations, parsed)
    return (observations, [])

def _run_retrieval(concerns: list[dict], image_urls: list[str] | None=None) -> list[dict]:
    from app.agents.retrieval_agent import build_retrieval_agent
    agent = build_retrieval_agent().compile()
    result = agent.invoke({'trace_id': f'a2a_{uuid4().hex[:8]}', 'task_id': '', 'query_plan': {}, 'retrieval_results': [], 'evidence': [], **_concern_state(concerns), 'image_urls': image_urls or [], 'errors': []})
    return result.get('evidence') or []

def _run_report(concerns: list[dict], evidence: list[dict], observations: list[dict], user_id: str='') -> dict:
    from app.agents.report_agent import build_report_agent
    agent = build_report_agent().compile()
    result = agent.invoke({'trace_id': f'a2a_{uuid4().hex[:8]}', 'task_id': '', 'user_id': user_id, 'evidence': evidence, **_concern_state(concerns), 'image_observations': observations, 'user_profile': {}, 'report_draft': {}, 'validated_claims': [], 'errors': []})
    return {'report_draft': result.get('report_draft') or {}, 'validated_claims': result.get('validated_claims') or []}

def run_health_consult(*, images: list[dict] | None=None, query: str='', user_id: str='a2a-user') -> dict[str, Any]:
    started = datetime.now(timezone.utc).isoformat()
    logger.info('[A2A] run_health_consult user=%s images=%d query=%r', user_id, len(images or []), query[:80])
    observations: list[dict] = []
    concerns: list[dict] = []
    if images:
        try:
            observations, concerns = _run_vision(images)
        except Exception as e:
            logger.error('[A2A] vision failed: %s', e, exc_info=True)
            return {'status': 'failed', 'error': f'视觉识别失败: {e}', 'started_at': started}
    if not concerns:
        concerns = _parse_health_concerns_from_query(query)
    if not concerns:
        return {'status': 'refused', 'refuse_reason': '未提供可识别的体检报告或健康诉求，拒绝咨询', 'report_version': '', 'sections': {}, 'evidence': [], 'claims': [], 'started_at': started}
    image_urls = [img.get('presigned_url', '') for img in images or [] if img.get('presigned_url')]
    try:
        evidence = _run_retrieval(concerns, image_urls=image_urls)
    except Exception as e:
        logger.error('[A2A] retrieval failed: %s', e, exc_info=True)
        return {'status': 'failed', 'error': f'检索失败: {e}', 'started_at': started}
    from app.evidence.validator import refuse_if_no_evidence as _refuse_shared
    claims_preview = []
    for item in concerns:
        name = item.get('name', '')
        related = [e for e in evidence if name in (e.get('quote') or '')]
        claims_preview.append({'claim_id': str(uuid4()), 'claim': name, 'type': 'fact' if related else 'unknown', 'text': f'健康诉求「{name}」', 'evidence_ids': [e['evidence_id'] for e in related if e.get('evidence_id')]})
    refuse, reason = _refuse_shared(claims_preview, evidence)
    if refuse:
        return {'status': 'refused', 'refuse_reason': reason, 'report_version': '', 'sections': {'observation': 'A2A 委托咨询未能形成可核验结论。', 'unknowns': reason}, 'evidence': evidence, 'claims': claims_preview, 'concerns': [i.get('name') for i in concerns], 'started_at': started}
    try:
        report_out = _run_report(concerns, evidence, observations, user_id=user_id)
    except Exception as e:
        logger.error('[A2A] report failed: %s', e, exc_info=True)
        return {'status': 'failed', 'error': f'报告生成失败: {e}', 'evidence': evidence, 'started_at': started}
    draft = report_out['report_draft']
    sections = draft.get('sections') if isinstance(draft, dict) else {}
    rv = f"rv_a2a_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:6]}"
    return {'status': 'completed', 'report_version': rv, 'sections': sections or {}, 'evidence': evidence, 'claims': report_out.get('validated_claims') or claims_preview, 'concerns': [i.get('name') for i in concerns], 'started_at': started, 'finished_at': datetime.now(timezone.utc).isoformat()}
