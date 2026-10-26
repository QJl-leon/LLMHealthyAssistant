from __future__ import annotations
import re
from dataclasses import dataclass, field
from typing import Any, Optional
DEFAULT_CHUNK_SIZE = 512
DEFAULT_OVERLAP = 128
_SENT_BOUNDARY = re.compile('(?<=[。！？!?\\n])\\s*')

@dataclass
class Chunk:
    text: str
    doc_id: str
    source_id: str = ''
    source_type: str = ''
    source_level: int = 1
    knowledge_version: str = ''
    page: Optional[int] = None
    strategy: str = 'evidence_row'
    chunk_index: int = 0
    parent_key: str = ''
    role: str = 'child'
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def index_key(self) -> str:
        prefix = 'p' if self.role == 'parent' else 'c'
        return f'{self.doc_id}:{prefix}{self.chunk_index}'

def _field(row: dict, key: str) -> str:
    value = row.get(key)
    return '' if value is None else str(value).strip()

def _page_of(content) -> Optional[int]:
    if not isinstance(content, dict):
        return None
    page = content.get('page')
    try:
        return int(page) if page is not None else None
    except (TypeError, ValueError):
        return None
