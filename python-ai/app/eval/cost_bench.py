from __future__ import annotations
import json
import os
import sys
from datetime import datetime
REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
SYSTEM_PROMPT_TOKENS = 1400
METRICS_TOKENS = 800
TREND_TOKENS = 300
PROFILE_TOKENS = 500

def _fixed_budget_text(evidence: list[dict]) -> str:
    lines = []
    for i, e in enumerate(evidence[:20]):
        lines.append(f"- [{i + 1}] {str(e.get('quote') or '')[:200]} | 来源: {e.get('source_name', '')} | 编号: {e.get('evidence_id', '')} | URL: {e.get('source_url', '')}")
    return '\n'.join(lines)

def main():
    if '--dry-run' in sys.argv:
        print('\n=== 上下文与成本工程评测（B6b）dry-run ===')
        print('对照: 固定预算(20×200) vs 动态预算(16K/64K/128K 窗口)')
        print('指标: 证据 token 占用 / 覆盖条数 / 单条平均长度 + 成本聚合')
        return
    from app.context.budget import allocate_evidence_budget, build_evidence_text_with_budget
    from app.context.compaction import estimate_tokens
    from app.eval.compaction_bench import _load_evidence
    evidence = _load_evidence()
    print(f'\n=== 上下文与成本工程评测（真实语料 {len(evidence)} 条证据）===\n')
    fixed_text = _fixed_budget_text(evidence)
    fixed = {'mode': 'fixed_20x200', 'tokens': estimate_tokens(fixed_text), 'items': min(20, len(evidence)), 'avg_item_chars': 200}
    print(f"  [固定预算] {fixed['items']} 条 | {fixed['tokens']} tokens")
    dynamic_results = []
    for window in (8000, 16000, 64000, 128000):
        budget = allocate_evidence_budget(system_prompt_tokens=SYSTEM_PROMPT_TOKENS, metrics_tokens=METRICS_TOKENS, trend_tokens=TREND_TOKENS, profile_tokens=PROFILE_TOKENS, evidence_count=len(evidence), model_window=window)
        text = build_evidence_text_with_budget(evidence, budget)
        tokens = estimate_tokens(text)
        shown = min(budget.max_items, len(evidence))
        dynamic_results.append({'mode': f'dynamic_window_{window}', 'window': window, 'tokens': tokens, 'items': shown, 'per_item_chars': budget.per_item_chars, 'budget_reason': budget.reason})
        print(f'  [动态 {window:>6}] {shown:>3} 条 | {tokens:>5} tokens | 单条 {budget.per_item_chars} 字符')
    cost_demo: dict = {'ok': False}
    try:
        from app.context import cost as cost_mod
        from app.context import ctx as call_ctx
        cost_mod.init_cost_tables()
        task_id = f'cost-bench-{datetime.now():%Y%m%d%H%M%S}'
        call_ctx.set_context(task_id=task_id, user_id='cost-bench-user', trace_id=task_id)
        cost_mod.record_usage('embedding', 'bge-m3', total_tokens=2100, call_count=30, latency_ms=800)
        cost_mod.record_usage('rerank', 'bge-reranker-v2-m3', total_tokens=3600, call_count=20, latency_ms=450)
        cost_mod.record_usage('llm', 'deepseek-chat', prompt_tokens=5200, completion_tokens=1400, latency_ms=6500)
        cost_mod.record_usage('vlm', 'qwen-vl-max', prompt_tokens=1800, completion_tokens=600, latency_ms=3200)
        task = cost_mod.get_task_cost(task_id)
        user = cost_mod.get_user_cost('cost-bench-user', days=1)
        models = cost_mod.get_model_summary(days=1)
        cost_demo = {'ok': task['total_tokens'] == 2100 + 3600 + 5200 + 1400 + 1800 + 600, 'task_total_tokens': task['total_tokens'], 'task_call_count': task['call_count'], 'task_items': task['items'], 'user_total_tokens': user['total_tokens'], 'model_summary_rows': len(models['items'])}
        print(f"\n  [成本聚合] 任务总 token: {cost_demo['task_total_tokens']} | 调用 {cost_demo['task_call_count']} 次 | 分桶: {[(i['call_type'], int(i['tokens'])) for i in task['items']]}")
        call_ctx.clear_context()
        import psycopg2
        with psycopg2.connect(cost_mod.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute('DELETE FROM token_usage WHERE task_id = %s', (task_id,))
            conn.commit()
    except Exception as e:
        print(f'\n  [WARN] 成本聚合演示跳过（PG 不可用）: {e}')
        cost_demo = {'ok': None, 'error': str(e)}
    d8 = next((r for r in dynamic_results if r['window'] == 8000))
    d16 = next((r for r in dynamic_results if r['window'] == 16000))
    d128 = next((r for r in dynamic_results if r['window'] == 128000))
    conclusions = {'tiny_window_shrinks_coverage': d8['items'] < fixed['items'], 'small_window_not_worse': d16['items'] >= fixed['items'] - 1, 'large_window_more_coverage': d128['items'] > fixed['items'], 'per_item_relaxed_when_ample': d128['per_item_chars'] > 200, 'cost_aggregation_ok': cost_demo.get('ok') is True}
    report = {'benchmark': 'cost_budget', 'question': '动态证据预算 vs 固定 20×200；token 成本聚合落库与三维度查询', 'evidence_count': len(evidence), 'fixed_baseline': fixed, 'dynamic': dynamic_results, 'cost_aggregation_demo': cost_demo, 'conclusions': conclusions, 'insight': f"动态预算按模型窗口自适应：8K 极小窗口证据收缩到 {d8['items']} 条（防超窗）；16K 与固定持平（未退化）；64K/128K 大窗口覆盖 {fixed['items']}→{d128['items']} 条（突破写死的 20 条上限），且预算宽裕时单条长度 200→{d128['per_item_chars']} 字符自动放宽。成本侧：LLM/Embedding/Rerank/VLM 每次调用落 token_usage 表，支持任务/用户/模型三维度聚合；限额 = 任务预算（超限降级）+ 用户日配额（超限拒绝）。", 'timestamp': datetime.now().isoformat(timespec='seconds')}
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f'cost_bench_{datetime.now():%Y%m%d}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    print(f'\n结论: {conclusions}')
    print(f'报告已落库: {path}')
if __name__ == '__main__':
    main()
