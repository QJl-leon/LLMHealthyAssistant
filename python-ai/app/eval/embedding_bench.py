from __future__ import annotations
import json
import math
import os
import sys
import time
from datetime import datetime
from typing import Optional
from httpx import Client
from app.eval.retrieval_bench import RETRIEVAL_EVAL_SET, _build_self_corpus, _load_db_corpus

REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
CANDIDATE_MODELS = {'BAAI/bge-m3': {'note': '基线：多语言多粒度，中文 RAG 标配', 'dim_hint': 1024}, 'BAAI/bge-large-zh-v1.5': {'note': '中文专用大模型', 'dim_hint': 1024}, 'Qwen/Qwen3-Embedding-0.6B': {'note': '轻量小模型，省成本/低延迟', 'dim_hint': 1024}}
BASE_URL = 'https://api.siliconflow.cn/v1'
TIMEOUT = 60
_CORPUS: list[tuple[str, str]] | None = None

def _get_corpus() -> list[tuple[str, str]]:
    global _CORPUS
    if _CORPUS is None:
        _CORPUS = _load_db_corpus() or _build_self_corpus()
    return _CORPUS

def _get_queries() -> list[dict]:
    return list(RETRIEVAL_EVAL_SET)

def _embed(api_key: str, model: str, texts: list[str]) -> Optional[list[list[float]]]:
    with Client(base_url=BASE_URL, timeout=TIMEOUT) as client:
        resp = client.post('/embeddings', json={'model': model, 'input': texts}, headers={'Authorization': f'Bearer {api_key}'})
        resp.raise_for_status()
        data = resp.json()
        return [item['embedding'] for item in data['data']]

def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum((x * y for x, y in zip(a, b)))
    na = math.sqrt(sum((x * x for x in a))) or 1e-09
    nb = math.sqrt(sum((x * x for x in b))) or 1e-09
    return dot / (na * nb)

def _ndcg(ranked: list[str], relevant: set[str], k: int) -> float:
    dcg = sum((1.0 / math.log2(i + 2) for i, d in enumerate(ranked[:k]) if d in relevant))
    idcg = sum((1.0 / math.log2(i + 2) for i in range(min(k, len(relevant)))))
    return dcg / idcg if idcg else 0.0

def bench_model(api_key: str, model: str, docs: list[tuple[str, str]]) -> dict:
    queries = _get_queries()
    t0 = time.time()
    doc_vecs = _embed(api_key, model, [t for _, t in docs])
    query_vecs = _embed(api_key, model, [q['query'] for q in queries])
    embed_s = round(time.time() - t0, 2)
    dim = len(doc_vecs[0]) if doc_vecs else 0
    recall_10, mrr_s, ndcg_s, hit_1 = (0, 0.0, 0.0, 0)
    for qv, q in zip(query_vecs, queries):
        topics = q['topics']
        relevant = {d for d, t in docs if any((topic in t for topic in topics))}
        if not relevant:
            continue
        scored = sorted(((_cosine(qv, doc_vecs[i]), i, doc_id) for i, (doc_id, _) in enumerate(docs)), key=lambda x: x[0], reverse=True)
        ranked = [d for _, _, d in scored[:10]]
        rel_top = sum((1 for d in ranked if d in relevant))
        recall_10 += rel_top / max(len(relevant), 1)
        ndcg_s += _ndcg(ranked, relevant, 10)
        for rank, (_, _, d) in enumerate(scored, 1):
            if d in relevant:
                mrr_s += 1.0 / rank
                if rank == 1:
                    hit_1 += 1
                break
    n = len(queries)
    return {'model': model, 'dim': dim, 'total_docs': len(docs), 'embed_seconds': embed_s, 'recall@10': round(recall_10 / n, 3), 'mrr': round(mrr_s / n, 3), 'ndcg@10': round(ndcg_s / n, 3), 'hit@1': round(hit_1 / n, 3), 'note': CANDIDATE_MODELS.get(model, {}).get('note', '')}

def main():
    argv = sys.argv[1:]
    dry = '--dry-run' in argv
    if '--models' in argv:
        selected = argv[argv.index('--models') + 1].split(',')
    else:
        selected = list(CANDIDATE_MODELS)
    api_key = os.getenv('SILICONFLOW_API_KEY', '')
    docs = _get_corpus()
    queries = _get_queries()
    if dry or not api_key:
        print('\n=== Embedding 选型对比（亮点3）===')
        if not api_key:
            print('SILICONFLOW_API_KEY 未配置 → dry-run 模式（仅预览，不调 API）')
        print(f'语料: {len(docs)} 条健康知识 | 查询: {len(queries)} 条')
        print(f'指标: Recall@10 / MRR / NDCG@10 / Hit@1 + 维度/耗时\n')
        print(f"{'模型':<32}{'维度':>6}{'叙事'}")
        for m in selected:
            print(f"{m:<32}{CANDIDATE_MODELS.get(m, {}).get('dim_hint', '?'):>6}  {CANDIDATE_MODELS.get(m, {}).get('note', '')}")
        print('\n配置 SILICONFLOW_API_KEY 后重跑即可得到真实对比数据。')
        return
    print('\n=== Embedding 选型对比（亮点3）真实模式 ===\n')
    results = []
    for model in selected:
        try:
            r = bench_model(api_key, model, docs)
            results.append(r)
            print(f"[OK] {model:<36} recall@10={r['recall@10']} mrr={r['mrr']} ndcg@10={r['ndcg@10']} dim={r['dim']} ({r['embed_seconds']}s)")
        except Exception as e:
            print(f'[FAIL] {model}: {e}')
    if not results:
        print('全部模型调用失败，检查网络 / API Key。')
        sys.exit(1)
    report = {'benchmark': 'embedding_selection', 'num_docs': len(docs), 'num_queries': len(queries), 'results': sorted(results, key=lambda x: x['recall@10'], reverse=True), 'timestamp': datetime.now().isoformat(timespec='seconds')}
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f'embedding_bench_{datetime.now():%Y%m%d}.json')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n选型报告已落库: {path}')
    except PermissionError:
        alt = f'/tmp/embedding_bench_{datetime.now():%Y%m%d}.json'
        with open(alt, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n报告落库到项目目录被拒（只读），已写 /tmp: {alt}')
    if '--json' in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    main()
