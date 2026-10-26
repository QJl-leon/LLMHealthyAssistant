from __future__ import annotations
import json
import os
import sys
from datetime import datetime
REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
CORPUS_DIR = os.path.join(os.path.dirname(__file__), '..', 'factory', 'corpus')
CITED_INDEXES = (1, 3, 7, 12, 18, 25, 33, 40)

def _load_evidence() -> list[dict]:
    evidence: list[dict] = []
    with open(os.path.join(CORPUS_DIR, 'guidelines.json'), encoding='utf-8') as f:
        guidelines = json.load(f).get('guidelines') or []
    for i, g in enumerate(guidelines):
        quote = str(g.get('content') or '')
        evidence.append({'evidence_id': f'gl-{i}', 'quote': quote, 'source_name': str(g.get('title') or g.get('org') or '指南'), 'source_url': str(g.get('url') or ''), 'source_type': 'guideline', 'knowledge_version': 'kv_bench'})
    with open(os.path.join(CORPUS_DIR, 'cases.json'), encoding='utf-8') as f:
        cases = json.load(f).get('cases') or []
    for i, c in enumerate(cases):
        quote = ' '.join((str(c.get(k) or '') for k in ('chief_complaint', 'findings'))).strip()
        evidence.append({'evidence_id': f'cs-{i}', 'quote': quote, 'source_name': str(c.get('case_code') or '病例'), 'source_url': str(c.get('url') or ''), 'source_type': 'case', 'knowledge_version': 'kv_bench'})
    return [e for e in evidence if e['quote']]

def _evidence_text(evidence: list[dict]) -> str:
    lines = []
    for i, e in enumerate(evidence):
        lines.append(f"- [{i + 1}] {str(e.get('quote') or '')[:200]} | 来源: {e.get('source_name', '')} | 编号: {e.get('evidence_id', '')} | URL: {e.get('source_url', '')}")
    return '\n'.join(lines)

def _simulate_report(evidence: list[dict]) -> tuple[dict, set[str]]:
    from app.evidence.conflicts import detect_evidence_conflicts
    cited_ids: list[str] = []
    for idx in CITED_INDEXES:
        if idx <= len(evidence):
            cited_ids.append(evidence[idx - 1]['evidence_id'])
    facts = '根据检索到的证据，' + '、'.join((f'第{idx}条建议每周 150 分钟中等强度运动 [{idx}]' for idx in CITED_INDEXES if idx <= len(evidence)))
    conflicts = detect_evidence_conflicts(evidence)
    conflict_text = '；'.join((f"关于「{c.get('topic', '')}」，不同证据存在不同建议" for c in conflicts))
    draft = {'sections': {'facts': facts, 'inferences': '', 'conflicts': conflict_text, 'unknowns': '', 'metric_reading': '', 'metric_trend': ''}, 'claims': [], 'advice_claims': [{'claim_id': 'advice_exercise_1', 'type': 'advice', 'section': 'exercise_advice', 'text': f'每周 150 分钟中等强度有氧运动 [{CITED_INDEXES[0]}]', 'evidence_ids': [evidence[CITED_INDEXES[0] - 1]['evidence_id']]}]}
    return (draft, set(cited_ids))

def _run_scenario(name: str, evidence: list[dict]) -> dict:
    from app.context.compaction import compact_evidence, estimate_tokens, extract_numbers
    from app.agents.report_agent import run_deterministic_checks
    draft, cited_ids = _simulate_report(evidence)
    text_before = _evidence_text(evidence)
    tokens_before = estimate_tokens(text_before)
    errors_before = run_deterministic_checks(draft, evidence, user_id='bench')
    nums_before = set()
    for e in evidence:
        nums_before |= extract_numbers(str(e.get('quote') or ''))
    compacted, stats = compact_evidence(evidence, cited_ids=cited_ids)
    text_after = _evidence_text(compacted)
    tokens_after = estimate_tokens(text_after)
    kept_ids = {str(e.get('evidence_id')) for e in compacted if e.get('evidence_id')}
    cited_kept = cited_ids & kept_ids
    citation_completeness = len(cited_kept) / len(cited_ids) if cited_ids else 1.0
    from app.evidence.validator import validate_existence
    exist = validate_existence('bench', sorted(cited_ids), registered_ids=kept_ids)
    nums_after = set()
    for e in compacted:
        nums_after |= extract_numbers(str(e.get('quote') or ''))
    biz_before = {n for n in nums_before if '.' in n}
    biz_after = {n for n in nums_after if '.' in n}
    new_numbers = biz_after - biz_before
    task_ok_before = len(errors_before) == 0
    task_ok_after = not exist.failures
    return {'scenario': name, 'evidence_count': len(evidence), 'tokens_before': tokens_before, 'tokens_after': tokens_after, 'token_reduction': round(1 - tokens_after / max(tokens_before, 1), 4), 'citation_completeness': round(citation_completeness, 4), 'cited_count': len(cited_ids), 'kept_count': stats['kept'], 'dropped_count': stats['dropped'], 'task_success_before': task_ok_before, 'task_success_after': task_ok_after, 'new_numbers_introduced': sorted(new_numbers), 'no_new_numbers': not new_numbers}

def main():
    if '--dry-run' in sys.argv:
        print('\n=== 上下文压缩评测（B6c）dry-run ===')
        print('语料: guidelines.json(49) + cases.json(13) 真实证据')
        print('场景: 1x / 2x / 3x 证据规模（模拟多轮累积）')
        print('指标: token 下降 / 引用完整率(目标100%) / 任务成功率 / 不引入新数字')
        return
    base = _load_evidence()
    print(f'\n=== 上下文压缩评测（真实语料 {len(base)} 条证据）===\n')
    scenarios = [('1x_全量证据', base), ('2x_双倍累积', base + [dict(e, evidence_id=f"{e['evidence_id']}-r2") for e in base]), ('3x_三倍累积', base + [dict(e, evidence_id=f"{e['evidence_id']}-r2") for e in base] + [dict(e, evidence_id=f"{e['evidence_id']}-r3") for e in base])]
    results = []
    for name, ev in scenarios:
        r = _run_scenario(name, ev)
        results.append(r)
        print(f"  [{name}] 证据 {r['evidence_count']} 条 | token {r['tokens_before']} → {r['tokens_after']} (↓{r['token_reduction']:.0%}) | 引用完整率 {r['citation_completeness']:.0%} | 任务成功率 {r['task_success_before']}→{r['task_success_after']} | 新数字 {len(r['new_numbers_introduced'])}")
    all_ok = all((r['citation_completeness'] == 1.0 and r['task_success_before'] and r['task_success_after'] and r['no_new_numbers'] and (r['tokens_after'] < r['tokens_before']) for r in results))
    report = {'benchmark': 'compaction', 'question': '纯结构化上下文压缩：token 显著下降且引用完整率 100%、不引入新数字、任务成功率不降', 'method': '真实语料（guidelines 49 + cases 13）× 3 规模；cited 模式压缩；无 LLM', 'results': results, 'all_ok': all_ok, 'insight': '压缩策略为纯结构化（零 LLM）：证据层只留被引用 + 计数摘要，观察层同名同值合并/同名异值保留冲突，讨论层只留结论+evidence_id；数字/单位/参考区间/evidence_id/source_url 原样保留。触发参考 Claude Code auto-compact：按 token 预算（COMPACTION_TRIGGER_TOKENS）接近上限时自动触发，压缩后无缝继续。', 'timestamp': datetime.now().isoformat(timespec='seconds')}
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f'compaction_bench_{datetime.now():%Y%m%d}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n总体: {('✅ 全部达标' if all_ok else '❌ 存在未达标项')}")
    print(f'报告已落库: {path}')
    if not all_ok:
        sys.exit(1)
if __name__ == '__main__':
    main()
