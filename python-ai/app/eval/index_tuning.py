from __future__ import annotations
import argparse
import json
import math
import uuid
import os
import sys
import time
from datetime import datetime
REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
PARAM_SPACE = {'M': [8, 16, 32], 'efConstruction': [100, 200], 'search_ef': [32, 64, 128]}
NPROBE_VALUES = [4, 8, 16, 32, 64]
N_VECTORS = 1000
DIM = 256
N_QUERIES = 100
TOPK = 10
SEEDS_PER_VEC = 35
PERTURB_STD = 0.15

def _milvus_ready() -> bool:
    try:
        from pymilvus import connections, utility
        host = os.getenv('MILVUS_HOST', 'localhost')
        port = os.getenv('MILVUS_PORT', '19530')
        connections.connect(host=host, port=port, timeout=8)
        utility.list_collections()
        connections.disconnect('default')
        return True
    except Exception:
        return False

def _load_real_vectors() -> list[list[float]]:
    import os
    from pymilvus import connections, Collection
    try:
        connections.connect(host=os.getenv('MILVUS_HOST', 'localhost'), port=os.getenv('MILVUS_PORT', '19530'), timeout=8)
        coll = Collection('evidence_text')
        coll.load()
        rows = coll.query(expr='tenant_id == "dev-tenant"', output_fields=['embedding'], limit=10000)
        connections.disconnect('default')
    except Exception:
        return []
    vecs = [list(r['embedding']) for r in rows if r.get('embedding')]
    return vecs

def _derive_corpus(seeds: list[list[float]], copies: int | None=None, seed: int=42) -> list[list[float]]:
    import random
    import math
    if copies is None:
        copies = SEEDS_PER_VEC
    rng = random.Random(seed)
    out: list[list[float]] = []
    for v in seeds:
        norm = math.sqrt(sum((x * x for x in v))) or 1.0
        base = [x / norm for x in v]
        for _ in range(copies):
            perturbed = [x + rng.gauss(0, PERTURB_STD) for x in base]
            n2 = math.sqrt(sum((x * x for x in perturbed))) or 1.0
            out.append([x / n2 for x in perturbed])
    return out

QUERY_TEMPLATES = [
    '{name} 参考区间 运动干预',
    '{name} 正常范围是多少，异常结果如何解读？',
    '{name} 偏高时适合哪些运动干预？',
    '{name} 偏低时运动有哪些注意事项？',
    '如何通过运动改善{name}，复查时需要关注什么？',
]


def _build_query_texts(names, num_queries):
    if num_queries <= 0:
        raise ValueError('查询数必须为正整数')
    names = list(dict.fromkeys(n.strip() for n in names if n.strip()))
    candidates = list(dict.fromkeys(
        template.format(name=name) for template in QUERY_TEMPLATES for name in names
    ))
    if len(candidates) < num_queries:
        raise ValueError(f'只能生成 {len(candidates)} 条不同查询，少于要求的 {num_queries} 条')
    # Retain the original queries first, then expand across all metric names.
    return candidates[:num_queries]


def _load_real_queries(num_queries=None, *, query_texts_out=None) -> list[list[float]]:
    import os
    from app.gateway.adapters.embedding import EmbeddingAdapter
    try:
        import psycopg2
        from app.factory.repository import get_current_version
        kv = get_current_version()
        db = os.getenv('DATABASE_URL', 'postgresql://lha:lha_dev@localhost:5432/lha')
        conn = psycopg2.connect(db)
        cur = conn.cursor()
        names = []
        if kv is not None:
            cur.execute("SELECT name_cn FROM metric_catalog WHERE knowledge_version = %s AND name_cn <> '' ORDER BY name_cn", (kv.version,))
            names = [str(r[0]).strip() for r in cur.fetchall()]
        if not names:
            cur.execute("SELECT name_cn FROM metric_catalog WHERE name_cn <> '' ORDER BY name_cn")
            names = [str(r[0]).strip() for r in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception:
        return []
    count = N_QUERIES if num_queries is None else num_queries
    queries_text = _build_query_texts(names, count)
    embedder = EmbeddingAdapter()
    vecs = []
    for start in range(0, len(queries_text), 32):
        batch = queries_text[start:start + 32]
        embeddings = embedder.embed(batch)
        if len(embeddings) != len(batch) or any(not v for v in embeddings):
            raise RuntimeError('查询 embedding 返回数量不匹配或空向量，停止评测')
        vecs.extend(list(v) for v in embeddings)
    if query_texts_out is not None:
        query_texts_out.extend(queries_text)
    return vecs

def _run_real_sweep(num_queries=None) -> dict:
    from pymilvus import Collection, CollectionSchema, FieldSchema, DataType, utility
    seeds = _load_real_vectors()
    if not seeds:
        raise RuntimeError('Milvus evidence_text 无真实向量，无法跑真实调参')
    queries = _load_real_queries(num_queries)
    if not queries:
        raise RuntimeError('无法嵌入真实查询向量，无法跑真实调参')
    vectors = _derive_corpus(seeds)
    dim = len(vectors[0])
    from pymilvus import connections
    connections.connect(host=os.getenv('MILVUS_HOST', 'localhost'), port=os.getenv('MILVUS_PORT', '19530'))
    coll_name = 'tune_hnsw'
    if utility.has_collection(coll_name):
        utility.drop_collection(coll_name)
    flat = Collection(coll_name, CollectionSchema([FieldSchema('id', DataType.INT64, is_primary=True), FieldSchema('embedding', DataType.FLOAT_VECTOR, dim=dim)]))
    flat.create_index('embedding', {'index_type': 'FLAT', 'metric_type': 'COSINE'})
    flat.insert([{'id': i, 'embedding': v} for i, v in enumerate(vectors)])
    flat.flush()
    flat.load()
    truth = {}
    for q_idx, q in enumerate(queries):
        hits = flat.search([q], 'embedding', {'metric_type': 'COSINE'}, limit=TOPK)[0]
        truth[q_idx] = {h.id for h in hits}
    utility.drop_collection(coll_name)
    results = []
    for M in PARAM_SPACE['M']:
        for ef_c in PARAM_SPACE['efConstruction']:
            coll = Collection(coll_name, CollectionSchema([FieldSchema('id', DataType.INT64, is_primary=True), FieldSchema('embedding', DataType.FLOAT_VECTOR, dim=dim)]))
            coll.create_index('embedding', {'index_type': 'HNSW', 'metric_type': 'COSINE', 'params': {'M': M, 'efConstruction': ef_c}})
            coll.insert([{'id': i, 'embedding': v} for i, v in enumerate(vectors)])
            coll.flush()
            utility.wait_for_index_building_complete(coll_name, timeout=120)
            coll.load()
            for ef in PARAM_SPACE['search_ef']:
                lat = []
                recall = 0
                for q_idx, q in enumerate(queries):
                    t0 = time.perf_counter()
                    hits = coll.search([q], 'embedding', {'metric_type': 'COSINE', 'params': {'ef': ef}}, limit=TOPK)[0]
                    lat.append((time.perf_counter() - t0) * 1000)
                    recall += len({h.id for h in hits} & truth[q_idx]) / TOPK
                lat.sort()
                p95 = lat[int(len(lat) * 0.95) - 1]
                results.append({'M': M, 'efConstruction': ef_c, 'search_ef': ef, 'recall@10': round(recall / len(queries), 4), 'p95_latency_ms': round(p95, 2)})
            utility.drop_collection(coll_name)
            print(f'  M={M} efC={ef_c} 完成')
    return {'mode': 'real', 'results': results, 'dim': dim, 'num_vectors': len(vectors), 'num_queries': len(queries)}

def _measure_search(coll, queries, search_params, truth=None):
    """Warm up each search configuration, then time individual queries."""
    for q in queries:
        coll.search([q], 'embedding', search_params, limit=TOPK, timeout=30)
    latencies = []
    hit_ids = []
    for q in queries:
        start = time.perf_counter()
        hits = coll.search([q], 'embedding', search_params, limit=TOPK, timeout=30)[0]
        latencies.append((time.perf_counter() - start) * 1000)
        hit_ids.append({h.id for h in hits})
    references = hit_ids if truth is None else truth
    recall = sum(len(ids & ref) / len(ref) for ids, ref in zip(hit_ids, references)) / len(queries)
    latencies.sort()
    p95 = latencies[math.ceil(len(latencies) * 0.95) - 1]
    return {'recall@10': round(recall, 4), 'p95_latency_ms': round(p95, 2)}, hit_ids


def _run_ivf_sq8_sweep(nprobes, nlist, num_queries=None):
    from pymilvus import Collection, CollectionSchema, FieldSchema, DataType, connections, utility
    seeds = _load_real_vectors()
    if not seeds:
        raise RuntimeError('Milvus evidence_text 无真实向量，无法跑真实调参')
    query_texts = []
    queries = _load_real_queries(num_queries, query_texts_out=query_texts)
    if not queries:
        raise RuntimeError('无法嵌入真实查询向量，无法跑真实调参')
    vectors = _derive_corpus(seeds)
    dim = len(vectors[0])
    if any(len(q) != dim for q in queries):
        raise ValueError('查询向量与语料向量维度不一致')
    if len(vectors) < nlist:
        raise ValueError(f'向量数 {len(vectors)} 小于 nlist={nlist}')
    connections.connect(host=os.getenv('MILVUS_HOST', 'localhost'), port=os.getenv('MILVUS_PORT', '19530'), timeout=8)
    coll_name = 'tune_ivf_sq8_' + uuid.uuid4().hex
    created = False
    try:
        coll = Collection(coll_name, CollectionSchema([
            FieldSchema('id', DataType.INT64, is_primary=True),
            FieldSchema('embedding', DataType.FLOAT_VECTOR, dim=dim),
        ]))
        created = True
        coll.insert([{'id': i, 'embedding': v} for i, v in enumerate(vectors)])
        coll.flush(timeout=120)
        coll.create_index('embedding', {'index_type': 'FLAT', 'metric_type': 'COSINE'}, timeout=120)
        utility.wait_for_index_building_complete(coll_name, timeout=120)
        coll.load(timeout=120)
        baseline, truth = _measure_search(coll, queries, {'metric_type': 'COSINE'})
        coll.release(timeout=30)
        coll.drop_index(timeout=30)
        coll.create_index('embedding', {
            'index_type': 'IVF_SQ8', 'metric_type': 'COSINE', 'params': {'nlist': nlist},
        }, timeout=120)
        utility.wait_for_index_building_complete(coll_name, timeout=120)
        coll.load(timeout=120)
        results = []
        for nprobe in nprobes:
            metrics, _ = _measure_search(coll, queries, {
                'metric_type': 'COSINE', 'params': {'nprobe': nprobe},
            }, truth)
            row = {'index_type': 'IVF_SQ8', 'nlist': nlist, 'nprobe': nprobe, **metrics}
            results.append(row)
            print(f"  nprobe={nprobe}: Recall@10={metrics['recall@10']:.4f}, P95={metrics['p95_latency_ms']:.2f} ms", flush=True)
        return {
            'mode': 'real', 'index_type': 'IVF_SQ8', 'metric_type': 'COSINE',
            'nlist': nlist, 'nprobes': nprobes, 'results': results,
            'baseline': {'index_type': 'FLAT', **baseline}, 'dim': dim,
            'num_seed_vectors': len(seeds), 'num_vectors': len(vectors),
            'num_queries': len(queries), 'query_texts': query_texts,
            'query_generation': 'metric_templates_v2',
            'embedding_model': os.getenv('EMBEDDING_MODEL', 'BAAI/bge-m3'),
            'copies_per_seed': SEEDS_PER_VEC,
            'corpus_seed': 42, 'perturb_std': PERTURB_STD,
            'warmup_queries_per_config': len(queries), 'p95_method': 'nearest_rank',
        }
    finally:
        if created:
            utility.drop_collection(coll_name, timeout=30)
        connections.disconnect('default')


def _positive_int_list(value):
    try:
        values = [int(x) for x in value.split(',')]
    except ValueError as exc:
        raise argparse.ArgumentTypeError('请输入逗号分隔的正整数') from exc
    if not values or any(x <= 0 for x in values):
        raise argparse.ArgumentTypeError('参数必须为正整数')
    return list(dict.fromkeys(values))


def main():
    parser = argparse.ArgumentParser(description='实验5：HNSW / IVF_SQ8 索引扫参')
    parser.add_argument('--index-type', choices=['HNSW', 'IVF_SQ8'], default='HNSW')
    parser.add_argument('--M', type=_positive_int_list)
    parser.add_argument('--ef', type=_positive_int_list)
    parser.add_argument('--nprobe', type=_positive_int_list, default=NPROBE_VALUES)
    parser.add_argument('--nlist', type=int, default=128)
    parser.add_argument('--num-queries', type=int, default=N_QUERIES)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.num_queries <= 0:
        parser.error('--num-queries 必须为正整数')
    if args.index_type == 'IVF_SQ8' and (args.nlist <= 0 or any(x > args.nlist for x in args.nprobe)):
        parser.error('nlist 必须为正整数，且所有 nprobe 必须不大于 nlist')
    if args.M:
        PARAM_SPACE['M'] = args.M
    if args.ef:
        PARAM_SPACE['search_ef'] = args.ef
    # Explicit dry runs must not contact Milvus or the embedding service.
    ready = False if args.dry_run else _milvus_ready()
    if args.dry_run or not ready:
        print(f'\n=== {args.index_type} 索引调参 sweep（亮点4）===')
        if not args.dry_run and not ready:
            print('Milvus 未启动 → dry-run（仅预览参数空间与实验设计）')
        if args.index_type == 'IVF_SQ8':
            print(f'参数空间: nlist={args.nlist}, nprobe={args.nprobe}')
        else:
            print(f"参数空间: M={PARAM_SPACE['M']} × efConstruction={PARAM_SPACE['efConstruction']} × search_ef={PARAM_SPACE['search_ef']}")
        print(f'数据: Milvus evidence_text 真实健康知识向量派生扩充（每个真实向量派生 {SEEDS_PER_VEC} 个副本）/ {args.num_queries} 条不同查询')
        print('实验设计：')
        print('  1. FLAT 暴力检索结果作 ground truth（召回上界）')
        if args.index_type == 'IVF_SQ8':
            print('  2. 固定 IVF_SQ8 索引与 nlist，逐组修改 nprobe，预热后测 Recall@10 与 P95 延迟')
            print('  3. 使用独立临时集合，结束后清理；结果单独保存')
        else:
            print('  2. 每组参数重建 HNSW 索引，测 Recall@10 与 P95 延迟')
            print('  3. 权衡曲线 → 选定参数写入配置')
        return
    print(f'\n=== {args.index_type} 索引调参（亮点4）真实模式 ===', flush=True)
    report = _run_ivf_sq8_sweep(args.nprobe, args.nlist, args.num_queries) if args.index_type == 'IVF_SQ8' else _run_real_sweep(args.num_queries)
    report['topk'] = TOPK
    report['data_source'] = 'Milvus evidence_text 真实向量派生扩充'
    report['timestamp'] = datetime.now().isoformat(timespec='seconds')
    os.makedirs(REPORT_DIR, exist_ok=True)
    filename = (f'index_tuning_ivf_sq8_{datetime.now():%Y%m%d_%H%M%S_%f}.json'
                if args.index_type == 'IVF_SQ8' else f'index_tuning_{datetime.now():%Y%m%d}.json')
    path = os.path.join(REPORT_DIR, filename)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'调参报告已保存: {path}')
    except PermissionError:
        alt = os.path.join('/tmp', filename)
        with open(alt, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'报告目录只读，已写 /tmp: {alt}')
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
