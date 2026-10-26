from __future__ import annotations
from app.retrieval.chunk_strategies.base import DEFAULT_CHUNK_SIZE

def chunk_fixed_length(text: str, *, chunk_size: int=DEFAULT_CHUNK_SIZE, overlap: int=0, embed_fn=None) -> list[str]:
    if overlap >= chunk_size:
        raise ValueError(f'overlap({overlap}) 必须小于 chunk_size({chunk_size})')
    text = (text or '').strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    pieces: list[str] = []
    step = chunk_size - overlap
    i = 0
    while i < len(text):
        piece = text[i:i + chunk_size]
        if pieces and len(piece) <= overlap:
            break
        pieces.append(piece)
        i += step
    return pieces
