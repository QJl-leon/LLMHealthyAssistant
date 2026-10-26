from __future__ import annotations
from app.retrieval.chunk_strategies.base import _SENT_BOUNDARY, DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP

def chunk_sliding_window(text: str, *, chunk_size: int=DEFAULT_CHUNK_SIZE, overlap: int=DEFAULT_OVERLAP, embed_fn=None) -> list[str]:
    if overlap >= chunk_size:
        raise ValueError(f'overlap({overlap}) 必须小于 chunk_size({chunk_size})')
    text = (text or '').strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    segments = [s for s in _SENT_BOUNDARY.split(text) if s.strip()]
    if not segments:
        segments = [text]
    chunks: list[str] = []
    buf = ''
    for seg in segments:
        seg = seg.strip()
        if not seg:
            continue
        if len(buf) + len(seg) <= chunk_size:
            buf = f'{buf}{seg}' if buf else seg
            continue
        tail = buf[-overlap:] if buf and overlap > 0 else ''
        if buf:
            chunks.append(buf)
        if len(seg) > chunk_size:
            i = 0
            while i < len(seg):
                piece = seg[i:i + chunk_size]
                chunks.append(piece)
                i += chunk_size - overlap
            buf = ''
        else:
            candidate = tail + seg
            buf = candidate if len(candidate) <= chunk_size else seg
    if buf:
        chunks.append(buf)
    return chunks
