import logging
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
logger = logging.getLogger(__name__)

class MemoryState(TypedDict):
    trace_id: str
    task_id: str
    user_id: str
    user_profile: dict
    parsed_metrics: list
    abnormal_metrics: list
    image_observations: list
    memory_writes_pending: list
    errors: list
_METRIC_TERM_MAP: dict[str, tuple[str, ...]] = {'血脂': ('血脂', '胆固醇', '甘油三酯', '低密度脂蛋白', '高密度脂蛋白', '载脂蛋白', '他汀', '降脂', '贝特', '血脂异常'), '血糖': ('血糖', '糖尿病', '糖化血红蛋白', '胰岛素', '二甲双胍', '控糖', '空腹血糖'), '肝功能': ('肝功能', '转氨酶', '谷丙转氨酶', '谷草转氨酶', '脂肪肝', '肝炎'), '肾功能': ('肾功能', '肌酐', '尿酸', '痛风', '尿素氮', 'eGFR', '肾小球'), '血压': ('血压', '高血压', '降压', '收缩压', '舒张压'), '血常规': ('贫血', '血红蛋白', '白细胞', '血小板', '红细胞'), '甲状腺': ('甲状腺', '促甲状腺激素', '甲亢', '甲减'), '体格': ('体重', '肥胖', 'BMI', '体质指数', '减重', '体脂', '腰围'), '尿常规': ('尿蛋白', '尿潜血', '尿常规')}
_REASON_BY_KIND = {'basic': '基本信息相关', 'condition': '既往病史命中', 'medication': '长期用药约束', 'allergy': '过敏史命中', 'goal': '健康目标相关', 'exercise': '运动基础参考'}
_KIND_PRIORITY = ('medication', 'allergy', 'condition', 'goal', 'exercise', 'basic')

def _report_hint(state: MemoryState) -> tuple[str, str]:
    for obs in state.get('image_observations') or []:
        if obs.get('type') == 'vlm_analysis':
            return (str(obs.get('report_date') or ''), str(obs.get('institution') or ''))
    return ('', '')

def _normalize(s: str) -> str:
    return ''.join((ch for ch in s.lower() if ch.isalnum() or '一' <= ch <= '鿿'))

def _terms_for(metric: dict) -> set[str]:
    name = str(metric.get('metric_name') or '')
    category = str(metric.get('category') or '')
    terms = {name, category}
    if category:
        terms.update(_METRIC_TERM_MAP.get(category, ()))
    else:
        for cat, words in _METRIC_TERM_MAP.items():
            if any((w in name for w in words)):
                terms.add(cat)
                terms.update(words)
                break
    return {t for t in terms if t and len(t) >= 2}

def _profile_entries(snapshot) -> list[dict]:
    entries: list[dict] = []
    groups = (('basic', getattr(snapshot, 'basic', [])), ('condition', getattr(snapshot, 'conditions', [])), ('medication', getattr(snapshot, 'medications', [])), ('allergy', getattr(snapshot, 'allergies', [])), ('goal', getattr(snapshot, 'goals', [])), ('exercise', getattr(snapshot, 'exercises', [])))
    for kind, items in groups:
        for e in items or []:
            entries.append({'kind': kind, 'content': str(getattr(e, 'content', '') or ''), 'metric_codes': [str(c) for c in getattr(e, 'metric_codes', None) or [] if c]})
    return entries

def _read_profile(state: MemoryState) -> MemoryState:
    logger.info('[Memory] read_profile user=%s', state.get('user_id', 'dev-user'))
    from app.memory.curator import MemoryCurator
    curator = MemoryCurator()
    uid = state.get('user_id', 'dev-user')
    _, institution = _report_hint(state)
    metric_codes = [str(m.get('metric_code')).strip() for m in state.get('parsed_metrics') or [] if m.get('metric_code')]
    snapshot, injection_text, injection_items = curator.build_injection(uid, report_label=institution if institution != 'unknown' else '', metric_codes=metric_codes, max_tokens=500)
    state['user_profile'] = {'basic': [e.content for e in getattr(snapshot, 'basic', [])], 'conditions': [e.content for e in snapshot.conditions], 'medications': [e.content for e in snapshot.medications], 'allergies': [e.content for e in snapshot.allergies], 'goals': [e.content for e in snapshot.goals], 'exercises': [e.content for e in snapshot.exercises], 'entries': _profile_entries(snapshot), 'episodes': snapshot.episodes, 'injection_text': injection_text, 'injection_items': injection_items, 'related': []}
    return state

def _extract_candidates(state: MemoryState) -> MemoryState:
    logger.info('[Memory] extract_candidates')
    state['memory_writes_pending'] = []
    return state

def _check_relevance(state: MemoryState) -> MemoryState:
    logger.info('[Memory] check_relevance')
    profile = state.get('user_profile') or {}
    metrics = state.get('parsed_metrics') or []
    entries = profile.get('entries') or []
    related: list[dict] = []
    ordered = sorted(entries, key=lambda e: _KIND_PRIORITY.index(e.get('kind')) if e.get('kind') in _KIND_PRIORITY else len(_KIND_PRIORITY))
    for metric in metrics:
        name = str(metric.get('metric_name') or '').strip()
        code = str(metric.get('metric_code') or '').strip()
        if not name and (not code):
            continue
        terms = {_normalize(t) for t in _terms_for(metric)}
        for entry in ordered:
            content = str(entry.get('content') or '').strip()
            if not content:
                continue
            reasons = entry.get('metric_codes') or []
            if code and code in reasons:
                reason = _REASON_BY_KIND.get(entry.get('kind', ''), '健康档案命中')
                reason += '（指标编码匹配）'
            elif any((t and t in _normalize(content) for t in terms)):
                reason = _REASON_BY_KIND.get(entry.get('kind', ''), '健康档案命中')
            else:
                continue
            related.append({'metric': name or code, 'metric_code': code, 'reason': reason, 'memory_entry': content, 'memory_layer': 'profile'})
            break
    _, institution = _report_hint(state)
    for ep in profile.get('episodes') or []:
        ep_name = ep.get('product_name') or ''
        if institution and ep_name and (institution in ep_name or ep_name in institution):
            related.append({'metric': institution, 'reason': '历史体检命中（同机构）', 'memory_entry': ep_name, 'memory_layer': 'episodic', 'task_id': ep.get('task_id', '')})
            break
    profile['related'] = related
    state['user_profile'] = profile
    logger.info('[Memory] found %d related items', len(related))
    return state

def build_memory_agent() -> StateGraph:
    graph = StateGraph(MemoryState)
    graph.add_node('read_profile', _read_profile)
    graph.add_node('extract_candidates', _extract_candidates)
    graph.add_node('check_relevance', _check_relevance)
    graph.add_edge(START, 'read_profile')
    graph.add_edge('read_profile', 'extract_candidates')
    graph.add_edge('extract_candidates', 'check_relevance')
    graph.add_edge('check_relevance', END)
    return graph
memory_agent = build_memory_agent().compile()
