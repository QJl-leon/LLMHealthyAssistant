from __future__ import annotations
import logging
logger = logging.getLogger(__name__)
_POLARITY: dict[str, tuple[str, ...]] = {'avoid': ('禁忌', '避免', '不宜', '禁止', '慎用', '不应', '避免剧烈', '风险较高'), 'recommend': ('推荐', '建议', '适宜', '可以', '有助', '有助于', '适宜进行', '获益')}
_TOPIC_KEYWORDS = ('血压', '血脂', '血糖', '胆固醇', '甘油三酯', '转氨酶', '尿酸', '肌酐', '肝功能', '肾功能', '运动', '饮食', '用药', '心率', '体重', '腰围', '甲状腺', '心电', '超声', '骨密度', '血糖控制', '生活方式')

def _polarities(text: str) -> set[str]:
    hits: set[str] = set()
    for polarity, words in _POLARITY.items():
        if any((w in text for w in words)):
            hits.add(polarity)
    return hits

def _topics(text: str) -> set[str]:
    return {kw for kw in _TOPIC_KEYWORDS if kw in (text or '')}

def detect_evidence_conflicts(evidence: list) -> list[dict]:
    by_topic: dict[str, list[tuple[str, str, set[str]]]] = {}
    for ev in evidence or []:
        if not isinstance(ev, dict):
            continue
        text = str(ev.get('quote') or ev.get('text') or '')
        eid = str(ev.get('evidence_id') or ev.get('id') or '')
        pol = _polarities(text)
        if not pol:
            continue
        for topic in _topics(text):
            by_topic.setdefault(topic, []).append((eid, text, pol))
    conflicts: list[dict] = []
    for topic, items in by_topic.items():
        polarities: dict[str, list[str]] = {}
        for eid, _text, pol in items:
            for p in pol:
                polarities.setdefault(p, []).append(eid)
        if 'avoid' in polarities and 'recommend' in polarities:
            involved = sorted({e for ids in polarities.values() for e in ids})
            conflicts.append({'topic': topic, 'evidence_ids': involved, 'polarities': {k: sorted(set(v)) for k, v in polarities.items()}, 'quotes': [t[:120] for _e, t, _p in items][:4]})
    if conflicts:
        logger.warning('[Conflicts] 检测到 %d 组方向性冲突: %s', len(conflicts), [c['topic'] for c in conflicts])
    return conflicts

def conflict_is_addressed(conflict: dict, sections: dict) -> bool:
    topic = str(conflict.get('topic') or '')
    if not topic:
        return True
    conflicts_text = str(sections.get('conflicts') or '')
    if topic in conflicts_text:
        return True
    neutral_markers = ('存在不同', '说法不一', '结论不完全一致', '需个体化', '不同研究', '存在争议', '建议咨询')
    joined = ' '.join((str(v) for k, v in (sections or {}).items() if k != 'conflicts' and isinstance(v, str)))
    if topic in joined and any((m in joined for m in neutral_markers)):
        return True
    return False

def validate_conflicts_addressed(conflicts: list[dict], sections: dict) -> list[dict]:
    errors: list[dict] = []
    for c in conflicts or []:
        if conflict_is_addressed(c, sections or {}):
            continue
        errors.append({'error_code': 'CITATION_MISMATCH', 'message': f"证据对「{c.get('topic')}」存在方向相反的结论（证据 {c.get('evidence_ids')}），报告应尽量说明存在不同建议，不得只取一方下结论", 'claim_id': ''})
    return errors
