import logging
import re
from typing import TypedDict
from uuid import uuid4
from langgraph.graph import StateGraph, START, END
logger = logging.getLogger(__name__)
_TEXT_SECTIONS = ('facts', 'inferences', 'metric_reading', 'metric_trend')
_SECTION_KEYS = ('observation', 'facts', 'inferences', 'conflicts', 'unknowns', 'related_to_you', 'metric_reading', 'metric_trend')
_ADVICE_SECTIONS = ('exercise_advice', 'lifestyle_advice', 'followup_advice')
_BETA_BLOCKER_TERMS = ('β受体阻滞剂', 'β-受体阻滞剂', 'β阻滞剂', '倍他受体阻滞剂', '美托洛尔', '比索洛尔', '阿替洛尔', '普萘洛尔', '卡维地洛', '拉贝洛尔', '阿罗洛尔', '奈必洛尔', '倍他乐克', '康忻', '博苏', 'bisoprolol', 'metoprolol', 'atenolol', 'propranolol', 'carvedilol')

class ReportState(TypedDict, total=False):
    trace_id: str
    task_id: str
    user_id: str
    report_id: str
    evidence: list
    parsed_metrics: list
    abnormal_metrics: list
    metric_trends: list
    trend_summary: str
    image_observations: list
    user_profile: dict
    report_draft: dict
    validated_claims: list
    refuse_reason: str
    errors: list

def _metric_related_to_quote(metric_name: str, metric_code: str, quote: str) -> bool:
    if not quote:
        return False
    if metric_code and metric_code in quote:
        return True
    if not metric_name:
        return False
    idx = quote.find(metric_name)
    while idx >= 0:
        before = quote[idx - 1] if idx > 0 else ''
        if not '一' <= before <= '鿿':
            return True
        idx = quote.find(metric_name, idx + 1)
    return False

def _metric_line(metric: dict) -> str:
    name = str(metric.get('metric_name') or '').strip()
    code = str(metric.get('metric_code') or '').strip()
    unit = str(metric.get('unit') or '').strip()
    value = metric.get('value_text') or metric.get('value_num')
    value_s = '' if value is None else str(value)
    ref = str(metric.get('ref_text') or '').strip()
    if not ref:
        low, high = (metric.get('ref_low'), metric.get('ref_high'))
        if low is not None and high is not None:
            ref = f'{low}-{high}'
        elif high is not None:
            ref = f'<{high}'
        elif low is not None:
            ref = f'>{low}'
    flag = str(metric.get('flag') or 'unknown')
    parts = [f'{name}']
    if code:
        parts.append(f'({code})')
    if value_s:
        parts.append(f"{value_s}{(' ' + unit if unit else '')}")
    if ref:
        parts.append(f'参考区间 {ref}')
    parts.append(f'判定 {flag}')
    return ' '.join(parts)

def _organize_evidence(state: ReportState) -> ReportState:
    logger.info('[Report] organize_evidence metrics=%d trends=%d evidence=%d', len(state.get('parsed_metrics', [])), len(state.get('metric_trends', [])), len(state.get('evidence', [])))
    evidence = state.get('evidence') or []
    claims: list[dict] = []
    for metric in state.get('parsed_metrics') or []:
        name = str(metric.get('metric_name') or '').strip()
        code = str(metric.get('metric_code') or '').strip()
        related = [e for e in evidence if _metric_related_to_quote(name, code, str(e.get('quote') or ''))]
        claims.append({'claim_id': str(uuid4()), 'source': 'metric', 'metric_name': name, 'metric_code': str(metric.get('metric_code') or ''), 'value_num': metric.get('value_num'), 'ref_low': metric.get('ref_low'), 'ref_high': metric.get('ref_high'), 'ref_text': str(metric.get('ref_text') or ''), 'type': 'fact' if related else 'unknown', 'text': _metric_line(metric), 'evidence_ids': [str(e.get('evidence_id')) for e in related if e.get('evidence_id')]})
    for trend in state.get('metric_trends') or []:
        name = str(trend.get('metric_name') or '').strip()
        code = str(trend.get('metric_code') or '').strip()
        related = [e for e in evidence if _metric_related_to_quote(name, code, str(e.get('quote') or ''))]
        claims.append({'claim_id': str(uuid4()), 'source': 'trend', 'metric_name': name, 'metric_code': str(trend.get('metric_code') or ''), 'type': 'fact' if related else 'unknown', 'text': str(trend.get('summary') or ''), 'evidence_ids': [str(e.get('evidence_id')) for e in related if e.get('evidence_id')]})
    state['validated_claims'] = claims
    return state
REPORT_PROMPT_VERSION = 'v4.0'
_REPORT_SYSTEM_PROMPT = '你是一位个人健康顾问助手，负责根据用户的体检指标与检索到的证据，给出运动与生活方式建议（prompt ' + REPORT_PROMPT_VERSION + '）。\n产品红线（必须遵守，违反会被确定性校验拒绝）：\n① 不做诊断、不给处方与用药剂量：不得输出疾病诊断结论，不得建议任何药物名称、剂量或自行停换药；\n② 运动建议必须引用传入的证据编号 [n]，没有证据就不要给这条运动建议；饮食建议可基于通用营养学知识生成（饮食知识库后续补充，暂不强制引用），但不得编造研究结论或引用编号；\n③ 异常指标只能表述为「建议就诊 XX 科室进一步评估」，不得自行下结论；\n④ 不确定性 / 证据冲突必须显式列出（conflicts / unknowns 章节），不允许掩盖。\n健康建议内容标准（针对每个异常指标 / 健康问题，必须覆盖以下 8 项要素）：\n1. 建议对象：明确针对哪个异常指标（如「空腹血糖偏高」「低密度脂蛋白胆固醇升高」）；\n2. 问题解释：用通俗语言解释该异常可能代表什么，但不下确诊结论；\n3. 风险判断：明确低危 / 中危 / 高危，或「需尽快复查 / 近期复查 / 下次体检关注」；\n4. 复查建议：写清复查项目、建议时间、必要时建议科室；\n5. 饮食建议：具体到「多吃什么 / 少吃什么 / 避免什么」，不写「清淡饮食」这类空话；\n6. 运动建议：具体到频率、时长、强度或运动类型；\n7. 生活方式建议：覆盖睡眠、体重管理、戒烟限酒、压力管理、久坐改善等；\n8. 免责声明：必须提示「仅供参考，不能替代医生诊断」。\n表述约束：\n- 不确诊：写「存在糖代谢异常风险」，不写「你已患糖尿病」；\n- 不给用药方案：写「如需药物治疗，请由医生结合复查结果评估」；\n- 建议可执行、语言通俗，但保留关键指标（如「空腹血糖 6.5 mmol/L，参考 3.9-6.1 mmol/L」）。\n输出必须为严格的 JSON 格式（JSON Schema 约束，只输出 JSON），包含以下字段：\n' + '```json\n{\n  "summary": "医生概括 — 用亲切口语化的医生口吻，先 1-2 句整体评价（如「您身体状况基本稳定，但有几项指标需要重视」），再分「正常指标方面」「异常指标方面」简要列举，最后给 1 句综合判断（如「代谢系统出现早期信号，尚未到疾病阶段，可通过生活方式干预改善」）；不下诊断、不列具体数值",\n  "observation": "观察 — 从体检报告图片观察到的内容（2-3句）",\n  "facts": "事实 — 逐条证据的可读总结（3-5句），关键句末用 [n] 标注证据编号",\n  "inferences": "推断 — 基于证据的推理（2-3句），有依据处同样用 [n] 标注",\n  "conflicts": "冲突 — 多来源证据不一致时并列说明，无冲突留空字符串",\n  "unknowns": "未知 — 无法确认或证据不足的指标项，无则留空字符串",\n  "related_to_you": "与你相关 — 结合个人档案（既往病史/长期用药/过敏史/健康目标/运动基础）的健康提示，无则留空字符串",\n  "metric_reading": "指标解读 — 逐项解读：异常项目、检测结果、参考范围、问题分析、风险判断（低/中/高危+复查紧迫度）；末尾附免责声明「本建议由 AI 根据体检报告生成，仅供参考，不能替代医生诊断」；异常项写「建议就诊 XX 科室」，有依据处用 [n] 标注",\n  "metric_trend": "指标趋势 — 说明历次体检该指标的变化方向与幅度（只允许使用给定的趋势数据），有依据处用 [n] 标注",\n  "exercise_advice": [{"text": "运动建议 — 分「有氧运动（核心推荐）/ 抗阻训练（辅助推荐）/ 注意事项」展开，具体到频率/时长/强度/类型...[1][3]", "evidence_ids": ["证据编号"]}],\n  "lifestyle_advice": [{"text": "饮食建议 — 按异常指标维度展开（如控糖/低脂/低嘌呤），给出具体食物清单（多吃/少吃/避免）和一日食谱示例；基于通用营养学知识，evidence_ids 可留空", "evidence_ids": []}],\n  "followup_advice": [{"text": "复查建议（复查项目+建议时间+建议科室）...[1]", "evidence_ids": ["证据编号"]}]\n}\n```\n\n规则：\n- 只输出 JSON，不要任何 markdown 标记或额外说明\n- summary / observation / facts / inferences / conflicts / unknowns / related_to_you /\n  metric_reading / metric_trend 为中文段落；exercise_advice / lifestyle_advice /\n  followup_advice 为「建议列表」，每条建议是一个对象\n- 建议条目必须填写 evidence_ids：把正文里用到的 [n] 对应的证据「编号」原样抄进列表，\n  不得留空、不得编造编号；无证据支撑的**运动**建议直接不要写\n- 饮食建议（lifestyle_advice）的 evidence_ids 可留空：饮食知识库后续补充，暂用通用\n  营养学知识生成，但不得编造引用编号或具体研究结论\n- 指标数值与参考区间必须原样取自「本次体检指标数据」，不得改写、不得编造；\n  本次体检数据里没有的数值一律不要出现在报告里\n- 用药约束：若「个人档案」显示用户正在长期用药（尤其 β 受体阻滞剂），\n  运动建议不得用心率法评估强度，应改用主观疲劳度（RPE / Borg）或「谈话测试」，\n  并提示调整运动方案前先咨询医生；任何情况下都不得建议自行调整用药\n- 异常指标只做就医引导、不做诊断：写「建议到相应科室（如心内科 / 内分泌科）进一步评估」，\n  不要写「你患有 XX 病」\n- 引用编号 [n] 必须 ≤ 传入的证据总数，越界编号会导致报告被拒绝'

def _build_evidence_text(evidence: list) -> str:
    lines = []
    for i, e in enumerate(evidence[:20]):
        lines.append(f"- [{i + 1}] {str(e.get('quote') or '')[:200]} | 来源: {e.get('source_name', '')} | 类型: {e.get('evidence_type') or e.get('channel', '')} | 编号: {e.get('evidence_id', '')} | URL: {e.get('source_url', '')}")
    return '\n'.join(lines)

def _build_profile_text(profile: dict) -> str:
    text = str(profile.get('injection_text') or '')
    if text:
        return text
    labels = (('既往病史', profile.get('conditions') or []), ('长期用药', profile.get('medications') or []), ('过敏史', profile.get('allergies') or []), ('健康目标', profile.get('goals') or []), ('运动基础', profile.get('exercises') or []))
    parts = [f"{label}: {', '.join((str(x) for x in values))}" for label, values in labels if values]
    return '；'.join(parts)

def _fallback_sections(state: ReportState, evidence: list) -> dict:
    metrics = state.get('parsed_metrics') or []
    trends = state.get('metric_trends') or []
    facts_lines = [f"📋 [{i + 1}] {str(ev.get('quote') or '')}" for i, ev in enumerate(evidence)]
    return {'observation': '本次共解析体检指标 %d 项（其中异常 %d 项）。' % (len(metrics), len(state.get('abnormal_metrics') or [])), 'facts': '\n'.join(facts_lines) if facts_lines else '（无匹配证据）', 'inferences': '', 'conflicts': '', 'unknowns': '本次未能生成模型解读（模型不可用），仅展示真实解析结果与证据。', 'related_to_you': '', 'metric_reading': '\n'.join((f'- {_metric_line(m)}' for m in metrics)), 'metric_trend': '\n'.join((f"- {t.get('summary', '')}" for t in trends)), 'exercise_advice': [], 'lifestyle_advice': [], 'followup_advice': []}
_DEGRADED_MARK = '该部分因缺少可核验证据未生成，建议咨询医生获取个体化建议'

def degrade_failed_sections(sections: dict, errors: list) -> tuple[dict, list[str]]:
    failed_keys: set[str] = set()
    advice_error = False
    for e in errors or []:
        if not isinstance(e, dict):
            continue
        msg = str(e.get('message') or '')
        if '未绑定任何 evidence_id' in msg:
            advice_error = True
        for key in tuple(_TEXT_SECTIONS) + tuple(_ADVICE_SECTIONS):
            if key in msg:
                failed_keys.add(key)
    if advice_error:
        failed_keys.update(_ADVICE_SECTIONS)
    if not failed_keys:
        return (sections or {}, [])
    kept: dict = {}
    degraded: list[str] = []
    for key, val in (sections or {}).items():
        if key in failed_keys:
            kept[key] = [] if key in _ADVICE_SECTIONS else _DEGRADED_MARK
            degraded.append(key)
        else:
            kept[key] = val
    meaningful = [k for k in _TEXT_SECTIONS if kept.get(k) and kept.get(k) != _DEGRADED_MARK]
    advice_left = any((kept.get(k) for k in _ADVICE_SECTIONS))
    if not meaningful and (not advice_left):
        logger.warning('[Report] 所有章节都未通过校验，不做章节级降级（交由整篇拒答）')
        return (sections or {}, [])
    return (kept, degraded)

def _build_retry_block(state: ReportState) -> str:
    errors = state.get('errors') or []
    if not errors or not state.get('report_draft'):
        return ''
    lines = []
    for e in errors[:10]:
        if not isinstance(e, dict):
            continue
        cid = str(e.get('claim_id') or '')
        msg = str(e.get('message') or '').strip()
        if msg:
            lines.append(f"- {(cid + '：' if cid else '')}{msg}")
    if not lines:
        return ''
    renumber_note = ''
    if state.get('cited_evidence_ids') and state.get('compaction_events'):
        renumber_note = '\n注意：证据列表已按「被引用证据」压缩重排，请以上面给出的最新证据列表与编号为准进行引用。'
    return '上一版输出未通过确定性校验，请**针对下列具体问题定向修正**后重新输出完整 JSON（不要解释原因，也不要省略其他章节）：\n' + '\n'.join(lines) + '\n修正要求：引用编号必须来自上面给出的证据列表（越界编号一律删除或替换）；指标数值必须与给出的体检数据完全一致；没有证据支撑的建议必须删除；若某主题存在方向相反的结论，必须显式说明「存在不同建议」而不是只取一方。' + renumber_note

def _draft_report(state: ReportState) -> ReportState:
    logger.info('[Report] draft_report claims=%d', len(state.get('validated_claims', [])))
    from app.context.compaction import compact_state
    cited = state.get('cited_evidence_ids')
    compacted, compact_report = compact_state(state, cited_ids=set(cited) if cited else None)
    if compact_report.get('triggered'):
        state.update(compacted)
        events = list(state.get('compaction_events') or [])
        events.append(compact_report)
        state['compaction_events'] = events
        logger.info('[Report] 上下文压缩已触发（cited 模式=%s）: %s', bool(cited), compact_report)
    evidence_list = state.get('evidence', [])
    claims = state.get('validated_claims', [])
    metrics = state.get('parsed_metrics') or []
    trends = state.get('metric_trends') or []
    profile = state.get('user_profile', {}) or {}
    metrics_text = '\n'.join((f'- {_metric_line(m)}' for m in metrics)) or '（本次未解析到体检指标）'
    trend_text = str(state.get('trend_summary') or '').strip()
    if not trend_text:
        trend_text = '\n'.join((f"- {t.get('summary', '')}" for t in trends)) or '（无历史体检记录）'
    vlm_text = ''
    for obs in state.get('image_observations', []):
        if obs.get('type') != 'vlm_analysis':
            continue
        parts = []
        if obs.get('report_date'):
            parts.append(f"报告日期: {obs['report_date']}")
        if obs.get('institution'):
            parts.append(f"体检机构: {obs['institution']}")
        parts.append(f"识别指标: {obs.get('metrics', 0)} 项")
        vlm_text = '；'.join(parts) + '\n'
        break
    profile_text = _build_profile_text(profile)
    from app.context.budget import allocate_evidence_budget, build_evidence_text_with_budget
    from app.context.compaction import estimate_tokens as _est_tokens
    ev_budget = allocate_evidence_budget(system_prompt_tokens=_est_tokens(_REPORT_SYSTEM_PROMPT), metrics_tokens=_est_tokens(metrics_text), trend_tokens=_est_tokens(trend_text), profile_tokens=_est_tokens(profile_text), evidence_count=len(evidence_list))
    evidence_text = build_evidence_text_with_budget(evidence_list, ev_budget)
    logger.info('[Report] 证据预算: %s', ev_budget.reason)
    user_msg = f"本次体检指标数据（共 {len(metrics)} 项，数值必须原样使用）:\n{metrics_text}\n\n指标时序趋势:\n{trend_text}\n\n{vlm_text}检索到的证据（共 {len(evidence_list)} 条，预算内展示 {min(ev_budget.max_items, len(evidence_list))} 条）:\n{evidence_text}\n\n用户健康档案: {profile_text or '无特殊记录'}"
    retry_block = _build_retry_block(state)
    if retry_block:
        logger.info('[Report] 回炉第 %d 次，注入 %d 条校验错误', len(state.get('errors') or []), len(retry_block.splitlines()) - 1)
        user_msg += '\n\n' + retry_block
    try:
        from app.gateway.adapters.llm import LLMAdapter
        from app.context.cost import BudgetExceededError, QuotaExceededError
        import json
        llm = LLMAdapter()
        resp = llm.chat(messages=[{'role': 'system', 'content': _REPORT_SYSTEM_PROMPT}, {'role': 'user', 'content': user_msg}], temperature=0.3, max_tokens=8192, response_format={'type': 'json_object'})
        content = resp.get('choices', [{}])[0].get('message', {}).get('content', '')
        logger.info('[Report] LLM 返回 %d chars', len(content))
        clean = content.strip()
        if clean.startswith('```'):
            clean = clean.split('```')[1]
            if clean.startswith('json'):
                clean = clean[4:]
            clean = clean.strip()
        raw_sections = json.loads(clean)
    except BudgetExceededError as be:
        logger.warning('[Report] 任务 token 预算超限，降级为真实数据拼接: %s', be)
        raw_sections = _fallback_sections(state, evidence_list)
        state['errors'] = state.get('errors', []) + [{'error_code': 'BUDGET_EXCEEDED', 'message': f'任务 token 预算超限，已降级（不生成建议）: {be}', 'retryable': False}]
    except QuotaExceededError as qe:
        logger.warning('[Report] 用户日配额超限，拒绝生成: %s', qe)
        state['errors'] = state.get('errors', []) + [{'error_code': 'QUOTA_EXCEEDED', 'message': f'用户日配额超限: {qe}', 'retryable': False}]
        raise
    except Exception as e:
        logger.warning('[Report] LLM 生成失败，降级为真实数据拼接（不生成建议）: %s', e)
        raw_sections = _fallback_sections(state, evidence_list)
        state['errors'] = state.get('errors', []) + [{'error_code': 'LLM_DEGRADED', 'message': f'报告模型调用失败，已降级为真实数据拼接: {e}', 'retryable': True}]
    sections, advice_claims = _normalize_sections(raw_sections, evidence_list)
    sections = _enrich_personal_sections(sections, profile, metrics)
    report = {'version': 'draft_v3', 'prompt_version': REPORT_PROMPT_VERSION, 'sections': sections, 'claims': claims, 'advice_claims': advice_claims, 'evidence': evidence_list}
    state['report_draft'] = report
    return state

def _normalize_sections(raw: dict, evidence_list: list) -> tuple[dict, list[dict]]:
    raw = raw if isinstance(raw, dict) else {}
    sections: dict = {}
    for key in _SECTION_KEYS:
        value = raw.get(key)
        sections[key] = '' if value is None else str(value).strip()
    advice_claims: list[dict] = []
    for key in _ADVICE_SECTIONS:
        items = _normalize_advice(raw.get(key), key, evidence_list)
        advice_claims.extend(items)
        sections[key] = '\n'.join((f"- {it['text']}" for it in items))
    return (sections, advice_claims)

def _normalize_advice(raw_items, section_key: str, evidence_list: list) -> list[dict]:
    if isinstance(raw_items, str):
        raw_items = [raw_items] if raw_items.strip() else []
    if not isinstance(raw_items, list):
        return []
    items: list[dict] = []
    for idx, item in enumerate(raw_items):
        if isinstance(item, str):
            text, raw_ids = (item.strip(), [])
        elif isinstance(item, dict):
            text = str(item.get('text') or item.get('content') or '').strip()
            raw_ids = item.get('evidence_ids') or item.get('evidence_id') or []
            if isinstance(raw_ids, (str, int)):
                raw_ids = [raw_ids]
        else:
            continue
        text = re.sub('^[-•*]\\s*', '', text).strip()
        if not text:
            continue
        items.append({'claim_id': f'advice_{section_key}_{idx + 1}', 'type': 'advice', 'section': section_key, 'text': text, 'evidence_ids': _resolve_evidence_ids(raw_ids, text, evidence_list)})
    return items

def _resolve_evidence_ids(raw_ids, text: str, evidence_list: list) -> list[str]:
    registered = [str(e.get('evidence_id')) for e in evidence_list if isinstance(e, dict) and e.get('evidence_id')]
    resolved: list[str] = []
    for rid in raw_ids or []:
        token = str(rid).strip()
        if not token:
            continue
        if token in registered:
            resolved.append(token)
        elif token.isdigit() and 1 <= int(token) <= len(registered):
            resolved.append(registered[int(token) - 1])
        else:
            resolved.append(token)
    if not resolved:
        for m in re.findall('\\[(\\d+)\\]', text or ''):
            i = int(m)
            if 1 <= i <= len(registered):
                resolved.append(registered[i - 1])
    return list(dict.fromkeys(resolved))

def _enrich_personal_sections(sections: dict, profile: dict, metrics: list) -> dict:
    related = profile.get('related') or []
    lines = []
    for r in related:
        if not isinstance(r, dict):
            continue
        name = r.get('metric') or r.get('metric_name') or ''
        reason = r.get('reason', '')
        entry = r.get('memory_entry', '')
        layer = r.get('memory_layer', 'profile')
        icon = '⚠️' if '过敏' in reason else '💊' if '用药' in reason else '📜' if layer == 'episodic' else '👤'
        lines.append(f'{icon} {name} — {reason}（记忆: {entry} / {layer}）')
    if not lines:
        keywords = ((profile.get('allergies') or [], '⚠️', '匹配过敏史，请谨慎并咨询医生'), (profile.get('conditions') or [], '👤', '与既往病史相关，建议持续关注'), (profile.get('medications') or [], '💊', '与长期用药相关，请遵医嘱'), (profile.get('goals') or [], '🎯', '与您的健康目标相关'), (profile.get('exercises') or [], '🏃', '与您的运动基础相关'))
        for metric in metrics:
            haystack = f"{metric.get('metric_name', '')}{metric.get('category', '')}"
            for entries, icon, reason in keywords:
                hit = next((e for e in entries if e and str(e) in haystack), None)
                if hit:
                    lines.append(f"{icon} {metric.get('metric_name', '')} — {reason}（记忆: {hit}）")
    constraint = _medication_exercise_constraint(profile)
    if constraint:
        lines.append(constraint)
    if not sections.get('related_to_you'):
        sections['related_to_you'] = '\n'.join(lines)
    elif constraint:
        sections['related_to_you'] = f"{sections['related_to_you']}\n{constraint}"
    items = profile.get('injection_items') or []
    if items:
        inj_lines = []
        for it in items[:12]:
            layer = it.get('layer', 'profile')
            kind = it.get('kind', '')
            content = it.get('content', '')
            inj_lines.append(f'[{layer}/{kind}] {content}')
        sections['memory_injection'] = '\n'.join(inj_lines)
    elif profile.get('injection_text'):
        sections['memory_injection'] = str(profile['injection_text'])
    return sections

def _medication_exercise_constraint(profile: dict) -> str:
    medications = [str(m) for m in profile.get('medications') or [] if m]
    if not medications:
        return ''
    beta = [m for m in medications if any((term.lower() in m.lower() for term in _BETA_BLOCKER_TERMS))]
    if beta:
        return f"💊 长期用药约束（{'、'.join(beta)}）：服用 β 受体阻滞剂会压低运动心率，用心率法评估运动强度不可靠，请改用主观疲劳度（RPE / Borg）或「谈话测试」控制强度；调整运动方案或用药前请先咨询医生。"
    return f"💊 长期用药提示（{'、'.join(medications[:5])}）：运动与生活方式建议需结合用药情况，调整方案前请先咨询医生，不要自行调整用药。"

def run_deterministic_checks(report_draft: dict, evidence: list, *, user_id: str='', report_id: str='', name_lookup=None) -> list[dict]:
    from app.evidence.validator import validate_advice_has_evidence, validate_existence, validate_metric_name, validate_metric_value, validate_support
    draft = report_draft or {}
    sections = draft.get('sections') if isinstance(draft.get('sections'), dict) else {}
    claims = draft.get('claims') or []
    advice_claims = draft.get('advice_claims') or []
    evidence = evidence or []
    registered = {str(e.get('evidence_id')) for e in evidence if isinstance(e, dict) and e.get('evidence_id')}
    ev_by_id = {str(e.get('evidence_id')): e for e in evidence if isinstance(e, dict) and e.get('evidence_id')}
    errors: list[dict] = []

    def _fail(message: str, claim_id: str='') -> None:
        errors.append({'error_code': 'CITATION_MISMATCH', 'message': message, 'claim_id': claim_id})
    max_n = len(evidence)
    for key in _TEXT_SECTIONS:
        bad = [f'{key}:[{m}]' for m in re.findall('\\[(\\d+)\\]', str(sections.get(key) or '')) if not 1 <= int(m) <= max_n]
        if bad:
            _fail(f"报告正文引用编号无效: {', '.join(bad)}")
    for item in advice_claims:
        bad = [f'[{m}]' for m in re.findall('\\[(\\d+)\\]', str(item.get('text') or '')) if not 1 <= int(m) <= max_n]
        if bad:
            _fail(f"建议 {item.get('claim_id')} 引用编号无效: {', '.join(bad)}", item.get('claim_id', ''))
    checked_codes: set[str] = set()
    checked_names: set[str] = set()
    for claim in claims:
        cid = str(claim.get('claim_id') or '')
        eids = [str(x) for x in claim.get('evidence_ids') or [] if x]
        if eids:
            result = validate_existence(cid, eids, registered_ids=registered)
            for failure in result.failures:
                _fail(failure, cid)
        if claim.get('type') in ('fact', 'inference') and eids:
            quote = ' '.join((str(ev_by_id.get(eid, {}).get('quote') or '') for eid in eids))
            support = validate_support(cid, str(claim.get('text') or ''), quote)
            for failure in support.failures:
                _fail(failure, cid)
        code = str(claim.get('metric_code') or '')
        unregistered = code.startswith('X_')
        has_number = claim.get('value_num') is not None
        if code and has_number and (not unregistered) and (code not in checked_codes):
            checked_codes.add(code)
            value = validate_metric_value(cid, code, claim.get('value_num'), user_id, report_id or None)
            for failure in value.failures:
                _fail(failure, cid)
        name = str(claim.get('metric_name') or '')
        if name and (not unregistered) and (name not in checked_names):
            checked_names.add(name)
            named = validate_metric_name(cid, name, name_lookup=name_lookup)
            for failure in named.failures:
                _fail(failure, cid)
    advice = validate_advice_has_evidence(advice_claims, evidence)
    for failure in advice.failures:
        _fail(failure, advice.claim_id)
    try:
        from app.evidence.conflicts import detect_evidence_conflicts, validate_conflicts_addressed
        conflicts = detect_evidence_conflicts(evidence)
        if conflicts:
            errors.extend(validate_conflicts_addressed(conflicts, sections))
    except Exception as e:
        logger.warning('[Report] 冲突检测异常（不阻塞校验）: %s', e)
    if errors:
        logger.warning('[Report] 确定性校验失败 %d 项，示例: %s', len(errors), errors[0].get('message'))
    return errors

def _citation_self_check(state: ReportState) -> ReportState:
    logger.info('[Report] citation_self_check')
    draft = state.get('report_draft') or {}
    evidence = state.get('evidence') or []
    errors = run_deterministic_checks(draft, evidence, user_id=str(state.get('user_id') or ''), report_id=str(state.get('report_id') or ''))
    if errors:
        state['errors'] = state.get('errors', []) + errors
        if not state.get('refuse_reason'):
            state['refuse_reason'] = errors[0].get('message', '引用校验失败')
    for claim in state.get('validated_claims', []):
        if not claim.get('evidence_ids'):
            claim['_needs_review'] = True
    cited: set[str] = set()
    for item in draft.get('advice_claims') or []:
        if isinstance(item, dict):
            cited.update((str(x) for x in item.get('evidence_ids') or [] if x))
    registered = [str(e.get('evidence_id')) for e in evidence if isinstance(e, dict) and e.get('evidence_id')]
    sections = draft.get('sections') if isinstance(draft.get('sections'), dict) else {}
    for key in _TEXT_SECTIONS:
        for m in re.findall('\\[(\\d+)\\]', str(sections.get(key) or '')):
            i = int(m)
            if 1 <= i <= len(registered):
                cited.add(registered[i - 1])
    if cited:
        state['cited_evidence_ids'] = sorted(cited)
        logger.info('[Report] 被引用证据 %d/%d 条', len(cited), len(registered))
    return state

def build_report_agent() -> StateGraph:
    graph = StateGraph(ReportState)
    graph.add_node('organize_evidence', _organize_evidence)
    graph.add_node('draft_report', _draft_report)
    graph.add_node('citation_self_check', _citation_self_check)
    graph.add_edge(START, 'organize_evidence')
    graph.add_edge('organize_evidence', 'draft_report')
    graph.add_edge('draft_report', 'citation_self_check')
    graph.add_edge('citation_self_check', END)
    return graph
report_agent = build_report_agent().compile()
