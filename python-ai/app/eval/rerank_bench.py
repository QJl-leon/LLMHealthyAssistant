from __future__ import annotations
import json
import argparse
import math
import os
import sys
import time
from datetime import datetime
REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
RERANK_TOP_K = 100
KNOWLEDGE_VERSION = os.getenv('RERANK_BENCH_KNOWLEDGE_VERSION') or None
SOURCE_TYPES = ['guideline', 'case', 'metric_catalog']
FINAL_TOP_K = 10
BENCH_PROVIDER = None
CASES = [{'query': '体检报告血脂那几个箭头怎么办', 'topic': '血脂'}, {'query': '血糖高的人怎样锻炼比较好', 'topic': '血糖'}, {'query': '血压有点高适合什么运动', 'topic': '血压'}, {'query': '尿酸偏高平时能不能运动', 'topic': '尿酸'}, {'query': '体检查出脂肪肝怎么运动', 'topic': '脂肪肝'}, {'query': '体重超标想减重怎么安排运动', 'topic': '体重'}]

def _is_rel(text: str, case: dict) -> bool:
    topic = case.get('topic', '')
    return bool(topic) and topic in text

def _ndcg(ranked: list[str], rel: set[str], k: int) -> float:
    dcg = sum((1.0 / math.log2(i + 2) for i, d in enumerate(ranked[:k]) if d in rel))
    idcg = sum((1.0 / math.log2(i + 2) for i in range(min(k, len(rel)))))
    return dcg / idcg if idcg else 0.0

def _metrics(ranked: list[str], rel: set[str]) -> dict:
    top = ranked[:FINAL_TOP_K]
    n_rel = sum((1 for d in top if d in rel))
    return {f'recall@{FINAL_TOP_K}': round(n_rel / max(len(rel), 1), 3), f'precision@{FINAL_TOP_K}': round(n_rel / max(FINAL_TOP_K, 1), 3), 'mrr': round(next((1.0 / (i + 1) for i, d in enumerate(top) if d in rel), 0.0), 3), 'hit@1': 1.0 if ranked and ranked[0] in rel else 0.0, f'ndcg@{FINAL_TOP_K}': round(_ndcg(ranked, rel, FINAL_TOP_K), 3)}

def _rough_rerank(query: str, candidates: list[dict]) -> list[str]:
    from app.gateway.adapters.reranker import RerankerAdapter
    docs = [c['text'] for c in candidates]
    reranked = RerankerAdapter(provider=BENCH_PROVIDER).rerank(query, docs, top_k=FINAL_TOP_K)
    indices = [r['index'] for r in reranked]
    if len(indices) != min(FINAL_TOP_K, len(candidates)) or len(indices) != len(set(indices)):
        raise RuntimeError('rerank 返回数量不符或存在重复索引')
    if any(not isinstance(i, int) or not 0 <= i < len(candidates) for i in indices):
        raise RuntimeError('rerank 返回无效文档索引')
    return [candidates[i]['doc_id'] for i in indices]

def _retrieve_candidates(query: str, mode: str='bm25', top_k: int=RERANK_TOP_K) -> list[dict]:
    from app.retrieval.channels import search_bm25, search_dense, fuse_and_rerank
    if mode in ('rrf', 'rrf_fusion'):
        results = []
        r1 = search_bm25(query, top_k=top_k, knowledge_version=KNOWLEDGE_VERSION, source_types=SOURCE_TYPES)
        if r1.snippets:
            results.append(r1)
        r2 = search_dense(f'{query} 健康指标 运动干预 建议', top_k=top_k, knowledge_version=KNOWLEDGE_VERSION, source_types=SOURCE_TYPES)
        if r2.snippets:
            results.append(r2)
        if not results:
            return []
        fused = fuse_and_rerank(results, query, top_k=top_k, rrf_k=int(os.getenv('RERANK_BENCH_RRF_K', '60')), expand_parents=False, rerank_enabled=False, channel_weights={})
        return [{'doc_id': row.get('doc_id', ''), 'text': str(row.get('snippet', ''))} for row in fused]
    if mode not in ('bm25', 'bm25_only'):
        raise ValueError(f'未知粗排模式: {mode}')
    r = search_bm25(query, top_k=top_k, knowledge_version=KNOWLEDGE_VERSION, source_types=SOURCE_TYPES)
    return [{'doc_id': did, 'text': sn} for did, sn in zip(r.doc_ids, r.snippets)]

def main():
    global BENCH_PROVIDER
    parser = argparse.ArgumentParser(description='Rerank 精排前后对比')
    parser.add_argument('--provider', choices=['jina', 'qwen', 'siliconflow'])
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--json', action='store_true')
    parser.add_argument('--evidence-labels', help='答案证据标注JSON；同一结果同时按新旧标签评测')
    parser.add_argument('--output', help='结果JSON路径，避免覆盖历史报告')
    args = parser.parse_args()
    BENCH_PROVIDER = args.provider
    dry = args.dry_run
    from app.gateway.adapters.reranker import RerankerAdapter
    adapter = RerankerAdapter(provider=BENCH_PROVIDER)
    api_key = adapter.api_key
    actual_model = adapter.model
    key_name = adapter.key_name
    adapter.client.close()
    evidence = None
    if args.evidence_labels:
        from app.eval.evidence_labels import EvidenceLabels
        evidence = EvidenceLabels(args.evidence_labels, KNOWLEDGE_VERSION)
    if dry or not api_key:
        print('\n=== Rerank 精排前后对比（亮点6）===')
        if not api_key:
            print(f'{key_name} 未配置 → dry-run（仅预览流程）')
        print(f'粗排组A: 纯 BM25 全文检索 top{RERANK_TOP_K}（词匹配弱粗排，rerank 价值场景）')
        print(f'粗排组B: BM25 + Dense + RRF 融合 top{RERANK_TOP_K}（完整管线对照）')
        print(f'精排: {actual_model} → top{FINAL_TOP_K}')
        print(f'查询: {len(CASES)} 条口语查询（均包含主题词）')
        print(f'对比: 精排前 vs 精排后 的 Recall/Precision/MRR@10/Hit@1/NDCG 与延迟')
        if evidence:
            print(f'双标注: 旧主题词标签 vs 新答案证据标签；标注状态={evidence.data["review_status"]}')
        print(f'\n配置 {key_name} 后重跑即可得到真实对比数据（Dense 召回仍需 SILICONFLOW_API_KEY）。')
        return
    print('\n=== Rerank 精排前后对比（亮点6）真实模式 ===\n')
    modes = [('bm25_only', 'BM25-only 粗排（词匹配）'), ('rrf_fusion', 'RRF 融合粗排（BM25+Dense）')]
    all_per: dict[str, list] = {m[0]: [] for m in modes}
    all_metrics: dict[str, dict] = {}
    skipped = []
    for mode, label in modes:
        pre_sum: dict[str, float] = {}
        post_sum: dict[str, float] = {}
        n = 0
        print(f'── [{label}] ──')
        for case in CASES:
            query = case['query']
            retrieval_start = time.perf_counter()
            cands = _retrieve_candidates(query, mode=mode)
            retrieval_ms = (time.perf_counter() - retrieval_start) * 1000
            if not cands:
                skipped.append({'mode': mode, 'query': query, 'reason': '无候选'})
                print(f'  [SKIP] {query}: 无候选')
                continue
            if evidence:
                evidence.validate_candidates(query, cands)
            rel = {c['doc_id'] for c in cands if _is_rel(c['text'], case)}
            if not rel and not evidence:
                skipped.append({'mode': mode, 'query': query, 'reason': '候选集无主题相关项'})
                print(f'  [SKIP] {query}: 候选集无相关项（粗排全错，rerank 无从救）')
                continue
            pre_ranked = [c['doc_id'] for c in cands]
            try:
                rerank_start = time.perf_counter()
                post_ranked = _rough_rerank(query, cands)
                rerank_ms = (time.perf_counter() - rerank_start) * 1000
            except Exception as e:
                skipped.append({'mode': mode, 'query': query, 'reason': f'rerank 失败: {e}'})
                print(f'  [FAIL] {query}: rerank 调用失败: {e}')
                continue
            pre_m = _metrics(pre_ranked, rel)
            post_m = _metrics(post_ranked, rel)
            for k, v in pre_m.items():
                pre_sum[k] = pre_sum.get(k, 0.0) + v
            for k, v in post_m.items():
                post_sum[k] = post_sum.get(k, 0.0) + v
            n += 1
            all_per[mode].append({'query': query, 'topic': case['topic'], 'num_candidates': len(cands), 'n_rel': len(rel), 'pre': pre_m, 'post': post_m, 'retrieval_ms': round(retrieval_ms, 3), 'rerank_ms': round(rerank_ms, 3), 'total_ms': round(retrieval_ms + rerank_ms, 3), 'pre_ranked': pre_ranked[:FINAL_TOP_K], 'post_ranked': post_ranked, 'relevant_ids': sorted(rel), 'candidates': cands})
            if evidence:
                all_per[mode][-1]['label_scores'] = evidence.score_pair(case, cands, pre_ranked, post_ranked)
            delta = {k: round(post_m[k] - pre_m[k], 3) for k in pre_m}
            print(f"  [OK] {query:<22} rel={len(rel):<3} mrr {pre_m['mrr']}→{post_m['mrr']} prec@10 {pre_m['precision@10']}→{post_m['precision@10']} hit@1 {pre_m['hit@1']}→{post_m['hit@1']} | {delta}")
        if n == 0:
            print(f'  {label}: 无有效查询。')
            continue
        print(f"\n  {'指标':<16}{'精排前':>10}{'精排后':>10}{'提升':>8}")
        report_rows = {}
        for k in pre_sum:
            p = round(pre_sum[k] / n, 3)
            s = round(post_sum[k] / n, 3)
            print(f'  {k:<16}{p:>10}{s:>10}{s - p:>+8.3f}')
            report_rows[k] = {'pre': p, 'post': s, 'delta': round(s - p, 3)}
        import numpy as np
        latency = {field: {'mean': round(float(np.mean([r[field] for r in all_per[mode]])), 3), 'p95': round(float(np.percentile([r[field] for r in all_per[mode]], 95)), 3)} for field in ('retrieval_ms', 'rerank_ms', 'total_ms')}
        all_metrics[mode] = {'num_queries': n, 'metrics': report_rows, 'latency_ms': latency}
        print(f'  延迟(ms): {latency}')
        print()
    if not any((m.get('num_queries') for m in all_metrics.values())):
        print('[ERROR] 无有效查询（Milvus evidence_text 可能仍是旧域语料，请 index_builder --rebuild 重建健康索引后重跑）。', file=sys.stderr)
        sys.exit(1)
    report = {'benchmark': 'rerank_impact', 'rerank_model': actual_model, 'candidate_top_k': RERANK_TOP_K, 'final_top_k': FINAL_TOP_K, 'knowledge_version': KNOWLEDGE_VERSION, 'source_types': SOURCE_TYPES, 'rrf_k': int(os.getenv('RERANK_BENCH_RRF_K', '60')), 'rrf_weights': 'equal', 'parent_expansion': False, 'mrr_scope': 'top10 for both pre and post', 'relevance_method': 'topic substring in candidate snippets (first 200 characters), candidate-pool denominator', 'requested_queries_per_mode': len(CASES), 'skipped': skipped, 'bm25_only': all_metrics.get('bm25_only', {}), 'rrf_fusion': all_metrics.get('rrf_fusion', {}), 'per_query': {m[0]: all_per[m[0]] for m in modes}, 'timestamp': datetime.now().isoformat(timespec='seconds')}
    if evidence:
        from app.eval.evidence_labels import aggregate_label_comparison
        report['label_comparison'] = {mode: aggregate_label_comparison(rows) for mode, rows in all_per.items() if rows}
        report['evidence_annotation'] = {'path': args.evidence_labels, 'sha256': evidence.sha256, 'review_status': evidence.data['review_status'], 'scope': evidence.data['scope'], 'documents': len(evidence.documents)}
        print('\n同一排序的新旧标签对比:')
        print(json.dumps(report['label_comparison'], ensure_ascii=False, indent=2))
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = args.output or os.path.join(REPORT_DIR, f'rerank_bench_{datetime.now():%Y%m%d}.json')
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n报告已落库: {path}')
    except PermissionError:
        alt = f'/tmp/rerank_bench_{datetime.now():%Y%m%d}.json'
        with open(alt, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n报告落库到项目目录被拒（只读），已写 /tmp: {alt}')
    if '--json' in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    main()
