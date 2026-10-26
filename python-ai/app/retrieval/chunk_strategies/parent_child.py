from __future__ import annotations
import os
from typing import Any, Optional
from app.retrieval.chunk_strategies.base import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP, Chunk, _field, _page_of
from app.retrieval.chunk_strategies.evidence_row import naturalize_content
from app.retrieval.chunk_strategies.sliding_window import chunk_sliding_window
PARENT_MIN_CHARS = int(os.getenv('PARENT_MIN_CHARS', '1200'))
PARENT_MAX_CHARS = int(os.getenv('PARENT_MAX_CHARS', '3000'))

def build_parent_child_chunks(parsed_docs: list[dict | Any], *, chunk_size: int=DEFAULT_CHUNK_SIZE, overlap: int=DEFAULT_OVERLAP, parent_min_chars: int=PARENT_MIN_CHARS, parent_max_chars: int=PARENT_MAX_CHARS) -> tuple[dict[str, str], list[Chunk]]:
    parents: dict[str, str] = {}
    children: list[Chunk] = []
    for idx, doc in enumerate(parsed_docs):
        if hasattr(doc, 'content'):
            content = doc.content
            doc_id = str(getattr(doc, 'id', '') or f'doc_{idx}')
            source_id = str(getattr(doc, 'source_id', ''))
            source_level = int(getattr(doc, 'source_level', 1) or 1)
            kv = str(getattr(doc, 'knowledge_version', '') or '')
        else:
            content = doc.get('content', {})
            doc_id = str(doc.get('id', '') or f'doc_{idx}')
            source_id = str(doc.get('source_id', ''))
            source_level = int(doc.get('source_level', 1) or 1)
            kv = str(doc.get('knowledge_version', '') or '')
        text = naturalize_content(content)
        if not text:
            continue
        source_type = (_field(content, 'source_type') or _field(content, 'kind')).lower() if isinstance(content, dict) else ''
        page = _page_of(content)
        parent_key = f'{doc_id}:p0'
        parents[parent_key] = text[:parent_max_chars]
        meta = dict(content) if isinstance(content, dict) else {}
        meta['source_type'] = source_type
        if len(text) <= parent_min_chars:
            children.append(Chunk(text=text, doc_id=doc_id, source_id=source_id, source_type=source_type, source_level=source_level, knowledge_version=kv, page=page, strategy='parent_as_child', chunk_index=0, parent_key=parent_key, metadata=meta))
            continue
        for i, piece in enumerate(chunk_sliding_window(text, chunk_size=chunk_size, overlap=overlap)):
            children.append(Chunk(text=piece, doc_id=doc_id, source_id=source_id, source_type=source_type, source_level=source_level, knowledge_version=kv, page=page, strategy='semantic_window', chunk_index=i, parent_key=parent_key, metadata=meta))
    return (parents, children)

def expand_to_parent(ranked: list[dict], parents: dict[str, str], child_of: Optional[dict[str, str]]=None) -> list[dict]:
    out: list[dict] = []
    for item in ranked:
        it = dict(item)
        key = str(it.get('id') or it.get('doc_id') or '')
        pk = str(it.get('parent_key') or '')
        if not pk and child_of:
            pk = child_of.get(key, '')
        if not pk and key:
            head, _, tail = key.rpartition(':')
            if not head:
                pk = key
            elif tail[:1] in ('c', 'p'):
                pk = f'{head}:p0'
            else:
                pk = head
        parent_text = parents.get(pk)
        if parent_text:
            it['child_snippet'] = it.get('snippet', '')
            it['snippet'] = parent_text
            it['parent_expanded'] = True
        out.append(it)
    return out
