from __future__ import annotations
import json
import os
import sys
import time
from datetime import datetime
REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
TOP_K = 20
RERANK_TOP_K = 10
QUERIES = ['血脂高的人该怎么锻炼', '血糖偏高怎么运动', '血压有点高适合什么运动', '尿酸偏高能不能运动', '脂肪肝靠运动能改善吗', '体重超标怎么减重', '低密度脂蛋白胆固醇参考区间是多少', '谷丙转氨酶偏高怎么办', '他汀用药和运动注意事项', '高尿酸血症运动禁忌']

def _install_counters() -> dict:
    from app.gateway.adapters.embedding import EmbeddingAdapter
    from app.gateway.adapters.reranker import RerankerAdapter
    counters = {'embedding_calls': 0, 'rerank_calls': 0}
    if not getattr(EmbeddingAdapter, '_counted', False):
        orig_embed = EmbeddingAdapter._embed_uncached

        def counted_embed(self, texts):
            counters['embedding_calls'] += 1
            return orig_embed(self, texts)
        EmbeddingAdapter._embed_uncached = counted_embed
        EmbeddingAdapter._counted = True
    if not getattr(RerankerAdapter, '_counted', False):
        orig_rerank = RerankerAdapter._rerank_uncached

        def counted_rerank(self, query, documents, top_k=10):
            counters['rerank_calls'] += 1
            return orig_rerank(self, query, documents, top_k)
        RerankerAdapter._rerank_uncached = counted_rerank
        RerankerAdapter._counted = True
    return counters

def _snapshot(counters: dict) -> dict:
    return dict(counters)

def _run_round(queries: list[str], use_rerank: bool) -> list[float]:
    from app.retrieval.channels import search_bm25, search_dense
    latencies = []
    for q in queries:
        t0 = time.time()
        r1 = search_bm25(q, top_k=TOP_K)
        r2 = search_dense(q, top_k=TOP_K)
        if use_rerank:
            docs = (list(r1.snippets) + list(r2.snippets))[:TOP_K]
            if docs:
                try:
                    from app.gateway.adapters.reranker import RerankerAdapter
                    RerankerAdapter().rerank(q, docs, top_k=RERANK_TOP_K)
                except Exception as e:
                    print(f'    [WARN] rerank 失败（忽略）: {str(e)[:80]}')
        latencies.append((time.time() - t0) * 1000)
    return latencies

def _p95(values: list[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = min(len(s) - 1, int(len(s) * 0.95))
    return round(s[idx], 1)

def main():
    dry = '--dry-run' in sys.argv
    use_rerank = '--no-rerank' not in sys.argv
    if dry:
        print('\n=== Redis 缓存效果实验 dry-run ===')
        print(f'查询: {len(QUERIES)} 条，每模式两轮（冷启动 / 热查询）')
        print(f"对比: CACHE_ENABLED=false vs true（rerank={('开' if use_rerank else '关')}）")
        print('指标: 平均/P95 延迟、命中率、embedding/rerank 真实回源次数')
        return
    from app.cache import get_cache
    cache = get_cache()
    probe = cache._get_client()
    if probe is None:
        print('Redis 不可用（检查 REDIS_URL / 容器状态），退出。')
        return
    counters = _install_counters()
    print('\n=== Redis 缓存效果实验（真实 Redis + 真实管线）===\n')
    print(f"  Redis: {cache.url} | 查询 {len(QUERIES)} 条 | rerank={('开' if use_rerank else '关')}\n")
    results: dict[str, dict] = {}
    for mode in ('off', 'on'):
        cache.enabled = mode == 'on'
        cache.clear_all()
        cache.reset_stats()
        for rnd in (1, 2):
            before = _snapshot(counters)
            lat = _run_round(QUERIES, use_rerank)
            after = _snapshot(counters)
            label = f'{mode}_round{rnd}'
            results[label] = {'mode': mode, 'round': rnd, 'avg_ms': round(sum(lat) / len(lat), 1), 'p95_ms': _p95(lat), 'embedding_calls': after['embedding_calls'] - before['embedding_calls'], 'rerank_calls': after['rerank_calls'] - before['rerank_calls'], 'cache_hit': cache.stats['hit'], 'cache_miss': cache.stats['miss']}
            print(f"  [{label:<12}] avg={results[label]['avg_ms']:>8.1f}ms p95={results[label]['p95_ms']:>8.1f}ms embedding={results[label]['embedding_calls']:>2}次 rerank={results[label]['rerank_calls']:>2}次 hit/miss={cache.stats['hit']}/{cache.stats['miss']}")
            if mode == 'on' and rnd == 1:
                cache.reset_stats()
    off2, on2 = (results.get('off_round2', {}), results.get('on_round2', {}))
    print('\n  热查询轮次对比（最能反映高频问题收益）:\n')
    print(f"  {'指标':<18}{'无缓存':>12}{'有缓存':>12}{'变化':>12}")
    rows = [('平均延迟', 'avg_ms', 'ms'), ('P95 延迟', 'p95_ms', 'ms'), ('embedding 回源', 'embedding_calls', '次'), ('rerank 回源', 'rerank_calls', '次')]
    for label, key, unit in rows:
        a, b = (off2.get(key, 0), on2.get(key, 0))
        delta = b - a
        print(f'  {label:<18}{a:>12}{b:>12}{delta:>+12}')
    hit_round2 = on2.get('cache_hit', 0)
    miss_round2 = on2.get('cache_miss', 0)
    hit_rate = round(hit_round2 / (hit_round2 + miss_round2), 4) if hit_round2 + miss_round2 else 0.0
    print(f'\n  缓存命中率（热查询轮）: {hit_rate:.1%}')
    speedup = round(off2.get('avg_ms', 0) / on2.get('avg_ms', 1), 2) if on2.get('avg_ms') else 0.0
    report = {'benchmark': 'redis_cache_impact', 'question': '高频问题缓存的收益量化', 'redis_url': cache.url, 'num_queries': len(QUERIES), 'rerank_enabled': use_rerank, 'results': results, 'hit_rate_round2': hit_rate, 'speedup_round2': speedup, 'insight': f"热查询轮：平均延迟 {off2.get('avg_ms')}ms → {on2.get('avg_ms')}ms（{speedup}x），P95 {off2.get('p95_ms')}ms → {on2.get('p95_ms')}ms；embedding 回源 {off2.get('embedding_calls')} → {on2.get('embedding_calls')} 次，rerank 回源 {off2.get('rerank_calls')} → {on2.get('rerank_calls')} 次，命中率 {hit_rate:.1%}。缓存对象是纯函数型中间产物（query 向量 / 检索结果 / 精排排序），key 含 tenant + knowledge_version，个性化结果不进共享缓存；Redis 故障自动熔断回源（不影响可用性）。", 'timestamp': datetime.now().isoformat(timespec='seconds')}
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f'cache_bench_{datetime.now():%Y%m%d}.json')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n报告已落库: {path}')
    except PermissionError:
        alt = f'/tmp/cache_bench_{datetime.now():%Y%m%d}.json'
        with open(alt, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n报告落库到项目目录被拒（只读），已写 /tmp: {alt}')
if __name__ == '__main__':
    main()
