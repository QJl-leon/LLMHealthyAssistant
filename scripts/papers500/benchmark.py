#!/usr/bin/env python3
"""Compare six isolated paper collections on the same labeled retrieval queries."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import statistics
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from import_vectors import STRATEGIES, embed_checked

DEFAULT_DATASET = Path(__file__).resolve().parent / 'eval_set_v1.jsonl'
CHANNELS = ('dense', 'bm25', 'hybrid')


def digest(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def load_dataset(path):
    sidecar = path.with_suffix('.meta.json')
    if not path.is_file() or not sidecar.is_file():
        raise ValueError('test set and matching .meta.json are required; run make_eval_set.py')
    meta = json.loads(sidecar.read_text(encoding='utf-8'))
    if meta.get('test_set_sha256') != digest(path):
        raise ValueError('test set checksum differs from its metadata')
    rows = []
    with path.open(encoding='utf-8') as source:
        for number, line in enumerate(source, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if (not isinstance(row.get('query'), str) or not row['query'].strip()
                    or not row.get('id') or not row.get('expected_doc_id')
                    or row.get('suite') not in ('human', 'coverage')
                    or row.get('knowledge_version') != meta.get('knowledge_version')):
                raise ValueError(f'{path}:{number}: invalid query or label')
            rows.append(row)
    counts = Counter(row['suite'] for row in rows)
    if (len({row['id'] for row in rows}) != len(rows)
            or counts['human'] != meta.get('human_query_variants')
            or counts['coverage'] != meta.get('coverage_queries')
            or len({row['pmcid'] for row in rows if row['suite'] == 'coverage'}) != meta.get('papers')):
        raise ValueError('test set counts/IDs disagree with metadata')
    return rows, meta


def collapse_documents(hits, limit):
    seen = set()
    out = []
    for hit in hits:
        doc_id = hit['doc_id']
        if doc_id and doc_id not in seen:
            seen.add(doc_id)
            out.append(hit)
            if len(out) >= limit:
                break
    return out


def reciprocal_rank_fusion(dense_hits, bm25_hits, k=60):
    scores, rows = defaultdict(float), {}
    for hits in (dense_hits, bm25_hits):
        for rank, hit in enumerate(hits, 1):
            chunk_id = hit['chunk_id']
            scores[chunk_id] += 1.0 / (k + rank)
            rows[chunk_id] = hit
    return [{**rows[chunk_id], 'score': score} for chunk_id, score in sorted(
        scores.items(), key=lambda item: (-item[1], item[0]))]


def score_one(ranked_docs, expected_doc_id, top_k):
    rank = next((i for i, row in enumerate(ranked_docs[:top_k], 1)
                 if row['doc_id'] == expected_doc_id), None)
    return {'hit@1': int(rank == 1), 'hit@5': int(rank is not None and rank <= 5),
            'hit@10': int(rank is not None and rank <= 10),
            'mrr@10': 1.0 / rank if rank is not None else 0.0,
            'ndcg@10': 1.0 / math.log2(rank + 1) if rank is not None else 0.0,
            'rank': rank}


def summarize(rows):
    if not rows:
        return {'queries': 0}
    latency = sorted(row['latency_ms'] for row in rows)
    size = len(latency)
    return {'queries': size, 'hit@1': round(statistics.mean(row['metrics']['hit@1'] for row in rows), 4),
            'hit@5': round(statistics.mean(row['metrics']['hit@5'] for row in rows), 4),
            'hit@10': round(statistics.mean(row['metrics']['hit@10'] for row in rows), 4),
            'mrr@10': round(statistics.mean(row['metrics']['mrr@10'] for row in rows), 4),
            'ndcg@10': round(statistics.mean(row['metrics']['ndcg@10'] for row in rows), 4),
            'empty_results': sum(not row['ranked_docs'] for row in rows),
            'mean_unique_docs': round(statistics.mean(row['unique_docs_in_candidates'] for row in rows), 2),
            'search_latency_ms_p50': round(latency[(size - 1) // 2], 1),
            'search_latency_ms_p95': round(latency[math.ceil(size * .95) - 1], 1)}


def summarize_strategy(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row['channel'], row['suite'], 'all')].append(row)
        case = row['case']
        for field in ('language', 'source_set', 'file_format', 'depth'):
            if case.get(field) is not None:
                grouped[(row['channel'], row['suite'], f'{field}:{case[field]}')].append(row)
        if row['suite'] == 'human' and isinstance(case.get('evidence_page'), int):
            group = 'first_page' if case['evidence_page'] == 1 else 'later_page'
            grouped[(row['channel'], row['suite'], f'page:{group}')].append(row)
    return [{'channel': key[0], 'suite': key[1], 'group': key[2], **summarize(value)}
            for key, value in sorted(grouped.items())]


def search(collection, query, vector, channel, candidate_k, expr, ef):
    if channel == 'dense':
        if vector is None:
            raise ValueError('dense search requires a query embedding')
        payload, field = [vector], 'embedding'
        params = {'metric_type': 'COSINE', 'params': {'ef': ef}}
    elif channel == 'bm25':
        payload, field = [query], 'sparse_vector'
        params = {'metric_type': 'BM25'}
    else:
        raise ValueError(f'unknown search channel: {channel}')
    started = time.perf_counter()
    results = collection.search(data=payload, anns_field=field, param=params,
                                limit=candidate_k, expr=expr,
                                output_fields=['doc_id', 'pmcid', 'chunk_index'], timeout=60)
    latency_ms = (time.perf_counter() - started) * 1000
    hits = [{
        'chunk_id': str(hit.id), 'doc_id': str(hit.entity.get('doc_id') or ''),
        'pmcid': str(hit.entity.get('pmcid') or ''),
        'chunk_index': hit.entity.get('chunk_index'), 'score': float(hit.score),
    } for hit in results[0]]
    if any(not hit['doc_id'] for hit in hits):
        raise ValueError('Milvus returned a hit without doc_id')
    return hits, latency_ms


def build_vectors(cases, adapter, dimension, batch_size):
    vectors = {}
    unique = {row['query']: None for row in cases}
    texts = list(unique)
    started = time.perf_counter()
    for offset in range(0, len(texts), batch_size):
        batch = texts[offset:offset + batch_size]
        values = embed_checked(adapter, batch, dimension, retries=3)
        vectors.update(zip(batch, values))
    return vectors, round((time.perf_counter() - started) * 1000, 1)


def evaluate_collection(collection, cases, vectors, args, expr, output):
    requested = set(args.channels)
    need_dense = bool(requested & {'dense', 'hybrid'})
    need_bm25 = bool(requested & {'bm25', 'hybrid'})
    rows = []
    with output.open('w', encoding='utf-8') as stream:
        for index, case in enumerate(cases, 1):
            dense_hits, dense_ms = ([], 0.0)
            bm25_hits, bm25_ms = ([], 0.0)
            if need_dense:
                dense_hits, dense_ms = search(collection, case['query'], vectors[case['query']],
                                              'dense', args.candidate_k, expr, args.ef)
            if need_bm25:
                bm25_hits, bm25_ms = search(collection, case['query'], None,
                                             'bm25', args.candidate_k, expr, args.ef)
            by_channel = {'dense': (dense_hits, dense_ms), 'bm25': (bm25_hits, bm25_ms),
                          'hybrid': (reciprocal_rank_fusion(dense_hits, bm25_hits),
                                     dense_ms + bm25_ms)}
            for channel in args.channels:
                hits, latency_ms = by_channel[channel]
                ranked_docs = collapse_documents(hits, args.top_k)
                row = {
                    'strategy': args.current_strategy, 'collection': collection.name,
                    'channel': channel, 'case_id': case['id'], 'suite': case['suite'],
                    'case': {key: case.get(key) for key in
                             ('language', 'source_set', 'file_format', 'depth', 'evidence_page')},
                    'expected_doc_id': case['expected_doc_id'], 'pmcid': case['pmcid'],
                    'metrics': score_one(ranked_docs, case['expected_doc_id'], args.top_k),
                    'latency_ms': round(latency_ms, 2),
                    'unique_docs_in_candidates': len({hit['doc_id'] for hit in hits}),
                    'ranked_docs': ranked_docs,
                }
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                rows.append(row)
            if index % 25 == 0 or index == len(cases):
                stream.flush()
                print(f'{collection.name}: {index}/{len(cases)} queries', flush=True)
    return rows


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, default=DEFAULT_DATASET)
    parser.add_argument('--strategies', nargs='+', choices=STRATEGIES, default=list(STRATEGIES))
    parser.add_argument('--suite', choices=('human', 'coverage', 'all'), default='all')
    parser.add_argument('--channels', nargs='+', choices=CHANNELS, default=list(CHANNELS))
    parser.add_argument('--collection-prefix', default='papers500')
    parser.add_argument('--tenant-id', default='dev-tenant')
    parser.add_argument('--top-k', type=int, default=10)
    parser.add_argument('--candidate-k', type=int, default=100,
                        help='same chunk candidate budget for each strategy/channel')
    parser.add_argument('--ef', type=int, default=128)
    parser.add_argument('--embedding-batch-size', type=int, default=16)
    parser.add_argument('--load-timeout', type=int, default=180)
    parser.add_argument('--limit', type=int, default=0, help='smoke run: first N selected queries')
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--dry-run', action='store_true', help='validate inputs; no Milvus/API calls')
    args = parser.parse_args(argv)
    if (not re.fullmatch(r'papers500[A-Za-z0-9_]*', args.collection_prefix)
            or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', args.tenant_id)):
        parser.error('invalid collection-prefix or tenant-id')
    if (min(args.top_k, args.candidate_k, args.ef, args.embedding_batch_size,
            args.load_timeout) <= 0 or args.top_k != 10 or args.candidate_k < 10
            or args.limit < 0):
        parser.error('positive limits required; top-k must be 10 and candidate-k >= 10')
    args.strategies = list(dict.fromkeys(args.strategies))
    args.channels = list(dict.fromkeys(args.channels))
    return args


def main(argv=None):
    args = parse_args(argv)
    cases, meta = load_dataset(args.dataset)
    cases = [case for case in cases if args.suite == 'all' or case['suite'] == args.suite]
    if args.limit:
        cases = cases[:args.limit]
    if not cases:
        raise ValueError('selected query set is empty')
    selected = dict(Counter(case['suite'] for case in cases))
    if args.dry_run:
        print(json.dumps({'status': 'validated', 'cases': len(cases), 'by_suite': selected,
                          'strategies': args.strategies, 'channels': args.channels,
                          'test_set_sha256': meta['test_set_sha256']}, ensure_ascii=False, indent=2))
        return

    from dotenv import load_dotenv
    load_dotenv(PROJECT / '.env')
    sys.path.insert(0, str(PROJECT / 'python-ai'))
    from pymilvus import Collection, connections, utility
    needs_dense = any(channel in args.channels for channel in ('dense', 'hybrid'))
    model = os.getenv('EMBEDDING_MODEL', 'BAAI/bge-m3')
    dimension = int(os.getenv('EMBEDDING_DIM', '1024'))
    if needs_dense and not os.getenv('SILICONFLOW_API_KEY', '').strip():
        raise ValueError('dense/hybrid benchmarking requires SILICONFLOW_API_KEY')
    state_dir = PROJECT / 'data/paper_vectors'
    expected_counts = {}
    for strategy in args.strategies:
        state_path = state_dir / f'{args.collection_prefix}_{strategy}.json'
        if not state_path.is_file():
            raise ValueError(f'missing import checkpoint: {state_path}')
        state = json.loads(state_path.read_text(encoding='utf-8'))
        identity = state.get('identity', {})
        source = identity.get('input', {})
        if (state.get('status') != 'completed' or state.get('completed_rows') != source.get('chunks')
                or source.get('papers') != meta['papers']
                or identity.get('version') != meta['knowledge_version']
                or identity.get('tenant_id') != args.tenant_id
                or (needs_dense and (identity.get('model') != model
                                     or identity.get('dimension') != dimension))):
            raise ValueError(f'{strategy} import checkpoint does not match evaluation configuration')
        expected_counts[strategy] = source['chunks']

    output = args.output_dir or PROJECT / 'data/paper_bench' / datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    output = output.resolve()
    if output.exists():
        raise ValueError(f'output directory already exists: {output}')

    connections.connect('default', host=os.getenv('MILVUS_HOST', 'localhost'),
                        port=os.getenv('MILVUS_PORT', '19530'), timeout=15)
    try:
        for strategy in args.strategies:
            name = f'{args.collection_prefix}_{strategy}'
            if not utility.has_collection(name):
                raise ValueError(f'missing collection: {name}')
        vectors, embedding_ms = ({}, 0.0)
        adapter = None
        if needs_dense:
            from app.gateway.adapters.embedding import EmbeddingAdapter
            adapter = EmbeddingAdapter()
            try:
                vectors, embedding_ms = build_vectors(cases, adapter, dimension,
                                                      args.embedding_batch_size)
            finally:
                adapter.client.close()

        output.mkdir(parents=True, exist_ok=False)
        run = {'status': 'running', 'started_at': datetime.now().astimezone().isoformat(),
               'dataset': str(args.dataset.resolve()), 'test_set_sha256': meta['test_set_sha256'],
               'cases': len(cases), 'by_suite': selected, 'limit': args.limit,
               'strategies': args.strategies, 'channels': args.channels,
               'candidate_k': args.candidate_k, 'top_k': args.top_k, 'ef': args.ef,
               'collection_prefix': args.collection_prefix, 'tenant_id': args.tenant_id,
               'embedding_model': model if needs_dense else None,
               'embedding_dim': dimension if needs_dense else None,
               'query_embedding_ms': embedding_ms, 'collections': {}}
        write_json(output / 'run.json', run)
        expr = ('tenant_id == ' + json.dumps(args.tenant_id)
                + ' and knowledge_version == ' + json.dumps(meta['knowledge_version'])
                + ' and chunk_role == "child"')
        try:
            for strategy in args.strategies:
                args.current_strategy = strategy
                name = f'{args.collection_prefix}_{strategy}'
                coll = Collection(name)
                loaded = False
                started = time.perf_counter()
                try:
                    coll.load(timeout=args.load_timeout)
                    loaded = True
                    actual = int(coll.query(expr='', output_fields=['count(*)'], timeout=60)[0]['count(*)'])
                    if actual != expected_counts[strategy]:
                        raise ValueError(f'{name}: expected {expected_counts[strategy]} rows, got {actual}')
                    rows = evaluate_collection(coll, cases, vectors, args, expr,
                                               output / f'{strategy}.jsonl')
                    run['collections'][strategy] = {
                        'collection': name, 'rows': actual, 'elapsed_seconds': round(
                            time.perf_counter() - started, 2),
                        'summary': summarize_strategy(rows),
                    }
                    write_json(output / 'run.json', run)
                finally:
                    if loaded:
                        coll.release(timeout=60)
            run.update(status='completed', finished_at=datetime.now().astimezone().isoformat())
            write_json(output / 'run.json', run)
        except BaseException as exc:
            run.update(status='failed', error_type=type(exc).__name__,
                       finished_at=datetime.now().astimezone().isoformat())
            write_json(output / 'run.json', run)
            raise
        print(json.dumps({'status': run['status'], 'output': str(output),
                          'cases': len(cases), 'collections': list(run['collections'])},
                         ensure_ascii=False, indent=2))
    finally:
        connections.disconnect('default')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        sys.exit(1)
