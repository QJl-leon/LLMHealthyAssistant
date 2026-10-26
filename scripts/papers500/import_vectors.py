#!/usr/bin/env python3
"""Validate exported paper chunks and import them into isolated Milvus collections."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import re
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
STRATEGIES = (
    'baseline', 'fixed_length', 'fixed_symbol',
    'semantic_window', 'semantic_split', 'structured_row',
)
LOGGER = logging.getLogger('paper_vectors')


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def iter_records(path):
    with path.open(encoding='utf-8') as source:
        for line_number, line in enumerate(source, 1):
            if line.strip():
                yield line_number, json.loads(line)


def bounded_text(text, max_bytes, max_chars, policy):
    preview = text[:max_chars].encode('utf-8')[:max_bytes].decode('utf-8', errors='ignore')
    if preview != text and policy == 'error':
        raise ValueError(
            f'超长块：{len(text)} 字符/{len(text.encode("utf-8"))} 字节；'
            '可显式指定 --long-text truncate（会改变检索输入）'
        )
    if not preview.strip():
        raise ValueError('长度限制产生了空文本')
    return preview


def preflight(path, strategy, args):
    """Scan every row before making any API calls or changing Milvus."""
    if path.suffix != '.jsonl' or not path.is_file():
        raise ValueError(f'只接受完整 .jsonl 文件：{path}')
    ids, docs, pmcids = set(), {}, {}
    count = truncated = 0
    for line, record in iter_records(path):
        try:
            for field, limit in (
                ('id', 64), ('doc_id', 64), ('source_id', 64), ('pmcid', 64),
                ('knowledge_version', 32), ('strategy', 32), ('actual_strategy', 32),
            ):
                value = record.get(field)
                if not isinstance(value, str) or not value or len(value.encode('utf-8')) > limit:
                    raise ValueError(f'{field} 缺失或超过 {limit} 字节')
            if record['id'] in ids:
                raise ValueError('块 ID 重复')
            if record['strategy'] != strategy or record['actual_strategy'] not in STRATEGIES:
                raise ValueError('分块策略不符')
            if record['knowledge_version'] != args.version:
                raise ValueError('知识版本不符')
            index = record.get('chunk_index')
            if type(index) is not int or index < 0:
                raise ValueError('chunk_index 必须为非负整数')
            doc_id, pmcid = record['doc_id'], record['pmcid']
            if docs.get(doc_id, (pmcid, 0)) != (pmcid, index):
                raise ValueError('论文块序号不连续、顺序不符或 PMCID 不一致')
            if pmcid in pmcids and pmcids[pmcid] != doc_id:
                raise ValueError('同一 PMCID 对应多个 doc_id')
            text = record.get('text')
            if not isinstance(text, str) or not text.strip() or record.get('characters') != len(text):
                raise ValueError('正文为空或字符统计不符')
            metadata = record.get('metadata')
            if not isinstance(metadata, dict) or metadata.get('pmcid') != pmcid:
                raise ValueError('论文元数据缺失或 PMCID 不符')
            if len(json.dumps(metadata, ensure_ascii=False).encode('utf-8')) > 60000:
                raise ValueError('metadata 超过 60000 字节')
            fallback = record.get('fallback_reason') or ''
            if not isinstance(fallback, str) or len(fallback.encode('utf-8')) > 512:
                raise ValueError('fallback_reason 格式或长度不符')
            preview = bounded_text(text, args.max_text_bytes, args.max_text_chars, args.long_text)
            truncated += preview != text
            ids.add(record['id'])
            docs[doc_id] = (pmcid, index + 1)
            pmcids[pmcid] = doc_id
            count += 1
        except (ValueError, TypeError) as exc:
            raise ValueError(f'{path.name}:{line}: {exc}') from exc
    if len(docs) != args.expected_papers:
        raise ValueError(f'{path.name} 期望 {args.expected_papers} 篇，实际 {len(docs)} 篇')
    with path.open('rb') as source:
        digest = hashlib.file_digest(source, 'sha256').hexdigest()
    return {'path': str(path), 'sha256': digest, 'papers': len(docs), 'chunks': count,
            'truncated_chunks': truncated}


def embed_checked(adapter, texts, dimension, retries):
    for attempt in range(retries + 1):
        try:
            vectors = adapter.embed(texts)
            if len(vectors) != len(texts):
                raise ValueError('Embedding 返回数量不符')
            for vector in vectors:
                if (len(vector) != dimension or not all(math.isfinite(x) for x in vector)
                        or not any(x != 0 for x in vector)):
                    raise ValueError('Embedding 返回维度、数值或零向量无效')
            return vectors
        except Exception as exc:
            if attempt == retries:
                raise RuntimeError(f'Embedding 失败，已尝试 {attempt + 1} 次；停止导入') from exc
            delay = min(2 ** attempt, 30)
            LOGGER.warning('Embedding 批次失败 (%s)，%s 秒后重试', type(exc).__name__, delay)
            time.sleep(delay)


def make_row(record, args, model, dimension):
    text = record['text']
    preview = bounded_text(text, args.max_text_bytes, args.max_text_chars, args.long_text)
    return {
        'id': record['id'], 'doc_id': record['doc_id'], 'source_id': record['source_id'],
        'pmcid': record['pmcid'], 'tenant_id': args.tenant_id, 'source_level': 2,
        'knowledge_version': record['knowledge_version'], 'source_type': 'paper',
        'chunk_role': 'child', 'parent_key': '', 'chunk_index': record['chunk_index'],
        'strategy': record['strategy'], 'actual_strategy': record['actual_strategy'],
        'fallback_reason': record.get('fallback_reason') or '',
        'embedding_model': model, 'embedding_dim': dimension,
        'text': preview, 'text_truncated': preview != text,
        'original_characters': len(text), 'original_bytes': len(text.encode('utf-8')),
        'metadata': record['metadata'],
    }


def create_collection(name, dimension, signature):
    from pymilvus import Collection, CollectionSchema, DataType, FieldSchema, Function, FunctionType
    fields = [FieldSchema('id', DataType.VARCHAR, is_primary=True, max_length=64)]
    for name_, limit in (
        ('doc_id', 64), ('source_id', 64), ('pmcid', 64), ('tenant_id', 64),
        ('knowledge_version', 32), ('source_type', 32), ('chunk_role', 8), ('parent_key', 64),
        ('embedding_model', 128), ('strategy', 32), ('actual_strategy', 32),
        ('fallback_reason', 512),
    ):
        fields.append(FieldSchema(name_, DataType.VARCHAR, max_length=limit))
    fields.append(FieldSchema('source_level', DataType.INT8))
    for name_ in ('embedding_dim', 'chunk_index', 'original_characters', 'original_bytes'):
        fields.append(FieldSchema(name_, DataType.INT64))
    fields.extend([
        FieldSchema('text_truncated', DataType.BOOL),
        FieldSchema('metadata', DataType.JSON),
        FieldSchema('text', DataType.VARCHAR, max_length=8192, enable_analyzer=True,
                    analyzer_params={'type': 'chinese'}),
        FieldSchema('embedding', DataType.FLOAT_VECTOR, dim=dimension),
        FieldSchema('sparse_vector', DataType.SPARSE_FLOAT_VECTOR),
    ])
    schema = CollectionSchema(fields, description=f'papers500:{signature}', enable_dynamic_field=False)
    schema.add_function(Function(name='bm25', function_type=FunctionType.BM25,
                                 input_field_names=['text'], output_field_names=['sparse_vector']))
    return Collection(name, schema)


def finish_indexes(collection):
    collection.create_index('embedding', {
        'index_type': 'HNSW', 'metric_type': 'COSINE',
        'params': {'M': 32, 'efConstruction': 200},
    }, index_name='idx_embedding')
    collection.create_index('sparse_vector', {
        'index_type': 'SPARSE_INVERTED_INDEX', 'metric_type': 'BM25',
    }, index_name='idx_sparse')
    collection.load()


def import_strategy(strategy, info, args, adapter, model, dimension):
    from pymilvus import Collection, utility
    name = f'{args.collection_prefix}_{strategy}'
    checkpoint = args.state_dir / f'{name}.json'
    identity = {
        'format_version': 1, 'input': info, 'collection': name, 'model': model, 'dimension': dimension,
        'version': args.version, 'tenant_id': args.tenant_id, 'long_text': args.long_text,
        'max_text_bytes': args.max_text_bytes, 'max_text_chars': args.max_text_chars,
        'milvus_host': os.getenv('MILVUS_HOST', 'localhost'),
        'milvus_port': os.getenv('MILVUS_PORT', '19530'),
    }
    signature = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    exists = utility.has_collection(name)
    if checkpoint.exists():
        state = json.loads(checkpoint.read_text(encoding='utf-8'))
        if not args.resume or state.get('signature') != signature:
            raise ValueError(f'{checkpoint} 已存在；只有相同输入/配置才能使用 --resume')
        if not exists and state.get('completed_rows', 0):
            raise ValueError(f'{name} 已丢失；不能跳过已导入的块，请使用新集合前缀')
    else:
        if exists:
            raise ValueError(f'{name} 已存在且没有匹配的断点记录，请使用新集合前缀')
        state = {'signature': signature, 'identity': identity, 'completed_rows': 0,
                 'status': 'pending', 'started_at': datetime.now().astimezone().isoformat()}
        write_json(checkpoint, state)
    if exists:
        collection = Collection(name)
        if collection.schema.description != f'papers500:{signature}':
            raise ValueError(f'{name} 的集合签名不符，停止，避免混入其他数据')
    else:
        collection = create_collection(name, dimension, signature)
    completed = state['completed_rows']
    if type(completed) is not int or not 0 <= completed <= info['chunks']:
        raise ValueError('断点行数无效')
    if state['status'] == 'completed':
        if completed != info['chunks']:
            raise ValueError(f'{name} 标记为完成，但断点块数与输入不符')
        LOGGER.info('%s: 已完成 %d 块，续跑时跳过', name, completed)
        return {'collection': name, 'chunks': completed,
                'truncated_chunks': info['truncated_chunks'], 'status': 'completed',
                'checkpoint': str(checkpoint)}
    state['status'] = 'running'
    write_json(checkpoint, state)
    pending = []

    def commit():
        nonlocal completed
        for offset in range(0, len(pending), args.embedding_batch_size):
            batch = pending[offset:offset + args.embedding_batch_size]
            vectors = embed_checked(adapter, [row['text'] for row in batch], dimension, args.retries)
            for row, vector in zip(batch, vectors):
                row['embedding'] = vector
        # Deterministic primary keys make replay safe if interrupted before checkpointing.
        collection.upsert(pending)
        collection.flush()
        completed += len(pending)
        state.update(completed_rows=completed, updated_at=datetime.now().astimezone().isoformat())
        write_json(checkpoint, state)
        LOGGER.info('%s: %d/%d 块已写入', name, completed, info['chunks'])
        pending.clear()

    try:
        for ordinal, (_, record) in enumerate(iter_records(Path(info['path']))):
            if ordinal < completed:
                continue
            pending.append(make_row(record, args, model, dimension))
            if len(pending) == args.insert_batch_size:
                commit()
        if pending:
            commit()
        finish_indexes(collection)
        state.update(status='completed', finished_at=datetime.now().astimezone().isoformat())
        write_json(checkpoint, state)
    except BaseException as exc:
        state.update(status='failed', error_type=type(exc).__name__)
        write_json(checkpoint, state)
        raise
    return {'collection': name, 'chunks': completed, 'truncated_chunks': info['truncated_chunks'],
            'status': state['status'], 'checkpoint': str(checkpoint)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--chunk-dirs', type=Path, nargs='+', required=True,
                        help='分块输出目录；同一策略须只存在一份完整结果')
    parser.add_argument('--strategies', nargs='+', choices=STRATEGIES, default=list(STRATEGIES))
    parser.add_argument('--version', default='kv_20260928_001')
    parser.add_argument('--expected-papers', type=int, default=500)
    parser.add_argument('--collection-prefix', default='papers500')
    parser.add_argument('--tenant-id', default='dev-tenant')
    parser.add_argument('--embedding-batch-size', type=int, default=16)
    parser.add_argument('--insert-batch-size', type=int, default=256)
    parser.add_argument('--retries', type=int, default=3)
    parser.add_argument('--max-text-bytes', type=int, default=8192)
    parser.add_argument('--max-text-chars', type=int, default=6000,
                        help='额外字符上限，非 token 上限；服务端仍会校验模型上下文限制')
    parser.add_argument('--long-text', choices=('error', 'truncate'), default='error')
    parser.add_argument('--state-dir', type=Path, default=PROJECT / 'data/paper_vectors')
    parser.add_argument('--resume', action='store_true')
    parser.add_argument('--dry-run', action='store_true', help='离线校验全部输入，不调用 API、不连接 Milvus')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'papers500[A-Za-z0-9_]*', args.collection_prefix):
        parser.error('集合前缀必须以 papers500 开头，仅含字母、数字、下划线')
    if len(args.collection_prefix) > 200:
        parser.error('集合前缀过长')
    if min(args.expected_papers, args.embedding_batch_size, args.insert_batch_size,
           args.max_text_bytes, args.max_text_chars) <= 0 or args.retries < 0:
        parser.error('篇数、批大小、长度上限必须为正数，retries 不能为负数')
    if args.max_text_bytes > 8192:
        parser.error('max-text-bytes 不能超过集合 text 字段的 8192 字节上限')
    if not args.tenant_id or len(args.tenant_id.encode('utf-8')) > 64:
        parser.error('tenant-id 必须为 1 至 64 字节')
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    args.chunk_dirs = list(dict.fromkeys(path.resolve() for path in args.chunk_dirs))
    args.strategies = list(dict.fromkeys(args.strategies))
    plan = {}
    for strategy in args.strategies:
        candidates = [path / f'{strategy}.jsonl' for path in args.chunk_dirs
                      if (path / f'{strategy}.jsonl').is_file()]
        if len(candidates) != 1:
            raise ValueError(f'{strategy} 需要且只能有一份完整结果，找到 {len(candidates)} 份；'
                             '不读取 .partial 文件')
        info = preflight(candidates[0], strategy, args)
        summary_file = candidates[0].parent / 'summary.json'
        if not summary_file.is_file():
            raise ValueError(f'缺少分块统计文件：{summary_file}')
        summary = json.loads(summary_file.read_text(encoding='utf-8'))
        stats = summary.get('strategies', {}).get(strategy, {})
        if (summary.get('knowledge_version') != args.version or stats.get('status') != 'completed'
                or stats.get('chunks') != info['chunks'] or stats.get('papers') != info['papers']):
            raise ValueError(f'{strategy} 的分块完成状态、篇数、块数或版本与 summary.json 不符')
        plan[strategy] = info
        LOGGER.info('%s: %d 篇/%d 块，需截断 %d 块', strategy, info['papers'],
                    info['chunks'], info['truncated_chunks'])
    if args.dry_run:
        print(json.dumps({'status': 'validated', 'strategies': plan}, ensure_ascii=False, indent=2))
        return
    sys.path.insert(0, str(PROJECT / 'python-ai'))
    from dotenv import load_dotenv
    load_dotenv(PROJECT / '.env')
    if not os.getenv('SILICONFLOW_API_KEY', '').strip():
        raise ValueError('必须配置 SILICONFLOW_API_KEY')
    from app.gateway.adapters.embedding import EmbeddingAdapter
    from pymilvus import connections
    dimension = int(os.getenv('EMBEDDING_DIM', '1024'))
    model = os.getenv('EMBEDDING_MODEL', 'BAAI/bge-m3')
    if dimension <= 0 or not model or len(model.encode('utf-8')) > 128:
        raise ValueError('EMBEDDING_DIM/EMBEDDING_MODEL 配置无效')
    args.state_dir = args.state_dir.resolve()
    args.state_dir.mkdir(parents=True, exist_ok=True)
    connections.connect('default', host=os.getenv('MILVUS_HOST', 'localhost'),
                        port=os.getenv('MILVUS_PORT', '19530'))
    adapter = EmbeddingAdapter()
    try:
        results = [import_strategy(strategy, info, args, adapter, model, dimension)
                   for strategy, info in plan.items()]
        print(json.dumps({'status': 'completed', 'results': results}, ensure_ascii=False, indent=2))
    finally:
        adapter.client.close()
        connections.disconnect('default')


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        LOGGER.error('%s: %s', type(exc).__name__, exc)
        sys.exit(1)
