from __future__ import annotations
import logging
import os
from dataclasses import dataclass
from app.context.compaction import estimate_tokens
logger = logging.getLogger(__name__)
MODEL_CONTEXT_WINDOW = int(os.getenv('MODEL_CONTEXT_WINDOW', '64000'))
OUTPUT_RESERVE_TOKENS = int(os.getenv('OUTPUT_RESERVE_TOKENS', '4096'))
EVIDENCE_BUDGET_RATIO = float(os.getenv('EVIDENCE_BUDGET_RATIO', '0.5'))
PER_ITEM_CHARS = int(os.getenv('EVIDENCE_PER_ITEM_CHARS', '200'))
PER_ITEM_CHARS_MAX = int(os.getenv('EVIDENCE_PER_ITEM_CHARS_MAX', '400'))
_PER_ITEM_OVERHEAD_CHARS = 120

@dataclass
class EvidenceBudget:
    total_tokens: int
    max_items: int
    per_item_chars: int
    reason: str

def allocate_evidence_budget(*, system_prompt_tokens: int, metrics_tokens: int, trend_tokens: int, profile_tokens: int, evidence_count: int, model_window: int=MODEL_CONTEXT_WINDOW, output_reserve: int=OUTPUT_RESERVE_TOKENS) -> EvidenceBudget:
    occupied = system_prompt_tokens + metrics_tokens + trend_tokens + profile_tokens
    available = model_window - occupied - output_reserve
    budget = max(0, min(int(available * EVIDENCE_BUDGET_RATIO), available))
    if budget <= 0 or evidence_count == 0:
        return EvidenceBudget(total_tokens=0, max_items=0, per_item_chars=PER_ITEM_CHARS, reason='无可用预算')

    def _fits(per_item_chars: int) -> int:
        per_tokens = int((per_item_chars + _PER_ITEM_OVERHEAD_CHARS) / 1.5) + 1
        return min(evidence_count, budget // per_tokens)
    max_items = _fits(PER_ITEM_CHARS)
    per_item = PER_ITEM_CHARS
    reason = f'预算 {budget} tokens，默认单条 {PER_ITEM_CHARS} 字符 → {max_items} 条'
    if max_items >= evidence_count:
        per_item = PER_ITEM_CHARS_MAX
        max_items = _fits(per_item)
        reason = f'预算宽裕（{budget} tokens ≥ 全部 {evidence_count} 条），单条放宽到 {per_item} 字符'
    logger.info('[Budget] %s', reason)
    return EvidenceBudget(total_tokens=budget, max_items=max_items, per_item_chars=per_item, reason=reason)

def build_evidence_text_with_budget(evidence: list[dict], budget: EvidenceBudget) -> str:
    if budget.max_items <= 0:
        return '（无证据预算）'
    lines = []
    for i, e in enumerate(evidence[:budget.max_items]):
        lines.append(f"- [{i + 1}] {str(e.get('quote') or '')[:budget.per_item_chars]} | 来源: {e.get('source_name', '')} | 类型: {e.get('evidence_type') or e.get('channel', '')} | 编号: {e.get('evidence_id', '')} | URL: {e.get('source_url', '')}")
    return '\n'.join(lines)
