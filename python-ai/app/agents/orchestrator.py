import logging
import re
from typing import TypedDict
from uuid import UUID, uuid4
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from app.agents.vision_agent import build_vision_agent
from app.agents.retrieval_agent import build_retrieval_agent
from app.agents.report_agent import build_report_agent, run_deterministic_checks
from app.agents.memory_agent import build_memory_agent
logger = logging.getLogger(__name__)
_ABNORMAL_FLAGS = ('low', 'high', 'critical')
_LAB_POSITIONS = ('lab_sheet', 'exam_report')

class ResearchState(TypedDict, total=False):
    trace_id: str
    task_id: str
    tenant_id: str
    user_id: str
    images: list[dict]
    report_date: str
    institution: str
    image_observations: list[dict]
    parsed_metrics: list[dict]
    abnormal_metrics: list[dict]
    vision_confidence: float
    user_profile: dict
    memory_writes_pending: list[dict]
    query_plan: dict
    retrieval_results: list
    evidence: list[dict]
    concentration_result: dict
    metric_trends: list[dict]
    trend_summary: str
    validated_claims: list[dict]
    report_draft: dict
    report_version: str
    missing_information: list[str]
    retry_count: int
    citation_retry_count: int
    refuse_reason: str
    hital_action: str
    quality_failed: bool
    rerun_mode: str
    pending_new_images: list[dict]
    errors: list[dict]
    status: str
    trace_events: list[dict]

def _quality_check(state: ResearchState) -> ResearchState:
    from app.agents.image_quality import actions_from_issues, assess_images, guidance_from_issues
    pending = state.get('pending_new_images') or []
    partial = state.get('rerun_mode') == 'partial' and bool(pending)
    images = pending if partial else state.get('images', [])
    logger.info('[Orch] quality_check images=%d mode=%s', len(images), state.get('rerun_mode') or 'full')
    state.setdefault('retry_count', 0)
    state.setdefault('errors', [])
    issues = assess_images(images, coverage_images=state.get('images', []) if partial else None)
    if issues:
        actions = actions_from_issues(issues)
        state['missing_information'] = actions
        state['quality_failed'] = True
        state['status'] = 'awaiting_images'
        state['errors'] = state.get('errors', []) + [{'error_code': 'IMAGE_QUALITY_LOW', 'message': guidance_from_issues(issues), 'retryable': True}]
        logger.warning('[Orch] 质量门禁未通过: %s', actions)
    else:
        state['quality_failed'] = False
        state['status'] = 'intake'
        logger.info('[Orch] 质量门禁通过')
    return state

def _quality_gate(state: ResearchState) -> str:
    if state.get('quality_failed'):
        return 'fail'
    return 'pass'

def _persist_health_report(state: ResearchState) -> None:
    metrics = state.get('parsed_metrics') or []
    if not metrics:
        return
    user_id = str(state.get('user_id') or 'dev-user')
    report_date = str(state.get('report_date') or '')
    institution = str(state.get('institution') or '')
    try:
        from app.factory.health_parser import build_report, save_report_and_metrics
        from app.factory.models import HealthMetric
        from app.factory.repository import delete_report, list_reports_by_user
        metric_objs: list[HealthMetric] = []
        for m in metrics:
            if isinstance(m, HealthMetric):
                metric_objs.append(m)
            elif isinstance(m, dict):
                allowed = {k: v for k, v in m.items() if k in HealthMetric.model_fields}
                allowed.setdefault('report_id', UUID(int=0))
                allowed.setdefault('user_id', user_id)
                metric_objs.append(HealthMetric(**allowed))
        if not metric_objs:
            return
        for old in list_reports_by_user(user_id):
            if str(old.report_date or '') == report_date:
                delete_report(str(old.id))
                logger.info('[Orch] 覆盖既有体检报告 report_id=%s date=%s', old.id, report_date)
        report, normalized = build_report(metric_objs, user_id=user_id, report_date=report_date, institution=institution)
        report_id, inserted = save_report_and_metrics(report, normalized)
        logger.info('[Orch] 体检报告落库 report_id=%s 指标=%d（新增 %d）', report_id, len(normalized), inserted)
    except Exception as e:
        logger.warning('[Orch] 体检报告落库失败（不阻断主链路）: %s', e)

def _vision_observe(state: ResearchState) -> ResearchState:
    logger.info('[Orch] vision_observe mode=%s', state.get('rerun_mode') or 'full')
    agent = build_vision_agent().compile()
    pending = state.get('pending_new_images') or []
    partial = state.get('rerun_mode') == 'partial' and bool(pending)
    target_images = pending if partial else state.get('images', [])
    sub_state = {'trace_id': state.get('trace_id', ''), 'task_id': state.get('task_id', ''), 'images': target_images, 'image_observations': [], 'parsed_metrics': [], 'abnormal_metrics': [], 'vision_confidence': 0.0, 'errors': []}
    result = agent.invoke(sub_state)
    new_obs = result.get('image_observations', [])
    new_metrics = result.get('parsed_metrics', []) or []
    if partial:
        merged_obs = list(state.get('image_observations') or []) + list(new_obs)
        state['image_observations'] = merged_obs
        merged_metrics = list(state.get('parsed_metrics') or [])
        seen = {(str(m.get('metric_name') or ''), str(m.get('value_text') or '')) for m in merged_metrics}
        for metric in new_metrics:
            key = (str(metric.get('metric_name') or ''), str(metric.get('value_text') or ''))
            if key[0] and key not in seen:
                merged_metrics.append(metric)
                seen.add(key)
        state['parsed_metrics'] = merged_metrics
        state['pending_new_images'] = []
        logger.info('[Orch] 局部 vision: +%d obs, +%d metrics → 合计指标=%d', len(new_obs), len(new_metrics), len(merged_metrics))
    else:
        state['image_observations'] = new_obs
        state['parsed_metrics'] = new_metrics
    state['abnormal_metrics'] = [m for m in state.get('parsed_metrics', []) if m.get('flag') in _ABNORMAL_FLAGS]
    _persist_health_report(state)
    confidence = result.get('vision_confidence')
    if not isinstance(confidence, (int, float)):
        confidence = state.get('vision_confidence', 0.0)
    elif partial and confidence <= 0:
        confidence = state.get('vision_confidence', 0.0)
    state['vision_confidence'] = float(confidence or 0.0)
    state['status'] = 'observing'
    vlm_actions: list[str] = []
    for obs in new_obs if partial else state['image_observations']:
        if obs.get('type') != 'vlm_analysis':
            continue
        pos = obs.get('region') or 'lab_sheet'
        from app.agents.image_quality import position_label
        label = position_label(pos)
        qissues = obs.get('quality_issues') or []
        for qi in qissues:
            qi_s = str(qi).strip()
            if not qi_s:
                continue
            vlm_actions.append(f'「{label}」存在问题：{qi_s}，请按提示调整后重拍')
        if not obs.get('metrics'):
            vlm_actions.append(f'「{label}」中未识别出体检指标，请补拍清晰的指标表格特写')
    if vlm_actions and (not state.get('parsed_metrics')):
        uniq: list[str] = []
        for a in vlm_actions:
            if a not in uniq:
                uniq.append(a)
        state['missing_information'] = uniq[:3]
        state['quality_failed'] = True
        state['status'] = 'awaiting_images'
        logger.warning('[Orch] VLM 质量/可见性问题，触发补拍: %s', uniq[:3])
    elif state.get('images') and (not state.get('parsed_metrics')):
        from app.agents.image_quality import position_label
        positions = {img.get('position') or 'lab_sheet' for img in state.get('images', [])}
        actions = [f'「{position_label(p)}」未能识别体检指标，请更清晰、完整地重拍该图位' for p in positions]
        state['missing_information'] = actions[:3] or ['未能从图片识别体检指标，请补拍清晰的化验单指标表特写']
        state['quality_failed'] = True
        state['status'] = 'awaiting_images'
        logger.warning('[Orch] 有图无指标，触发补拍')
    return state

def _after_vision_gate(state: ResearchState) -> str:
    if state.get('quality_failed'):
        return 'fail'
    confidence = state.get('vision_confidence')
    if isinstance(confidence, (int, float)) and state.get('parsed_metrics'):
        from app.agents.vision_agent import _LOW_CONFIDENCE_THRESHOLD
        if confidence < _LOW_CONFIDENCE_THRESHOLD:
            retry = state.get('retry_count', 0) + 1
            state['retry_count'] = retry
            message = f'体检报告识别置信度偏低（{confidence:.2f}），请补拍更清晰的报告照片：正对报告、光线充足、无遮挡，指标表格文字清晰可读'
            if retry < 3:
                state['missing_information'] = [message]
                state['quality_failed'] = True
                state['status'] = 'awaiting_images'
                state['errors'] = state.get('errors', []) + [{'error_code': 'IMAGE_QUALITY_LOW', 'message': message, 'retryable': True}]
                logger.warning('[Orch] 识别置信度偏低 %.2f，触发补拍 (第 %d/3 次)', confidence, retry)
                return 'fail'
            logger.warning('[Orch] 置信度补拍已达上限，放行并在报告中显式标注不确定性')
            state['errors'] = state.get('errors', []) + [{'error_code': 'VISION_LOW_CONFIDENCE_ACCEPTED', 'message': message, 'retryable': False}]
    return 'pass'

def _memory_read(state: ResearchState) -> ResearchState:
    if state.get('rerun_mode') == 'partial' and state.get('user_profile'):
        logger.info('[Orch] memory_read 跳过（局部重跑复用档案）')
        return state
    logger.info('[Orch] memory_read')
    agent = build_memory_agent().compile()
    sub_state = {'trace_id': state.get('trace_id', ''), 'task_id': state.get('task_id', ''), 'user_id': state.get('user_id', 'dev-user'), 'user_profile': {}, 'parsed_metrics': state.get('parsed_metrics', []), 'abnormal_metrics': state.get('abnormal_metrics', []), 'image_observations': state.get('image_observations', []), 'memory_writes_pending': [], 'errors': []}
    result = agent.invoke(sub_state, config={'recursion_limit': 5})
    state['user_profile'] = result.get('user_profile', {})
    return state

def _retrieval(state: ResearchState) -> ResearchState:
    logger.info('[Orch] retrieval metrics=%d', len(state.get('parsed_metrics', [])))
    agent = build_retrieval_agent().compile()
    image_urls = [img.get('presigned_url', '') for img in state.get('images', []) if img.get('presigned_url')]
    sub_state = {'trace_id': state.get('trace_id', ''), 'task_id': state.get('task_id', ''), 'query_plan': {}, 'retrieval_results': [], 'evidence': [], 'abnormal_metrics': state.get('abnormal_metrics', []), 'parsed_metrics': state.get('parsed_metrics', []), 'image_urls': image_urls, 'errors': []}
    result = agent.invoke(sub_state)
    state['retrieval_results'] = result.get('retrieval_results', [])
    state['evidence'] = result.get('evidence', [])
    state['status'] = 'retrieving'
    codes = [str(m.get('metric_code')).strip() for m in state.get('abnormal_metrics') or state.get('parsed_metrics') or [] if m.get('metric_code')]
    try:
        from app.health.trends import TREND_SOURCE_NOTE, build_trends
        trends = build_trends(state.get('user_id', 'dev-user'), codes or None)
        state['metric_trends'] = trends
        if trends:
            state['trend_summary'] = '\n'.join(['以下为该用户体检指标的时序趋势（含首次/最近一次数值与变化方向）:'] + [f"- {t.get('summary', '')}" for t in trends] + [TREND_SOURCE_NOTE])
        else:
            state['trend_summary'] = '暂无该用户的历史体检指标记录，无法给出趋势分析。'
        logger.info('[Orch] 指标趋势 %d 项', len(trends))
    except Exception as e:
        logger.warning('[Orch] 指标趋势组装失败（降级为空）: %s', e)
        state['metric_trends'] = []
        state['trend_summary'] = ''
    return state

def _evidence_gate(state: ResearchState) -> str:
    evidence = state.get('evidence', [])
    if not evidence:
        retry = state.get('retry_count', 0)
        if retry >= 3:
            reason = '多次补充体检报告材料后仍无可用证据，拒绝生成报告。请更换更清晰的体检报告照片（化验单指标表特写）后重新发起。'
            state['refuse_reason'] = reason
            state['errors'] = state.get('errors', []) + [{'error_code': 'NO_EVIDENCE', 'message': reason, 'retryable': False}]
            logger.warning('[Orch] 补材料已达上限 %d，严格拒答', retry)
            return 'refuse'
        state['retry_count'] = retry + 1
        logger.warning('[Orch] 证据不足，触发补材料 (第 %d/3 次)', state['retry_count'])
        positions = {img.get('position') or '' for img in state.get('images', [])}
        missing: list[str] = []
        if not set(_LAB_POSITIONS) & positions:
            missing.append('请补拍「化验单指标表特写」，保证项目/结果/单位/参考区间整表文字清晰入镜')
        else:
            missing.append('「化验单指标表特写」未能识别出可检索指标，请更近距离重拍并避免反光')
        if 'exam_report' not in positions:
            missing.append('建议补拍「体检报告首页/结论页」，便于核对体检日期、机构与体检结论')
        if not {'other', 'conclusion'} & positions:
            missing.append('如报告有检查结论 / 医生建议页，建议一并补拍（图位选「其他资料」）')
        seen: set[str] = set()
        uniq: list[str] = []
        for m in missing:
            if m not in seen:
                seen.add(m)
                uniq.append(m)
        state['missing_information'] = uniq[:3]
        state['quality_failed'] = False
        return 'insufficient'
    return 'sufficient'

def _report_draft(state: ResearchState) -> ResearchState:
    logger.info('[Orch] report_draft evidence=%d metrics=%d', len(state.get('evidence', [])), len(state.get('parsed_metrics', [])))
    agent = build_report_agent().compile()
    sub_state = {'trace_id': state.get('trace_id', ''), 'task_id': state.get('task_id', ''), 'user_id': state.get('user_id', 'dev-user'), 'report_id': '', 'evidence': state.get('evidence', []), 'parsed_metrics': state.get('parsed_metrics', []), 'abnormal_metrics': state.get('abnormal_metrics', []), 'metric_trends': state.get('metric_trends', []), 'trend_summary': state.get('trend_summary', ''), 'image_observations': state.get('image_observations', []), 'user_profile': state.get('user_profile', {}), 'report_draft': {}, 'validated_claims': [], 'errors': []}
    result = agent.invoke(sub_state)
    state['validated_claims'] = result.get('validated_claims', [])
    state['report_draft'] = result.get('report_draft', {})
    sub_errors = [e for e in result.get('errors') or [] if isinstance(e, dict) and e.get('error_code') in ('CITATION_MISMATCH', 'NO_EVIDENCE')]
    if sub_errors:
        state['errors'] = state.get('errors', []) + sub_errors
        if not state.get('refuse_reason'):
            state['refuse_reason'] = sub_errors[0].get('message', '引用校验失败')
    state['status'] = 'drafting'
    return state

def _citation_validate(state: ResearchState) -> ResearchState:
    logger.info('[Orch] citation_validate claims=%d', len(state.get('validated_claims', [])))
    from app.evidence.validator import refuse_if_no_evidence
    state['errors'] = [e for e in state.get('errors', []) if e.get('error_code') not in ('CITATION_MISMATCH', 'NO_EVIDENCE')]
    claims = state.get('validated_claims', [])
    evidence = state.get('evidence', [])
    draft = state.get('report_draft') or {}
    logger.info('[Citation] 校验开始 claims=%d evidence=%d advice=%d', len(claims), len(evidence), len(draft.get('advice_claims') or []))
    logger.info('[Citation] 门禁暂关：跳过确定性校验，直接放行 claims=%d', len(claims))
    citation_errors = [e for e in state.get('errors', []) if e.get('error_code') in ('CITATION_MISMATCH', 'NO_EVIDENCE')]
    if citation_errors:
        state['citation_retry_count'] = state.get('citation_retry_count', 0) + 1
    else:
        state['citation_retry_count'] = 0
    state['status'] = 'validating'
    return state

def _citation_gate(state: ResearchState) -> str:
    errors = state.get('errors', [])
    citation_errors = [e for e in errors if e.get('error_code') in ('CITATION_MISMATCH', 'NO_EVIDENCE')]
    if citation_errors:
        n = state.get('citation_retry_count', 0)
        if n < 3:
            logger.warning('[Orch] 引用校验失败，回炉重试 %d/3', n)
            return 'fail'
        if not state.get('refuse_reason'):
            state['refuse_reason'] = citation_errors[0].get('message', '引用校验失败')
        logger.warning('[Orch] 引用校验失败已达上限 %d，严格拒答', n)
        return 'refuse'
    return 'pass'

def _refuse_report(state: ResearchState) -> ResearchState:
    reason = state.get('refuse_reason') or '证据不足或引用无法核验'
    logger.warning('[Orch] refuse_report: %s', reason)
    draft = state.get('report_draft') or {}
    draft_sections = draft.get('sections') or {}
    kept, degraded = ({}, [])
    try:
        from app.agents.report_agent import degrade_failed_sections
        kept, degraded = degrade_failed_sections(draft_sections, state.get('errors') or [])
    except Exception as e:
        logger.warning('[Orch] 章节级降级失败，回退整篇拒答: %s', e)
    if degraded:
        from datetime import datetime
        state['report_version'] = f"rv_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{state.get('task_id', 'unknown')[:8]}"
        sections = {k: '' if isinstance(v, list) else v for k, v in kept.items()}
        note = '以下部分因证据不足或存在方向相反的结论，未能给出可核验内容：' + '、'.join(degraded)
        if sections.get('unknowns'):
            sections['unknowns'] = f"{sections.get('unknowns')}\n{note}"
        else:
            sections['unknowns'] = note
        state['status'] = 'published'
        state['report_draft'] = {'version': state['report_version'], 'sections': sections, 'claims': draft.get('claims') or [], 'advice_claims': [], 'evidence': state.get('evidence') or [], 'partial': True, 'degraded_sections': degraded}
        state['validated_claims'] = draft.get('claims') or []
        state['memory_writes_pending'] = []
        state['errors'] = [e for e in state.get('errors', []) if e.get('error_code') != 'CITATION_MISMATCH']
        logger.info('[Orch] 降级发布：保留可信章节，降级 %s', degraded)
        return state
    sections = {'observation': '本次体检分析未能形成可核验结论。', 'facts': '', 'inferences': '', 'conflicts': '', 'unknowns': reason, 'related_to_you': '', 'metric_reading': '', 'metric_trend': '', 'exercise_advice': '', 'lifestyle_advice': '', 'followup_advice': ''}
    state['status'] = 'refused'
    state['report_draft'] = {'version': 'refused', 'sections': sections, 'claims': [], 'advice_claims': [], 'evidence': state.get('evidence') or [], 'partial': False, 'degraded_sections': []}
    state['validated_claims'] = []
    state['memory_writes_pending'] = []
    state['report_version'] = ''
    state['errors'] = state.get('errors', []) + [{'error_code': 'NO_EVIDENCE', 'message': reason, 'retryable': False}]
    return state

def _ask_missing_info(state: ResearchState) -> ResearchState:
    logger.info('[Orch] ask_missing_info — HITL interrupt')
    missing = state.get('missing_information', ['请补充体检报告材料'])
    from app.agents.image_quality import guidance_from_issues
    guidance = '请根据下列具体动作补充体检报告材料（最多三项），补充后将只继续分析流程'
    for err in state.get('errors') or []:
        if isinstance(err, dict) and err.get('error_code') == 'IMAGE_QUALITY_LOW' and err.get('message'):
            guidance = err['message']
            break
    if state.get('quality_failed'):
        guidance = guidance_from_issues([{'position': 'lab_sheet', 'action': a} for a in missing]) if missing else guidance
    user_response = interrupt({'hital_action': 'awaiting_images', 'missing_items': missing[:3], 'guidance': guidance})
    logger.info('[Orch] 补材料后恢复, user_response=%s', {k: v for k, v in (user_response or {}).items() if k != 'images'})
    if isinstance(user_response, dict):
        new_images = user_response.get('new_images', [])
        if new_images:
            existing = state.get('images', [])
            state['images'] = existing + new_images
            state['pending_new_images'] = list(new_images)
            logger.info('[Orch] 新增 %d 张图片, 总计 %d', len(new_images), len(state['images']))
    had_progress = bool(state.get('parsed_metrics') or state.get('image_observations') or state.get('user_profile'))
    partial = bool(state.get('pending_new_images')) and had_progress
    state['rerun_mode'] = 'partial' if partial else 'full'
    logger.info('[Orch] 补材料恢复 rerun_mode=%s', state['rerun_mode'])
    state['retry_count'] = state.get('retry_count', 0)
    state['quality_failed'] = False
    state['status'] = 'intake'
    state['evidence'] = []
    state['report_draft'] = {}
    state['validated_claims'] = []
    state['missing_information'] = []
    state['errors'] = []
    state['retrieval_results'] = []
    state['query_plan'] = {}
    state['metric_trends'] = []
    state['trend_summary'] = ''
    if state['rerun_mode'] == 'full':
        state['parsed_metrics'] = []
        state['abnormal_metrics'] = []
        state['image_observations'] = []
        if not had_progress:
            state['user_profile'] = {}
        state['pending_new_images'] = []
    return state

def _memory_write(state: ResearchState) -> ResearchState:
    logger.info('[Orch] memory_write — 自动入库（无 HITL 中断）')
    proposals = _generate_memory_proposals(state)
    if not proposals:
        logger.info('[Orch] 无候选记忆')
        state['memory_writes_pending'] = []
        return state
    saved: list[dict] = []
    try:
        from app.memory.curator import MemoryCurator, ProfileEntry
        curator = MemoryCurator()
        uid = state.get('user_id', 'dev-user')
        for p in proposals:
            try:
                entry = ProfileEntry(kind=p.get('kind', 'condition'), content=p.get('content', ''), metric_codes=list(p.get('metric_codes') or []), source=p.get('source', 'inferred'), confidence=float(p.get('confidence', 0.5)))
                if curator.commit(uid, entry, confirmed=True):
                    saved.append(p)
            except ValueError as ve:
                logger.warning('[Orch] 候选记忆被门禁拒绝: %s', ve)
            except Exception as ie:
                logger.error('[Orch] 候选记忆入库失败: %s', ie)
    except Exception as e:
        logger.error('[Orch] 记忆自动入库失败: %s', e)
    state['memory_writes_pending'] = saved
    logger.info('[Orch] 自动入库 %d/%d 条候选记忆', len(saved), len(proposals))
    return state

def _publish_gate(state: ResearchState) -> ResearchState:
    logger.info('[Orch] publish_gate — 直接发布')
    from datetime import datetime
    state['report_version'] = f"rv_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{state.get('task_id', 'unknown')[:8]}"
    state['status'] = 'published'
    logger.info('[Orch] 直接发布, version=%s', state['report_version'])
    _persist_episodic(state)
    return state

def _persist_episodic(state: ResearchState) -> None:
    try:
        from app.memory.curator import MemoryCurator
        draft = state.get('report_draft') or {}
        sections = draft.get('sections') if isinstance(draft, dict) else {}
        if not isinstance(sections, dict):
            sections = {}
        report_date, institution = ('', state.get('institution') or '')
        for obs in state.get('image_observations') or []:
            if obs.get('type') == 'vlm_analysis':
                report_date = str(obs.get('report_date') or report_date)
                institution = str(obs.get('institution') or institution)
                break
        metric_codes = [str(m.get('metric_code')).strip() for m in state.get('parsed_metrics') or [] if m.get('metric_code')]
        related = (state.get('user_profile') or {}).get('related') or []
        related_hits = [f"{r.get('metric')}({r.get('reason')})" for r in related if isinstance(r, dict)]
        summary_bits = [str(sections.get('observation', ''))[:120], str(sections.get('metric_reading', ''))[:120]]
        summary = ' '.join((b for b in summary_bits if b)).strip() or f'体检指标 {len(metric_codes)} 项分析'
        MemoryCurator().save_episode(user_id=state.get('user_id', 'dev-user'), task_id=state.get('task_id', ''), product_name=institution if institution != 'unknown' else report_date, product_type='体检报告', metric_codes=metric_codes[:40], summary=summary[:500], unknowns=str(sections.get('unknowns') or '')[:300], report_version=state.get('report_version') or '', related_hits=related_hits[:20])
    except Exception as e:
        logger.error('[Orch] 情景记忆写入失败: %s', e, exc_info=True)

def _norm(s: str) -> str:
    return ''.join((ch for ch in str(s).lower() if ch.isalnum() or '一' <= ch <= '鿿'))

def _existing_profile_keys(user_profile: dict) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    mapping = (('basic', user_profile.get('basic') or []), ('condition', user_profile.get('conditions') or []), ('medication', user_profile.get('medications') or []), ('allergy', user_profile.get('allergies') or []), ('goal', user_profile.get('goals') or []), ('exercise', user_profile.get('exercises') or []))
    for kind, items in mapping:
        for item in items:
            if item:
                keys.add((kind, _norm(item)))
    return keys

def _generate_memory_proposals(state: ResearchState) -> list[dict]:
    proposals: list[dict] = []
    metrics = state.get('parsed_metrics') or []
    abnormal = state.get('abnormal_metrics') or []
    user_profile = state.get('user_profile') or {}
    observations = state.get('image_observations') or []
    logger.info('[Memory] 生成记忆候选 metrics=%d abnormal=%d', len(metrics), len(abnormal))
    existing = _existing_profile_keys(user_profile)
    seen: set[tuple[str, str]] = set(existing)

    def _add(kind: str, content: str, detail: str, confidence: float, source: str, metric_codes: list[str] | None=None) -> None:
        key = (kind, _norm(content))
        if not content or key in seen:
            return
        seen.add(key)
        proposals.append({'candidate_id': f'mem_{uuid4().hex[:8]}', 'kind': kind, 'label': content, 'content': content, 'detail': detail, 'metric_codes': [c for c in metric_codes or [] if c], 'confidence': confidence, 'source': source})
    for metric in abnormal[:3]:
        name = str(metric.get('metric_name') or '').strip()
        code = str(metric.get('metric_code') or '').strip()
        if not name:
            continue
        content = f"{metric.get('category') or name}指标需持续关注（{name}）"
        _add('condition', content, f'体检提示「{name}」异常，是否记录为需持续关注的健康状况？', 0.6, 'metric_abnormal', [code])
    text = ' '.join((str(obs.get('text') or '') for obs in observations if obs.get('type') == 'ocr'))
    for m in re.finditer('(?:长期服用|正在服用|口服|服用)([一-鿿A-Za-z0-9]{2,12})', text):
        med = m.group(1).strip()
        _add('medication', f'长期服用{med}', f'报告中提到正在服用「{med}」，是否记录为长期用药？', 0.6, 'report_statement')
    allergens: list[str] = []
    for m in re.finditer('过敏史[:：]?\\s*([^；;。\\n]{2,30})', text):
        for part in re.split('[、,，/\\s]+', m.group(1).replace('过敏', '')):
            if part.strip():
                allergens.append(part.strip())
    for m in re.finditer('([一-鿿]{2,8})过敏', text):
        token = m.group(1).lstrip('对')
        if token and '史' not in token:
            allergens.append(token)
    for allergen in allergens[:3]:
        _add('allergy', f'{allergen}过敏', f'报告中提到「{allergen}」过敏，是否记录为过敏史？', 0.6, 'report_statement')
    for m in re.finditer('(减重|减脂|降脂|控糖|控制血糖|降血压|增肌|改善睡眠|戒烟限酒)', text):
        _add('goal', f'健康目标: {m.group(1)}', f'报告中提到目标「{m.group(1)}」，是否记录为健康目标？', 0.5, 'report_statement')
    for m in re.finditer('((?:每周|每天)[^，。；\\s]{0,10}(?:跑步|快走|游泳|健身|瑜伽|骑行|球类|散步|久坐))', text):
        _add('exercise', f'运动基础: {m.group(1)}', f'报告中提到运动习惯「{m.group(1)}」，是否记录为运动基础？', 0.5, 'report_statement')
    for metric in abnormal[:3]:
        category = str(metric.get('category') or '').strip()
        if not category:
            continue
        _add('goal', f'持续关注{category}指标', f'本次体检{category}类指标异常，是否加入您的持续关注目标？', 0.5, 'abnormal_followup', [str(metric.get('metric_code') or '')])
    result = proposals[:5]
    logger.info('[Memory] 候选生成完成 %d 条（截断前 %d 条）', len(result), len(proposals))
    return result

def _persist_trace(trace_id: str, task_id: str, node: str, status: str, errors: int, evidence: int, ts: str) -> None:
    try:
        import os
        import psycopg2
        db = os.getenv('DATABASE_URL', 'postgresql://lha:lha_dev@localhost:5432/lha')
        conn = psycopg2.connect(db)
        cur = conn.cursor()
        cur.execute("CREATE TABLE IF NOT EXISTS task_trace (\n                 id        BIGSERIAL PRIMARY KEY,\n                 task_id   TEXT NOT NULL,\n                 trace_id  TEXT NOT NULL DEFAULT '',\n                 node      TEXT NOT NULL,\n                 ts        TIMESTAMPTZ NOT NULL DEFAULT now(),\n                 status    TEXT NOT NULL DEFAULT '',\n                 errors    INT NOT NULL DEFAULT 0,\n                 evidence  INT NOT NULL DEFAULT 0\n               )")
        cur.execute('INSERT INTO task_trace (task_id, trace_id, node, ts, status, errors, evidence)\n               VALUES (%s, %s, %s, %s::timestamptz, %s, %s, %s)', (task_id, trace_id, node, ts, status, errors, evidence))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning('[Trace] 落库失败 node=%s: %s', node, e)

def build_orchestrator(checkpointer=None) -> StateGraph:
    graph = StateGraph(ResearchState)
    from datetime import datetime
    from functools import wraps
    from app.observability.runtime import timed

    def track(fn, name: str):

        @wraps(fn)
        def wrapper(state):
            state = fn(state)
            try:
                events = state.setdefault('trace_events', [])
                trace = {'node': name, 'ts': datetime.utcnow().isoformat(timespec='seconds'), 'status': state.get('status', ''), 'errors': len(state.get('errors', [])), 'evidence': len(state.get('evidence', [])), 'trace_id': state.get('trace_id', '')}
                events.append(trace)
                logger.info('[Trace] node=%s status=%s errors=%d evidence=%d', name, trace['status'], trace['errors'], trace['evidence'])
                _persist_trace(trace_id=trace['trace_id'], task_id=state.get('task_id', ''), node=name, status=trace['status'], errors=trace['errors'], evidence=trace['evidence'], ts=trace['ts'])
            except Exception as e:
                logger.warning('[Orch] trace_event 记录失败 %s: %s', name, e)
            return state
        return timed('orchestrator.' + name)(wrapper)
    graph.add_node('node_quality_check', track(_quality_check, 'quality_check'))
    graph.add_node('node_vision_observe', track(_vision_observe, 'vision_observe'))
    graph.add_node('node_memory_read', track(_memory_read, 'memory_read'))
    graph.add_node('node_retrieval', track(_retrieval, 'retrieval'))
    graph.add_node('node_report_draft', track(_report_draft, 'report_draft'))
    graph.add_node('node_citation_validate', track(_citation_validate, 'citation_validate'))
    graph.add_node('node_memory_write', track(_memory_write, 'memory_write'))
    graph.add_node('node_ask_missing_info', track(_ask_missing_info, 'ask_missing_info'))
    graph.add_node('node_publish_gate', track(_publish_gate, 'publish_gate'))
    graph.add_node('node_refuse', track(_refuse_report, 'refuse'))
    graph.add_edge(START, 'node_quality_check')
    graph.add_conditional_edges('node_quality_check', _quality_gate, {'pass': 'node_vision_observe', 'fail': 'node_ask_missing_info'})
    graph.add_conditional_edges('node_vision_observe', _after_vision_gate, {'pass': 'node_memory_read', 'fail': 'node_ask_missing_info'})
    graph.add_edge('node_memory_read', 'node_retrieval')
    graph.add_conditional_edges('node_retrieval', _evidence_gate, {'sufficient': 'node_report_draft', 'insufficient': 'node_ask_missing_info', 'refuse': 'node_refuse'})
    graph.add_edge('node_ask_missing_info', 'node_quality_check')
    graph.add_edge('node_report_draft', 'node_citation_validate')
    graph.add_conditional_edges('node_citation_validate', _citation_gate, {'pass': 'node_memory_write', 'fail': 'node_report_draft', 'refuse': 'node_refuse'})
    graph.add_edge('node_refuse', END)
    graph.add_edge('node_memory_write', 'node_publish_gate')
    graph.add_edge('node_publish_gate', END)
    if checkpointer:
        return graph.compile(checkpointer=checkpointer)
    return graph.compile()
from app.agents.checkpointer import get_checkpointer
orchestrator = build_orchestrator(checkpointer=get_checkpointer())
