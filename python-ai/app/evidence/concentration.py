import logging
import math
from dataclasses import dataclass, field
from typing import Optional
logger = logging.getLogger(__name__)
LIGHT_CONCENTRATION = 0.5
MODERATE_CONCENTRATION = 0.7
HEAVY_CONCENTRATION = 0.9
SOURCE_LEVEL_WEIGHT = {1: 0.5, 2: 0.7, 3: 1.0, 4: 1.2}

@dataclass
class ConcentrationResult:
    total_evidence: int
    unique_sources: int
    unique_channels: int
    max_source_ratio: float
    dominant_source: str
    source_entropy: float
    channel_distribution: dict[str, int]
    level: str = 'diverse'
    needs_diversification: bool = False
    diversification_queries: list[str] = field(default_factory=list)

    def __repr__(self):
        return f'Concentration(level={self.level}, max_ratio={self.max_source_ratio:.2f}, entropy={self.source_entropy:.2f}, sources={self.unique_sources}, channels={self.unique_channels})'

def check_concentration(evidence: list[dict], threshold: float=MODERATE_CONCENTRATION, min_evidence_for_check: int=4) -> ConcentrationResult:
    if len(evidence) < min_evidence_for_check:
        return ConcentrationResult(total_evidence=len(evidence), unique_sources=0, unique_channels=0, max_source_ratio=0, dominant_source='', source_entropy=0, channel_distribution={}, level='diverse')
    source_counts: dict[str, int] = {}
    channel_counts: dict[str, int] = {}
    source_levels: dict[str, int] = {}
    for ev in evidence:
        source_id = ev.get('doc_id', '') or ev.get('source_name', '') or ev.get('channel', 'unknown')
        source_counts[source_id] = source_counts.get(source_id, 0) + 1
        channel = ev.get('channel', 'unknown')
        channel_counts[channel] = channel_counts.get(channel, 0) + 1
        level = ev.get('source_level', 4)
        if source_id not in source_levels:
            source_levels[source_id] = level
    total = len(evidence)
    max_source = ''
    max_count = 0
    for src, cnt in source_counts.items():
        if cnt > max_count:
            max_count = cnt
            max_source = src
    max_ratio = max_count / total if total > 0 else 0
    source_entropy = 0.0
    for cnt in source_counts.values():
        p = cnt / total
        if p > 0:
            source_entropy -= p * math.log(p)
    if len(source_counts) > 1:
        source_entropy = source_entropy / math.log(len(source_counts))
    if max_ratio >= HEAVY_CONCENTRATION:
        level = 'heavy'
    elif max_ratio >= MODERATE_CONCENTRATION:
        level = 'moderate'
    elif max_ratio >= LIGHT_CONCENTRATION:
        level = 'light'
    else:
        level = 'diverse'
    needs_div = max_ratio >= threshold
    div_queries: list[str] = []
    if needs_div:
        div_queries = _generate_diversification_queries(evidence, source_counts, channel_counts, max_source)
    result = ConcentrationResult(total_evidence=len(evidence), unique_sources=len(source_counts), unique_channels=len(channel_counts), max_source_ratio=max_ratio, dominant_source=max_source, source_entropy=min(source_entropy, 1.0), channel_distribution=channel_counts, level=level, needs_diversification=needs_div, diversification_queries=div_queries)
    if needs_div:
        logger.warning('[Concentration] 来源集中度=%s max_ratio=%.0f%% dominant=%s sources=%d 建议补充查询=%d', level, max_ratio * 100, max_source, len(source_counts), len(div_queries))
    return result

def _generate_diversification_queries(evidence: list[dict], source_counts: dict[str, int], channel_counts: dict[str, int], dominant_source: str) -> list[str]:
    queries = []
    all_channels = {'bm25', 'dense', 'sql', 'image'}
    present_channels = set(channel_counts.keys())
    missing = all_channels - present_channels
    topics = set()
    for ev in evidence:
        snippet = ev.get('snippet', '') or ev.get('quote', '')
        import re
        words = re.findall('[一-鿿]{2,}', str(snippet)[:100])
        topics.update(words[:3])
    topic_str = ' '.join(list(topics)[:5]) if topics else '健康指标'
    if 'sql' in missing:
        queries.append(f'查表: {topic_str} 的指标目录与参考区间数据')
    if 'dense' in missing:
        queries.append(f'语义检索: {topic_str} 的健康指南与运动干预研究')
    if 'bm25' in missing:
        queries.append(f'精确匹配: {topic_str} 的指南名称与指标术语')
    if len(source_counts) == 1 and len(evidence) >= 3:
        for topic in list(topics)[:2]:
            queries.append(f'交叉验证: {topic} 的其他数据来源')
    levels = {ev.get('source_level', 4) for ev in evidence}
    if min(levels) >= 3 and len(evidence) >= 4:
        queries.append(f'补充高权威来源: {topic_str} 的健康指南与共识原文')
    return queries[:5]

def annotate_evidence(evidence: list[dict], result: ConcentrationResult) -> list[dict]:
    for ev in evidence:
        source_id = ev.get('doc_id', '') or ev.get('source_name', '') or ev.get('channel', '')
        ev['concentration_level'] = result.level
        ev['concentration_flag'] = source_id == result.dominant_source
        ev['source_entropy'] = result.source_entropy
    return evidence
