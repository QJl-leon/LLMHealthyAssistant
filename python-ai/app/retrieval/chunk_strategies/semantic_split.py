from __future__ import annotations
import logging
import os
from app.retrieval.chunk_strategies.base import _SENT_BOUNDARY, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP
from app.retrieval.chunk_strategies.sliding_window import chunk_sliding_window
logger = logging.getLogger(__name__)
SEMANTIC_BREAK_THRESHOLD = float(os.getenv('SEMANTIC_BREAK_THRESHOLD', '0.55'))
SEMANTIC_MIN_FILL = float(os.getenv('SEMANTIC_MIN_FILL', '0.35'))

def _cosine(a, b) -> float:
    import math
    dot = sum((x * y for x, y in zip(a, b)))
    na = math.sqrt(sum((x * x for x in a)))
    nb = math.sqrt(sum((y * y for y in b)))
    if na == 0.0 or nb == 0.0:
        return 1.0
    return dot / (na * nb)

def chunk_semantic_by_similarity(text: str, *, embed_fn, threshold: float=SEMANTIC_BREAK_THRESHOLD, chunk_size: int=DEFAULT_CHUNK_SIZE, overlap: int=DEFAULT_OVERLAP, min_fill: float=SEMANTIC_MIN_FILL) -> list[str]:
    text = (text or '').strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    segments = [s.strip() for s in _SENT_BOUNDARY.split(text) if s.strip()]
    if len(segments) <= 1:
        return chunk_sliding_window(text, chunk_size=chunk_size, overlap=overlap)
    try:
        vectors = embed_fn(segments)
    except Exception as e:
        logger.warning('[Chunker] 语义切分 embedding 失败，回退窗口切分: %s', e)
        return chunk_sliding_window(text, chunk_size=chunk_size, overlap=overlap)
    if not vectors or len(vectors) != len(segments):
        logger.warning('[Chunker] 语义切分向量数不符，回退窗口切分（期望 %d 实际 %s）', len(segments), None if not vectors else len(vectors))
        return chunk_sliding_window(text, chunk_size=chunk_size, overlap=overlap)
    boundaries = {i for i in range(1, len(segments)) if _cosine(vectors[i - 1], vectors[i]) < threshold}
    chunks: list[str] = []
    buf = ''
    for i, seg in enumerate(segments):
        boundary = i in boundaries
        if buf and (boundary and len(buf) >= chunk_size * min_fill or len(buf) + len(seg) > chunk_size):
            chunks.append(buf)
            tail = buf[-overlap:] if overlap > 0 else ''
            candidate = tail + seg
            buf = candidate if len(candidate) <= chunk_size else seg
        else:
            buf = f'{buf}{seg}' if buf else seg
    if buf:
        chunks.append(buf)
    return chunks
