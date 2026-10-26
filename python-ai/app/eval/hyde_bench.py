from __future__ import annotations
import json
import math
import os
import sys
import time
from contextlib import contextmanager
from datetime import datetime
REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
TOP_K = 50
FINAL_TOP_K = 10
MULTI_N = 3
KNOWLEDGE_VERSION = os.getenv('HYDE_BENCH_KNOWLEDGE_VERSION') or None
SOURCE_TYPES = ['guideline', 'case', 'metric_catalog']
CASES = [{'query': '血脂高的人该怎么锻炼', 'topic': '血脂'}, {'query': '血糖偏高怎么运动', 'topic': '血糖'}, {'query': '血压有点高适合什么运动', 'topic': '血压'}, {'query': '尿酸偏高能不能运动', 'topic': '尿酸'}, {'query': '脂肪肝靠运动能改善吗', 'topic': '脂肪肝'}, {'query': '体重超标怎么减重', 'topic': '体重'}, {'query': '血脂异常的运动建议', 'topic': '血脂'}, {'query': '血糖控制怎么运动', 'topic': '血糖'}, {'query': '高血压运动注意事项', 'topic': '血压'}, {'query': '高尿酸怎么运动', 'topic': '尿酸'}, {'query': '低密度脂蛋白胆固醇参考区间是多少', 'name': '低密度脂蛋白胆固醇'}, {'query': '谷丙转氨酶偏高怎么办', 'name': '谷丙转氨酶'}, {'query': '他汀用药和运动注意事项', 'name': '他汀'}, {'query': '高尿酸血症运动禁忌', 'name': '高尿酸'}]


def _is_rel(text: str, case: dict) -> bool:
    label = case.get('topic') or case.get('name') or ''
    return bool(label) and label in text


def _ndcg(ranked: list[str], rel: set[str], k: int) -> float:
    dcg = sum(1.0 / math.log2(i + 2) for i, d in enumerate(ranked[:k]) if d in rel)
    idcg = sum(1.0 / math.log2(i + 2) for i in range(min(k, len(rel))))
    return dcg / idcg if idcg else 0.0


def _metrics(ranked: list[str], rel: set[str]) -> dict:
    top = ranked[:FINAL_TOP_K]
    n_rel = sum(d in rel for d in top)
    return {'recall@10': round(n_rel / max(len(rel), 1), 3), 'mrr': round(next((1.0 / (i + 1) for i, d in enumerate(ranked) if d in rel), 0.0), 3), 'hit@1': float(bool(ranked) and ranked[0] in rel), 'ndcg@10': round(_ndcg(ranked, rel, FINAL_TOP_K), 3)}


@contextmanager
def _llm_counter():
    """Measure actual API usage and restore the adapter even on failure."""
    from app.gateway.adapters.llm import LLMAdapter
    counters = dict(tokens=0, prompt_tokens=0, completion_tokens=0, calls=0, attempts=0, failed_calls=0, usage_missing_calls=0, truncated_calls=0)
    original = LLMAdapter.chat
    def counted(self, messages, **kwargs):
        counters['attempts'] += 1
        try:
            response = original(self, messages, **kwargs)
        except Exception:
            counters['failed_calls'] += 1
            raise
        counters['calls'] += 1
        usage = response.get('usage') or {}
        if 'total_tokens' not in usage:
            counters['usage_missing_calls'] += 1
        for source, dest in [('total_tokens', 'tokens'), ('prompt_tokens', 'prompt_tokens'), ('completion_tokens', 'completion_tokens')]:
            counters[dest] += int(usage.get(source) or 0)
        counters['truncated_calls'] += sum(choice.get('finish_reason') == 'length' for choice in response.get('choices', []))
        return response
    LLMAdapter.chat = counted
    try:
        yield counters
    finally:
        LLMAdapter.chat = original


def _avg_vector(vecs: list[list[float]]) -> list[float]:
    import numpy as np
    if not vecs:
        return []
    arr = np.array(vecs, dtype='float32').mean(axis=0)
    norm = float(np.linalg.norm(arr))
    return (arr / norm if norm > 0 else arr).tolist()


def _embed(texts: list[str]) -> list[list[float]]:
    from app.gateway.adapters.embedding import EmbeddingAdapter
    vectors = EmbeddingAdapter().embed(texts)
    dim = int(os.getenv('EMBEDDING_DIM', '1024'))
    if len(vectors) != len(texts) or any(len(v) != dim or not any(v) for v in vectors):
        raise RuntimeError('Embedding 数量、维度或非零检查失败')
    return vectors


def _run_mode(query, mode, counters):
    from app.retrieval.channels import search_dense
    from app.retrieval.hyde import build_hyde_queries, build_hyde_query
    before = counters.copy()
    start = time.perf_counter()
    if mode == 'raw':
        texts = [query]
    elif mode == 'hyde':
        texts = [build_hyde_query(query)]
    elif mode == 'multi_hyde':
        texts = build_hyde_queries(query, n=MULTI_N)
    else:
        raise ValueError(mode)
    generation_ms = (time.perf_counter() - start) * 1000
    embed_start = time.perf_counter()
    vectors = _embed(texts)
    vector = _avg_vector(vectors) if mode == 'multi_hyde' else vectors[0]
    embedding_ms = (time.perf_counter() - embed_start) * 1000
    retrieval_start = time.perf_counter()
    result = search_dense(query, embedding=vector, top_k=TOP_K, knowledge_version=KNOWLEDGE_VERSION, source_types=SOURCE_TYPES)
    retrieval_ms = (time.perf_counter() - retrieval_start) * 1000
    if not result.doc_ids:
        raise RuntimeError('Dense 通道无结果，不能作为成功的 HyDE 对照')
    candidates = [{'doc_id': str(did), 'text': snippet} for did, snippet in zip(result.doc_ids, result.snippets)]
    if len({c['doc_id'] for c in candidates}) != len(candidates):
        raise RuntimeError('候选主键重复')
    return {'candidates': candidates, 'generated_documents': texts if mode != 'raw' else [], 'effective_documents': sum(text != query for text in texts) if mode != 'raw' else 0, 'fallback_to_raw': mode != 'raw' and all(text == query for text in texts), 'generation_ms': round(generation_ms, 3), 'embedding_ms': round(embedding_ms, 3), 'retrieval_ms': round(retrieval_ms, 3), 'latency_ms': round((time.perf_counter() - start) * 1000, 3), 'usage': {key: counters[key] - before[key] for key in counters}}


def _evaluate(counters):
    modes = ['raw', 'hyde', 'multi_hyde']
    per_query, excluded, attempts = [], [], []
    for case in CASES:
        query = case['query']
        results, errors = {}, []
        for mode in modes:
            before = counters.copy()
            start = time.perf_counter()
            try:
                results[mode] = _run_mode(query, mode, counters)
                attempts.append({'query': query, 'mode': mode, 'status': 'ok', 'latency_ms': results[mode]['latency_ms'], 'usage': results[mode]['usage']})
            except Exception as exc:
                error = f'{type(exc).__name__}: {str(exc)[:160]}'
                errors.append({'mode': mode, 'error': error})
                attempts.append({'query': query, 'mode': mode, 'status': 'failed', 'error': error, 'latency_ms': round((time.perf_counter()-start)*1000,3), 'usage': {key: counters[key]-before[key] for key in counters}})
                print(f'  [FAIL] {query} {mode}: {error}', flush=True)
        if errors:
            excluded.append({'query': query, 'reason': '模式不完整，排除整个查询以保持配对比较', 'errors': errors})
            continue
        relevant = {c['doc_id'] for result in results.values() for c in result['candidates'] if _is_rel(c['text'], case)}
        if not relevant:
            excluded.append({'query': query, 'reason': '三路候选片段均无目标词子串'})
            print(f'  [SKIP] {query}: 无主题词相关项', flush=True)
            continue
        row = {**case, 'rel': len(relevant), 'relevant_ids': sorted(relevant), 'details': results}
        for mode in modes:
            ranked = [c['doc_id'] for c in results[mode]['candidates']]
            row[mode] = _metrics(ranked, relevant)
            results[mode]['ranked_top10'] = ranked[:FINAL_TOP_K]
        per_query.append(row)
        print(f"  [OK] {query:<22} rel={len(relevant):<3} raw mrr={row['raw']['mrr']} hyde mrr={row['hyde']['mrr']} multi mrr={row['multi_hyde']['mrr']}", flush=True)
    import numpy as np
    aggregated = {}
    for mode in modes:
        accepted = [row['details'][mode] for row in per_query]
        all_attempts = [attempt for attempt in attempts if attempt['mode'] == mode]
        aggregate = {key: round(sum(row[mode][key] for row in per_query)/len(per_query),3) for key in ('recall@10','mrr','hit@1','ndcg@10')} if per_query else {}
        for field in ('latency_ms','generation_ms','embedding_ms','retrieval_ms'):
            latencies = [detail[field] for detail in accepted]
            aggregate[('avg_' if field == 'latency_ms' else 'avg_') + field] = round(float(np.mean(latencies)),3) if latencies else None
        aggregate['p95_latency_ms'] = round(float(np.percentile([d['latency_ms'] for d in accepted],95)),3) if accepted else None
        aggregate['llm_usage'] = {key: sum(detail['usage'][key] for detail in accepted) for key in counters}
        aggregate['llm_usage_all_attempts'] = {key: sum(attempt['usage'][key] for attempt in all_attempts) for key in counters}
        aggregate['fallback_queries'] = sum(d['fallback_to_raw'] for d in accepted)
        aggregate['partial_multi_queries'] = sum(0<d['effective_documents']<MULTI_N for d in accepted) if mode == 'multi_hyde' else 0
        aggregated[mode] = aggregate
    return per_query, excluded, attempts, aggregated


def main():
    if '--dry-run' in sys.argv:
        print('=== Query HyDE 效果实验 dry-run ===')
        print(f'查询: {len(CASES)} 条；A=raw / B=HyDE 单文档 / C=multi-HyDE 三文档均值向量')
        print('隔离变量: Dense-only，关闭缓存；不执行 BM25、RRF 或 rerank')
        print('指标: Recall@10 / MRR(Top50) / Hit@1 / NDCG@10 / 分阶段延迟 / API token usage / 回退')
        return
    if not os.getenv('DEEPSEEK_API_KEY') or not os.getenv('SILICONFLOW_API_KEY'):
        print('[ERROR] 真实 HyDE 评测需要 LLM 与 embedding API key。', file=sys.stderr)
        sys.exit(1)
    from app.cache import get_cache
    from app.gateway.adapters.llm import LLMAdapter
    from app.retrieval.hyde import HYDE_MODEL, HYDE_MAX_TOKENS
    llm = LLMAdapter()
    cache = get_cache()
    cache_was_enabled = cache.enabled
    cache.enabled = False
    print('=== Query HyDE 效果实验（真实 LLM + Milvus，Dense-only）===', flush=True)
    try:
        with _llm_counter() as counters:
            per_query, excluded, attempts, avgs = _evaluate(counters)
            usage_total = counters.copy()
    finally:
        cache.enabled = cache_was_enabled
    report = {'benchmark': 'query_hyde_impact', 'requested_queries': len(CASES), 'num_queries': len(per_query), 'multi_n': MULTI_N, 'knowledge_version': KNOWLEDGE_VERSION, 'source_types': SOURCE_TYPES, 'candidate_top_k': TOP_K, 'final_top_k': FINAL_TOP_K, 'mrr_scope': 'full returned Top50 for all modes', 'relevance_method': 'topic/name substring in first 200 characters of snippets; union of three candidate pools', 'isolated_variable': 'Dense-only; BM25/RRF/rerank not executed; cache disabled', 'llm_model': HYDE_MODEL or llm.model, 'llm_base_url': llm.base_url, 'hyde_max_tokens': HYDE_MAX_TOKENS, 'embedding_model': os.getenv('EMBEDDING_MODEL','BAAI/bge-m3'), 'llm_usage_total': usage_total, 'raw': avgs['raw'], 'hyde': avgs['hyde'], 'multi_hyde': avgs['multi_hyde'], 'per_query': per_query, 'excluded': excluded, 'attempts': attempts, 'timestamp': datetime.now().isoformat(timespec='seconds')}
    if per_query:
        report['delta'] = {mode: {key: round(avgs[mode][key]-avgs['raw'][key],3) for key in ('recall@10','mrr','hit@1','ndcg@10','avg_latency_ms')} for mode in ('hyde','multi_hyde')}
        print(f'\n配对有效查询: {len(per_query)}/{len(CASES)}',flush=True)
        for mode in ('raw','hyde','multi_hyde'):
            print(mode, json.dumps(avgs[mode],ensure_ascii=False),flush=True)
    os.makedirs(REPORT_DIR,exist_ok=True)
    path=os.path.join(REPORT_DIR,f'hyde_bench_{datetime.now():%Y%m%d}.json')
    with open(path,'w',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=False,indent=2)
    print(f'报告已落库: {path}',flush=True)
    if not per_query or any(attempt['status']=='failed' for attempt in attempts):
        sys.exit(1)

if __name__ == '__main__':
    main()
