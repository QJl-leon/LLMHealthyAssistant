from uuid import uuid4
from typing import Optional
from dataclasses import dataclass, field

@dataclass
class Evidence:
    evidence_id: str
    doc_id: str
    source_level: int
    quote: str
    page: Optional[int] = None
    region: Optional[dict] = None
    knowledge_version: str = ''
    source_name: str = ''
    confidence: float = 1.0

def build_evidence_from_retrieval(channel_results: list[dict], source_levels: Optional[dict[str, int]]=None) -> list[Evidence]:
    evidence_list = []
    for item in channel_results:
        ev = Evidence(evidence_id=str(uuid4()), doc_id=item.get('doc_id', 'unknown'), source_level=item.get('source_level', source_levels.get(item['doc_id'], 3) if source_levels else 3), quote=item.get('snippet', '')[:500], knowledge_version=item.get('knowledge_version', ''), source_name=item.get('channel', 'unknown'), confidence=item.get('score', 0.0))
        evidence_list.append(ev)
    return evidence_list

def group_by_claim(evidence_list: list[Evidence]) -> dict[str, list[Evidence]]:
    groups: dict[str, list[Evidence]] = {}
    for ev in evidence_list:
        key = ev.doc_id
        if key not in groups:
            groups[key] = []
        groups[key].append(ev)
    return groups
