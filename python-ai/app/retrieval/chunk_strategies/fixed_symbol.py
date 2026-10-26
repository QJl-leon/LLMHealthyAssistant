from __future__ import annotations
from app.retrieval.chunk_strategies.base import DEFAULT_CHUNK_SIZE
DEFAULT_SYMBOLS = ('\n\n', '\n', '。', '！', '？', '；')

def _split_piece(piece: str, sym: str) -> list[str]:
    if not piece.strip():
        return []
    parts = piece.split(sym)
    head = [p + sym for p in parts[:-1] if p.strip()]
    tail = [parts[-1]] if parts[-1].strip() else []
    return head + tail

def chunk_fixed_symbol(text: str, *, chunk_size: int=DEFAULT_CHUNK_SIZE, symbols: tuple[str, ...]=DEFAULT_SYMBOLS, overlap: int=0, embed_fn=None) -> list[str]:
    text = (text or '').strip()
    if not text:
        return []
    if len(text) <= chunk_size:
        return [text]
    pieces = [text]
    for sym in symbols:
        if all((len(p) <= chunk_size for p in pieces)):
            break
        pieces = [q for p in pieces for q in _split_piece(p, sym)]
    chunks: list[str] = []
    buf = ''
    for p in pieces:
        if len(buf) + len(p) <= chunk_size:
            buf += p
        else:
            if buf:
                chunks.append(buf)
            buf = p
    if buf:
        chunks.append(buf)
    return chunks
