from __future__ import annotations
import logging
import os
from typing import Any
from app.retrieval.chunk_strategies import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP, PARENT_MAX_CHARS, PARENT_MIN_CHARS, Chunk, is_evidence_row, naturalize_content, resolve_text_strategy
from app.retrieval.chunk_strategies.base import _field, _page_of
logger = logging.getLogger(__name__)

def build_chunks(parsed_docs: list[dict | Any], *, strategy: str='auto', chunk_size: int=DEFAULT_CHUNK_SIZE, overlap: int=DEFAULT_OVERLAP, embed_fn=None) -> list[Chunk]:
    chunks: list[Chunk] = []
    text_fn, piece_strategy = resolve_text_strategy('auto' if strategy == 'evidence_row' else strategy, embed_fn)
    for doc in parsed_docs:
        if hasattr(doc, 'content'):
            content = doc.content
            doc_id = str(getattr(doc, 'id', ''))
            source_id = str(getattr(doc, 'source_id', ''))
            source_level = int(getattr(doc, 'source_level', 1) or 1)
            kv = str(getattr(doc, 'knowledge_version', '') or '')
        else:
            content = doc.get('content', {})
            doc_id = str(doc.get('id', ''))
            source_id = str(doc.get('source_id', ''))
            source_level = int(doc.get('source_level', 1) or 1)
            kv = str(doc.get('knowledge_version', '') or '')
        source_type = (_field(content, 'source_type') or _field(content, 'kind')).lower() if isinstance(content, dict) else ''
        page = _page_of(content)
        if strategy == 'evidence_row' or (strategy == 'auto' and is_evidence_row(content)):
            text = naturalize_content(content)
            if text:
                metadata = dict(content) if isinstance(content, dict) else {}
                metadata['source_type'] = source_type
                chunks.append(Chunk(text=text, doc_id=doc_id, source_id=source_id, source_type=source_type, source_level=source_level, knowledge_version=kv, page=page, strategy='evidence_row', chunk_index=len(chunks), metadata=metadata))
            continue
        text = naturalize_content(content)
        pieces = text_fn(text, embed_fn=embed_fn, chunk_size=chunk_size, overlap=overlap)
        for i, piece in enumerate(pieces):
            chunks.append(Chunk(text=piece, doc_id=doc_id, source_id=source_id, source_type=source_type, source_level=source_level, knowledge_version=kv, page=page, strategy=piece_strategy, chunk_index=i, metadata={}))
    return chunks

def build_index_chunks(parsed_docs: list[dict | Any], *, strategy: str='auto', embed_fn=None, use_parent_child: bool=True, chunk_size: int=DEFAULT_CHUNK_SIZE, overlap: int=DEFAULT_OVERLAP, parent_min_chars: int=PARENT_MIN_CHARS, parent_max_chars: int=PARENT_MAX_CHARS) -> tuple[list[Chunk], dict[str, str]]:
    out: list[Chunk] = []
    parents: dict[str, str] = {}
    if not use_parent_child:
        return (build_chunks(parsed_docs, strategy=strategy, chunk_size=chunk_size, overlap=overlap, embed_fn=embed_fn), {})
    items: list[dict] = []
    for idx, doc in enumerate(parsed_docs):
        if hasattr(doc, 'content'):
            content = doc.content
            doc_id = str(getattr(doc, 'id', '') or f'doc_{idx}')
            source_id = str(getattr(doc, 'source_id', '') or '')
            source_level = int(getattr(doc, 'source_level', 1) or 1)
            kv = str(getattr(doc, 'knowledge_version', '') or '')
        else:
            content = doc.get('content', {})
            doc_id = str(doc.get('id', '') or f'doc_{idx}')
            source_id = str(doc.get('source_id', '') or '')
            source_level = int(doc.get('source_level', 1) or 1)
            kv = str(doc.get('knowledge_version', '') or '')
        text = naturalize_content(content)
        if not text:
            continue
        source_type = (_field(content, 'source_type') or _field(content, 'kind')).lower() if isinstance(content, dict) else ''
        meta = dict(content) if isinstance(content, dict) else {}
        meta['source_type'] = source_type
        items.append({'doc_id': doc_id, 'source_id': source_id, 'text': text, 'source_type': source_type, 'source_level': source_level, 'knowledge_version': kv, 'page': _page_of(content), 'meta': meta, 'is_evidence': is_evidence_row(content)})
    groups: dict[str, list[dict]] = {}
    for it in items:
        groups.setdefault(it['source_id'] or it['doc_id'], []).append(it)
    text_fn, piece_strategy = resolve_text_strategy('auto' if strategy == 'evidence_row' else strategy, embed_fn)
    for gkey, members in groups.items():
        group_text = ''.join((m['text'] for m in members))
        parent_key = ''
        if len(group_text) > parent_min_chars:
            parent_key = f'{gkey}:p0'
            parents[parent_key] = group_text[:parent_max_chars]
            head = members[0]
            out.append(Chunk(text=parents[parent_key], doc_id=gkey, source_id=head['source_id'], source_type=head['source_type'], source_level=head['source_level'], knowledge_version=head['knowledge_version'], page=head['page'], strategy='parent', chunk_index=0, role='parent', parent_key=parent_key, metadata=head['meta']))
        for m in members:
            common = dict(doc_id=m['doc_id'], source_id=m['source_id'], source_type=m['source_type'], source_level=m['source_level'], knowledge_version=m['knowledge_version'], page=m['page'])
            if len(m['text']) <= chunk_size:
                out.append(Chunk(text=m['text'], strategy='evidence_row' if m['is_evidence'] else 'parent_as_child', chunk_index=0, role='child', parent_key=parent_key, metadata=m['meta'], **common))
                continue
            pieces = text_fn(m['text'], embed_fn=embed_fn, chunk_size=chunk_size, overlap=overlap)
            for i, piece in enumerate(pieces):
                out.append(Chunk(text=piece, strategy=piece_strategy, chunk_index=i, role='child', parent_key=parent_key, metadata=m['meta'], **common))
    return (out, parents)

def chunks_to_index_rows(chunks: list[Chunk], *, tenant_id: str='dev-tenant', embedding_provider=None, dim: int=1024) -> list[dict]:
    rows = []
    embed_model = os.getenv('EMBEDDING_MODEL', 'BAAI/bge-m3')
    for c in chunks:
        rows.append({'id': c.index_key, 'doc_id': c.source_id or c.doc_id, 'tenant_id': tenant_id, 'source_level': c.source_level, 'knowledge_version': c.knowledge_version, 'chunk_role': c.role, 'parent_key': c.parent_key[:64], 'embedding_model': embed_model[:64], 'embedding_dim': int(dim or 0), 'text': c.text[:8192], 'embedding': None, 'sparse_vector': {}})
    if embedding_provider is not None:
        batch = []
        for r in rows:
            batch.append(r['text'] if r['text'].strip() else ' ')
        try:
            vectors = embedding_provider(batch)
            for r, vec in zip(rows, vectors):
                r['embedding'] = vec
        except Exception as e:
            logger.warning('[Chunker] Embedding 生成失败，置零向量: %s', e)
    for r in rows:
        if r['embedding'] is None:
            r['embedding'] = [0.0] * dim
    return rows
