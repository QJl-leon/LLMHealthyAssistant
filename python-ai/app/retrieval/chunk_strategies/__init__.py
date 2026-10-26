from __future__ import annotations
import os
from typing import Callable
from app.retrieval.chunk_strategies.base import DEFAULT_CHUNK_SIZE, DEFAULT_OVERLAP, Chunk
from app.retrieval.chunk_strategies.evidence_row import EVIDENCE_SOURCE_TYPES, is_evidence_row, naturalize_case_row, naturalize_content, naturalize_guideline_row, naturalize_metric_row
from app.retrieval.chunk_strategies.fixed_length import chunk_fixed_length
from app.retrieval.chunk_strategies.fixed_symbol import chunk_fixed_symbol
from app.retrieval.chunk_strategies.parent_child import PARENT_MAX_CHARS, PARENT_MIN_CHARS, build_parent_child_chunks, expand_to_parent
from app.retrieval.chunk_strategies.semantic_split import SEMANTIC_BREAK_THRESHOLD, SEMANTIC_MIN_FILL, chunk_semantic_by_similarity
from app.retrieval.chunk_strategies.sliding_window import chunk_sliding_window
TEXT_STRATEGIES: dict[str, Callable] = {'fixed_length': chunk_fixed_length, 'fixed_symbol': chunk_fixed_symbol, 'semantic_window': chunk_sliding_window, 'semantic_split': chunk_semantic_by_similarity}

def resolve_text_strategy(strategy: str='auto', embed_fn=None) -> tuple[Callable, str]:
    if strategy and strategy != 'auto':
        name = strategy.strip().lower()
    else:
        name = (os.getenv('CHUNK_STRATEGY', '') or '').strip().lower() or 'auto'
    if name == 'auto':
        name = 'semantic_split' if embed_fn is not None else 'semantic_window'
    text_fn = TEXT_STRATEGIES.get(name)
    if text_fn is None:
        raise ValueError(f"未知 chunk 策略 {strategy!r}（env CHUNK_STRATEGY={os.getenv('CHUNK_STRATEGY', '')!r}）；可选: auto | {' | '.join(TEXT_STRATEGIES)}")
    if name == 'semantic_split' and embed_fn is None:
        return (chunk_sliding_window, 'semantic_window')
    return (text_fn, name)
__all__ = ['TEXT_STRATEGIES', 'resolve_text_strategy', 'Chunk', 'DEFAULT_CHUNK_SIZE', 'DEFAULT_OVERLAP', 'EVIDENCE_SOURCE_TYPES', 'is_evidence_row', 'naturalize_content', 'naturalize_metric_row', 'naturalize_guideline_row', 'naturalize_case_row', 'chunk_fixed_length', 'chunk_fixed_symbol', 'chunk_sliding_window', 'chunk_semantic_by_similarity', 'SEMANTIC_BREAK_THRESHOLD', 'SEMANTIC_MIN_FILL', 'build_parent_child_chunks', 'expand_to_parent', 'PARENT_MIN_CHARS', 'PARENT_MAX_CHARS']
