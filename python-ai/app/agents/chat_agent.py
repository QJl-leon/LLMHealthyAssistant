import logging
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
logger = logging.getLogger(__name__)
_REFUSE_TEXT = '我是一个健康顾问助手，建议我们多聊聊健康、运动、饮食相关的事情呢～'
_INTENT_HISTORY_TURNS = 6
_ANSWER_HISTORY_TURNS = 8
_HEALTH_KEYWORDS = ('运动', '健身', '锻炼', '训练', '跑步', '力量', '有氧', '抗阻', '拉伸', '减脂', '增肌', '体能', '心肺', '饮食', '营养', '睡眠', '作息', '减肥', '减重', '戒烟', '限酒', '生活方式', '食谱', '食物', '三餐', '早餐', '午餐', '晚餐', '吃什么', '吃啥', '菜单', '菜谱', '主食', '蔬菜', '水果', '蛋白质', '碳水', '热量', '卡路里', '血糖', '血脂', '血压', '尿酸', '胆固醇', '甘油三酯', '转氨酶', '肌酐', '血红蛋白', '体重', 'bmi', '腰围', '糖化', '肝功能', '肾功能', '贫血', '代谢', '健康', '体检', '报告', '指标', '复查', '复检')

class ChatState(TypedDict, total=False):
    query: str
    user_id: str
    tenant_id: str
    trace_id: str
    history: list
    intent: str
    user_profile: dict
    evidence: list
    answer: str
    refused: bool
    refuse_text: str

def _is_health_topic(query: str, history: list | None=None) -> bool:
    t = (query or '').lower()
    if any((k in t for k in _HEALTH_KEYWORDS)):
        return True
    for item in (history or [])[-_INTENT_HISTORY_TURNS:]:
        content = str((item or {}).get('content', '')).lower()
        if any((k in content for k in _HEALTH_KEYWORDS)):
            return True
    return False

def _history_context(history: list, turns: int) -> str:
    lines = []
    for item in (history or [])[-turns:]:
        role = str(item.get('role', ''))
        who = '医生' if role == 'assistant' else '用户'
        content = str(item.get('content', '')).strip()[:150]
        if content:
            lines.append(f'{who}：{content}')
    return '\n'.join(lines)

def _llm_is_health(query: str, history: list | None=None) -> bool:
    from app.gateway.adapters.llm import LLMAdapter
    context = _history_context(history or [], _INTENT_HISTORY_TURNS)
    user_content = query
    if context:
        user_content = f'最近对话：\n{context}\n\n用户最新一句话：{query}'
    llm = LLMAdapter.small()
    resp = llm.chat(messages=[{'role': 'system', 'content': '你是话题分类器。判断用户最新一句话是否涉及「健康、体检、运动、饮食、营养、睡眠、体重管理、食物、食谱、慢病指标」等话题。注意：\n① 用户可能是提问、陈述或表达偏好（如「我不想吃馒头」「最近睡不好」），只要话题属于上述领域就回复 health；\n② 省略式追问（如「那早餐呢」「再来一组」）要结合最近对话判断；\n③ 只有与这些领域完全无关（如天气、娱乐、时事、编程）才回复 other。\n只回复一个词：health 或 other。'}, {'role': 'user', 'content': user_content}], temperature=0, max_tokens=8)
    content = resp.get('choices', [{}])[0].get('message', {}).get('content', '')
    lowered = content.strip().lower()
    if 'other' in lowered and 'health' not in lowered:
        return False
    if 'health' in lowered:
        return True
    return True

def _classify_intent(state: ChatState) -> ChatState:
    query = state.get('query', '')
    history = state.get('history') or []
    try:
        is_health = _llm_is_health(query, history)
    except Exception as e:
        logger.warning('[Chat] 小模型意图判断失败，回退关键词: %s', e)
        is_health = _is_health_topic(query, history)
    if is_health:
        state['intent'] = 'health'
        state['refused'] = False
    else:
        state['intent'] = 'refuse'
        state['refused'] = True
        state['refuse_text'] = _REFUSE_TEXT
        logger.info('[Chat] 非健康话题，拒答: %s', query[:40])
    return state

def _intent_gate(state: ChatState) -> str:
    return 'refuse' if state.get('refused') else 'continue'

def _read_memory(state: ChatState) -> ChatState:
    user_id = state.get('user_id', '')
    profile: dict = {}
    try:
        from app.memory.curator import MemoryCurator
        curator = MemoryCurator()
        snapshot = curator.get_profile(user_id)
        profile = {'basic': [getattr(e, 'content', '') for e in snapshot.basic or []], 'conditions': [getattr(e, 'content', '') for e in snapshot.conditions or []], 'medications': [getattr(e, 'content', '') for e in snapshot.medications or []], 'allergies': [getattr(e, 'content', '') for e in snapshot.allergies or []], 'goals': [getattr(e, 'content', '') for e in snapshot.goals or []], 'exercises': [getattr(e, 'content', '') for e in snapshot.exercises or []]}
    except Exception as e:
        logger.warning('[Chat] 读取记忆失败（降级为空档案）: %s', e)
    state['user_profile'] = profile
    logger.info('[Chat] 记忆档案 %s', '已读取' if profile else '为空')
    return state

def _retrieve(state: ChatState) -> ChatState:
    query = state.get('query', '')
    user_id = state.get('user_id', '')
    history = state.get('history') or []
    retrieval_query = query
    if history and len(query.strip()) < 20:
        prev_user = next((str(h.get('content', '')).strip() for h in reversed(history) if str(h.get('role', '')) == 'user' and h.get('content')), '')
        if prev_user:
            retrieval_query = f'{prev_user} {query}'.strip()
            logger.info('[Chat] 短追问检索词补全: %s', retrieval_query[:60])
    try:
        from app.agents.retrieval_agent import retrieval_agent
        sub_state = {'trace_id': state.get('trace_id', ''), 'task_id': state.get('trace_id', ''), 'user_id': user_id, 'query': retrieval_query, 'abnormal_metrics': [], 'parsed_metrics': [], 'user_profile': state.get('user_profile', {}), 'image_urls': [], 'errors': []}
        result = retrieval_agent.invoke(sub_state)
        state['evidence'] = result.get('evidence', [])
    except Exception as e:
        logger.warning('[Chat] 检索失败（降级为空证据）: %s', e)
        state['evidence'] = []
    logger.info('[Chat] 检索证据 %d 条', len(state.get('evidence', [])))
    return state

def _generate_answer(state: ChatState) -> ChatState:
    query = state.get('query', '')
    profile = state.get('user_profile', {})
    evidence = state.get('evidence', [])
    history = state.get('history') or []
    evidence_text = ''
    for i, ev in enumerate(evidence[:8], 1):
        quote = str(ev.get('quote', ''))[:200]
        source = str(ev.get('source_name', ''))
        evidence_text += f'[{i}] {source}：{quote}\n'
    profile_text = ''
    for k, v in list(profile.items())[:10]:
        profile_text += f'- {k}: {v}\n'
    system_prompt = '你是一位亲切的健康顾问助手，负责回答用户的健康、运动、饮食相关问题。\n回答要求：\n① 医生口吻，自然亲切，先直接回应用户的问题；\n② 基于「证据」给出可执行建议，引用处用 [n] 标注证据编号；\n③ 不下诊断、不给处方；异常情况提示「建议就诊 XX 科室进一步评估」；\n④ 证据不足时诚实说明，不编造；\n⑤ 结合用户健康档案（如已有既往指标）与之前的对话内容个性化回答；\n⑥ 末尾一句免责声明「以上建议仅供参考，不能替代医生诊断」；\n⑦ 回答简洁，控制在 150 字以内（除非用户要求详细）。'
    user_msg = f"用户问题：{query}\n\n用户健康档案：\n{profile_text or '（暂无）'}\n\n检索到的证据（{len(evidence)} 条）：\n{evidence_text or '（无）'}\n\n请给出回答。"
    messages = [{'role': 'system', 'content': system_prompt}]
    for item in history[-_ANSWER_HISTORY_TURNS:]:
        role = str(item.get('role', ''))
        content = str(item.get('content', '')).strip()
        if role in ('user', 'assistant') and content:
            messages.append({'role': role, 'content': content[:800]})
    messages.append({'role': 'user', 'content': user_msg})
    try:
        from app.gateway.adapters.llm import LLMAdapter
        llm = LLMAdapter()
        resp = llm.chat(messages=messages, temperature=0.4, max_tokens=1024)
        answer = resp.get('choices', [{}])[0].get('message', {}).get('content', '')
        state['answer'] = answer.strip()
    except Exception as e:
        logger.warning('[Chat] LLM 生成失败（降级为空回答）: %s', e)
        state['answer'] = '抱歉，我暂时无法回答这个问题，请稍后再试。'
    state['refused'] = False
    return state

def _refuse(state: ChatState) -> ChatState:
    state['answer'] = state.get('refuse_text', _REFUSE_TEXT)
    state['evidence'] = []
    return state

def build_chat_agent() -> StateGraph:
    graph = StateGraph(ChatState)
    graph.add_node('classify_intent', _classify_intent)
    graph.add_node('read_memory', _read_memory)
    graph.add_node('retrieve', _retrieve)
    graph.add_node('generate_answer', _generate_answer)
    graph.add_node('refuse', _refuse)
    graph.add_edge(START, 'classify_intent')
    graph.add_conditional_edges('classify_intent', _intent_gate, {'refuse': 'refuse', 'continue': 'read_memory'})
    graph.add_edge('read_memory', 'retrieve')
    graph.add_edge('retrieve', 'generate_answer')
    graph.add_edge('generate_answer', END)
    graph.add_edge('refuse', END)
    return graph
chat_agent = build_chat_agent().compile()

def answer_health_question(query: str, user_id: str, tenant_id: str='dev-tenant', trace_id: str='', history: list | None=None) -> dict:
    result = chat_agent.invoke({'query': query, 'user_id': user_id, 'tenant_id': tenant_id, 'trace_id': trace_id or user_id, 'history': [h for h in history or [] if isinstance(h, dict) and h.get('content')][-_ANSWER_HISTORY_TURNS:]})
    return {'refused': bool(result.get('refused')), 'answer': str(result.get('answer', '')), 'evidence': result.get('evidence', [])}
