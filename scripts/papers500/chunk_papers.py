#!/usr/bin/env python3
"""Chunk the verified paper export with the project's six experiment strategies."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
WORKSPACE = PROJECT.parent
STRATEGIES = (
    'baseline', 'fixed_length', 'fixed_symbol',
    'semantic_window', 'semantic_split', 'structured_row',
)
LOGGER = logging.getLogger('chunk_papers')


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def load_papers(path, version, expected):
    docs = []
    ids, pmcids = set(), set()
    with path.open(encoding='utf-8') as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            doc = json.loads(line)
            content = doc.get('content', {})
            if doc.get('knowledge_version') != version:
                raise ValueError(f'第 {line_number} 行知识版本不符')
            if content.get('kind') != 'paper' or not isinstance(content.get('raw_text'), str):
                raise ValueError(f'第 {line_number} 行不是解析后的论文正文')
            if not content['raw_text'].strip():
                raise ValueError(f'第 {line_number} 行正文为空')
            doc_id, pmcid = doc.get('id'), content.get('pmcid')
            if not doc_id or not pmcid or doc_id in ids or pmcid in pmcids:
                raise ValueError(f'第 {line_number} 行 ID/PMCID 缺失或重复')
            actual_hash = hashlib.md5(
                json.dumps(content, sort_keys=True, ensure_ascii=False).encode()
            ).hexdigest()
            if doc.get('content_hash') != actual_hash:
                raise ValueError(f'第 {line_number} 行正文内容哈希不符')
            ids.add(doc_id)
            pmcids.add(pmcid)
            docs.append(doc)
    if len(docs) != expected:
        raise ValueError(f'期望 {expected} 篇，实际 {len(docs)} 篇；停止，避免误用不完整数据')
    return sorted(docs, key=lambda doc: doc['content']['pmcid'])


class SemanticEmbedder:
    """Track API failures that the existing semantic splitter catches internally."""

    def __init__(self, batch_size):
        from app.gateway.adapters.embedding import EmbeddingAdapter
        self.adapter = EmbeddingAdapter()
        self.batch_size = batch_size
        self.dimension = int(os.getenv('EMBEDDING_DIM', '1024'))
        self.calls = 0
        self.reason = None

    def reset(self):
        self.calls = 0
        self.reason = None

    def __call__(self, texts):
        result = []
        try:
            for offset in range(0, len(texts), self.batch_size):
                batch = texts[offset:offset + self.batch_size]
                self.calls += 1
                vectors = self.adapter.embed(batch)
                if len(vectors) != len(batch) or any(
                    len(vector) != self.dimension
                    or not all(math.isfinite(value) for value in vector)
                    or not any(value != 0 for value in vector)
                    for vector in vectors
                ):
                    raise ValueError('Embedding 返回的数量、维度或数值无效')
                result.extend(vectors)
        except Exception as exc:
            self.reason = type(exc).__name__
            raise
        return result


def make_chunks(strategy, doc, args, functions, embedder):
    content = doc['content']
    text = content['raw_text'].strip()
    actual_strategy, fallback = strategy, None
    if strategy == 'baseline':
        pieces = [text[:args.chunk_size] if args.baseline_mode == 'truncate' else text]
    elif strategy == 'structured_row':
        metadata = '\n'.join(
            f'{key}: {content[key]}'
            for key in ('pmcid', 'title', 'journal', 'year', 'topic', 'doi', 'license')
            if content.get(key) is not None and str(content[key]).strip()
        )
        pieces = [metadata + '\n\n' + text]
    elif strategy == 'semantic_split':
        embedder.reset()
        pieces = functions[strategy](
            text, embed_fn=embedder, chunk_size=args.chunk_size,
            overlap=args.overlap, threshold=args.semantic_threshold,
            min_fill=args.semantic_min_fill,
        )
        if embedder.reason:
            fallback = 'embedding_error:' + embedder.reason
            if args.semantic_fallback == 'error':
                raise RuntimeError(
                    f"{content['pmcid']} 语义向量请求失败；未将回退结果标记为成功。"
                    '可修复 API 后重跑，或显式使用 --semantic-fallback window。'
                )
        elif len(text) > args.chunk_size and embedder.calls == 0:
            fallback = 'insufficient_sentence_segments'
        if fallback:
            actual_strategy = 'semantic_window'
    else:
        pieces = functions[strategy](
            text, chunk_size=args.chunk_size,
            overlap=args.overlap if strategy == 'semantic_window' else 0,
        )
    if not pieces or any(not piece.strip() for piece in pieces):
        raise ValueError(f"{content['pmcid']} 的 {strategy} 生成空块")
    return pieces, actual_strategy, fallback


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=WORKSPACE/'实验2_解析结果/parsed_papers.jsonl')
    parser.add_argument('--version', default='kv_20260928_001')
    parser.add_argument('--expected-papers', type=int, default=500)
    parser.add_argument('--limit', type=int, default=0, help='校验全量输入后取前 N 篇；0 为全部')
    parser.add_argument('--strategies', nargs='+', choices=STRATEGIES, default=list(STRATEGIES))
    parser.add_argument('--chunk-size', type=int, default=400, help='字符数，不是 token 数')
    parser.add_argument('--overlap', type=int, default=64, help='仅窗口/语义策略使用')
    parser.add_argument('--baseline-mode', choices=('truncate', 'full'), default='truncate')
    parser.add_argument('--semantic-threshold', type=float, default=0.55)
    parser.add_argument('--semantic-min-fill', type=float, default=0.35)
    parser.add_argument('--embedding-batch-size', type=int, default=16)
    parser.add_argument('--semantic-fallback', choices=('error', 'window'), default='error')
    parser.add_argument('--output-dir', type=Path, help='必须是不存在的新目录')
    args = parser.parse_args()
    if args.chunk_size <= 0 or not 0 <= args.overlap < args.chunk_size:
        parser.error('要求 chunk-size > 0，且 0 <= overlap < chunk-size')
    if args.expected_papers <= 0 or args.limit < 0 or args.embedding_batch_size <= 0:
        parser.error('expected-papers/batch-size 必须为正数，limit 不能为负数')
    if not -1 <= args.semantic_threshold <= 1 or not 0 <= args.semantic_min_fill <= 1:
        parser.error('threshold 范围为 [-1,1]，min-fill 范围为 [0,1]')
    args.strategies = list(dict.fromkeys(args.strategies))
    # Load configuration before importing project modules that read environment variables.
    sys.path.insert(0, str(PROJECT/'python-ai'))
    from dotenv import load_dotenv
    load_dotenv(PROJECT/'.env')
    from app.retrieval.chunk_strategies import TEXT_STRATEGIES

    needs_embedding = 'semantic_split' in args.strategies
    if needs_embedding and not os.getenv('SILICONFLOW_API_KEY', '').strip():
        parser.error('semantic_split 需要 .env 中的 SILICONFLOW_API_KEY')
    docs = load_papers(args.input, args.version, args.expected_papers)
    if args.limit:
        docs = docs[:args.limit]
    output = args.output_dir or PROJECT/'data/paper_chunks'/datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    output.mkdir(parents=True, exist_ok=False)
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s',
                        handlers=[logging.StreamHandler(), logging.FileHandler(output/'run.log')])
    with args.input.open('rb') as source:
        input_hash = hashlib.file_digest(source, 'sha256').hexdigest()
    config = {
        'chunk_size': args.chunk_size, 'overlap': args.overlap,
        'baseline_mode': args.baseline_mode, 'semantic_threshold': args.semantic_threshold,
        'semantic_min_fill': args.semantic_min_fill, 'semantic_fallback': args.semantic_fallback,
        'embedding_batch_size': args.embedding_batch_size,
        'embedding_model': os.getenv('EMBEDDING_MODEL', 'BAAI/bge-m3') if needs_embedding else None,
        'embedding_dim': int(os.getenv('EMBEDDING_DIM', '1024')) if needs_embedding else None,
    }
    signature = hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    summary = {
        'status': 'running', 'started_at': datetime.now().astimezone().isoformat(),
        'input': str(args.input.resolve()), 'input_sha256': input_hash,
        'knowledge_version': args.version, 'validated_papers': args.expected_papers,
        'selected_papers': len(docs), 'requested_strategies': args.strategies,
        'config': config, 'strategies': {},
    }
    write_json(output/'summary.json', summary)
    embedder = None
    try:
        embedder = SemanticEmbedder(args.embedding_batch_size) if needs_embedding else None
        for strategy in args.strategies:
            started = time.monotonic()
            stats = dict(status='running', papers=0, chunks=0, total_characters=0,
                         min_characters=None, max_characters=0, over_chunk_size=0,
                         fallback_papers=0, embedding_batch_calls=0)
            summary['strategies'][strategy] = stats
            temporary = output/f'{strategy}.jsonl.partial'
            with temporary.open('w', encoding='utf-8') as target, (
                output/f'{strategy}_papers.jsonl'
            ).open('w', encoding='utf-8') as paper_output:
                for doc in docs:
                    pieces, actual, fallback = make_chunks(strategy, doc, args, TEXT_STRATEGIES, embedder)
                    metadata = {key: value for key, value in doc['content'].items() if key != 'raw_text'}
                    for index, piece in enumerate(pieces):
                        key = f"{signature}:{strategy}:{doc['id']}:{doc['content_hash']}:{index}:{piece}"
                        record = {
                            'id': hashlib.sha256(key.encode()).hexdigest(), 'doc_id': doc['id'],
                            'source_id': doc.get('source_id', ''), 'pmcid': metadata['pmcid'],
                            'knowledge_version': args.version, 'strategy': strategy,
                            'actual_strategy': actual, 'fallback_reason': fallback,
                            'chunk_index': index, 'text': piece, 'characters': len(piece),
                            'metadata': metadata,
                        }
                        target.write(json.dumps(record, ensure_ascii=False)+'\n')
                        stats['chunks'] += 1
                        stats['total_characters'] += len(piece)
                        stats['min_characters'] = min(stats['min_characters'] or len(piece), len(piece))
                        stats['max_characters'] = max(stats['max_characters'], len(piece))
                        stats['over_chunk_size'] += int(len(piece) > args.chunk_size)
                    stats['papers'] += 1
                    stats['fallback_papers'] += int(fallback is not None)
                    if strategy == 'semantic_split':
                        stats['embedding_batch_calls'] += embedder.calls
                    paper_output.write(json.dumps({
                        'doc_id': doc['id'], 'pmcid': metadata['pmcid'], 'chunks': len(pieces),
                        'actual_strategy': actual, 'fallback_reason': fallback,
                    }, ensure_ascii=False)+'\n')
                    if stats['papers'] % 10 == 0 or stats['papers'] == len(docs):
                        LOGGER.info('%s: %d/%d papers, %d chunks', strategy, stats['papers'], len(docs), stats['chunks'])
                        write_json(output/'summary.json', summary)
            temporary.replace(output/f'{strategy}.jsonl')
            stats.update(status='completed', elapsed_seconds=round(time.monotonic()-started, 3),
                         mean_characters=round(stats['total_characters']/stats['chunks'], 2))
            write_json(output/'summary.json', summary)
        summary['status'] = 'completed'
    except BaseException as exc:
        summary['status'] = 'interrupted' if isinstance(exc, KeyboardInterrupt) else 'failed'
        summary['error_type'] = type(exc).__name__
        for stats in summary['strategies'].values():
            if stats['status'] == 'running':
                stats['status'] = summary['status']
        raise
    finally:
        summary['finished_at'] = datetime.now().astimezone().isoformat()
        write_json(output/'summary.json', summary)
        if embedder is not None:
            embedder.adapter.client.close()
    print(f'完成：{output.resolve()}')


if __name__ == '__main__':
    main()
