import os
import logging
from typing import Optional
from pymilvus import connections, Collection, CollectionSchema, FieldSchema, DataType, utility, Function, FunctionType
logger = logging.getLogger(__name__)
MILVUS_HOST = os.getenv('MILVUS_HOST', 'localhost')
MILVUS_PORT = os.getenv('MILVUS_PORT', '19530')
COLLECTION_TEXT = 'evidence_text'
COLLECTION_PAPERS = 'papers_lib'
COLLECTION_IMAGE = 'evidence_image'

def hnsw_index_params() -> dict:
    return {'M': int(os.getenv('INDEX_M', '32')), 'efConstruction': int(os.getenv('INDEX_EF_CONSTRUCTION', '200'))}

def search_ef() -> int:
    return int(os.getenv('INDEX_SEARCH_EF', '128'))

def papers_index_type() -> str:
    return os.getenv('PAPERS_INDEX_TYPE', 'IVF_SQ8')

def papers_index_params() -> dict:
    index_type = papers_index_type()
    if index_type.startswith('IVF'):
        return {'nlist': int(os.getenv('PAPERS_INDEX_NLIST', '512'))}
    return hnsw_index_params()

def papers_search_params() -> dict:
    if papers_index_type().startswith('IVF'):
        return {'metric_type': 'COSINE', 'params': {'nprobe': int(os.getenv('PAPERS_SEARCH_NPROBE', '32'))}}
    return {'metric_type': 'COSINE', 'params': {'ef': search_ef()}}

def embedding_dim() -> int:
    return int(os.getenv('EMBEDDING_DIM', '1024'))

def connect():
    try:
        connections.connect('default', host=MILVUS_HOST, port=MILVUS_PORT)
        logger.info(f'✅ Milvus 已连接 {MILVUS_HOST}:{MILVUS_PORT}')
    except Exception:
        pass

def _create_text_collection(collection_name: str, dense_index: dict, description: str, drop_if_exists: bool=False) -> Collection:
    connect()
    if drop_if_exists and utility.has_collection(collection_name):
        utility.drop_collection(collection_name)
        logger.info(f'已删除旧 Collection: {collection_name}')
    if utility.has_collection(collection_name):
        logger.info(f'Collection {collection_name} 已存在，跳过创建')
        return Collection(collection_name)
    fields = [FieldSchema('id', DataType.VARCHAR, is_primary=True, max_length=64, description='parsed_documents.id'), FieldSchema('doc_id', DataType.VARCHAR, max_length=64), FieldSchema('tenant_id', DataType.VARCHAR, max_length=64, description='租户预过滤'), FieldSchema('source_level', DataType.INT8, description='来源等级预过滤 (1-4)'), FieldSchema('knowledge_version', DataType.VARCHAR, max_length=32, description='知识版本预过滤'), FieldSchema('source_type', DataType.VARCHAR, max_length=32, description='知识库分区预过滤 (guideline / case / metric_catalog / paper)'), FieldSchema('chunk_role', DataType.VARCHAR, max_length=8, description='父子块标记：child 参与召回 / parent 仅做上下文扩展'), FieldSchema('parent_key', DataType.VARCHAR, max_length=64, description='子块指向的父块主键（doc_id:p0），用于命中后扩展上下文'), FieldSchema('embedding_model', DataType.VARCHAR, max_length=64, description='生成该行向量的模型名（亮点3：换模型可追溯、A/B 可归因）'), FieldSchema('embedding_dim', DataType.INT64, description='生成该行向量的维度（与向量字段维度必须一致）'), FieldSchema('text', DataType.VARCHAR, max_length=8192, description='文本内容，BM25 Function 在此字段上', enable_analyzer=True, analyzer_params={'type': 'chinese'}), FieldSchema('embedding', DataType.FLOAT_VECTOR, dim=embedding_dim(), description='Dense 向量（维度随 EMBEDDING_DIM 配置）'), FieldSchema('sparse_vector', DataType.SPARSE_FLOAT_VECTOR, description='BM25 稀疏向量')]
    schema = CollectionSchema(fields, description=description, enable_dynamic_field=False)
    bm25_fn = Function(name='bm25', function_type=FunctionType.BM25, input_field_names=['text'], output_field_names=['sparse_vector'])
    schema.add_function(bm25_fn)
    collection = Collection(collection_name, schema)
    for scalar_field in ['tenant_id', 'source_level', 'knowledge_version', 'source_type', 'chunk_role', 'parent_key']:
        collection.create_index(field_name=scalar_field, index_name=f'idx_{scalar_field}')
    collection.create_index(field_name='embedding', index_params={'index_type': dense_index['index_type'], 'metric_type': 'COSINE', 'params': dense_index['params']}, index_name='idx_embedding')
    collection.create_index(field_name='sparse_vector', index_params={'index_type': 'SPARSE_INVERTED_INDEX', 'metric_type': 'BM25'}, index_name='idx_sparse')
    collection.load()
    logger.info(f"✅ {collection_name} 创建完成（Dense {dense_index['index_type']} + BM25 Sparse）")
    return collection

def create_text_collection(drop_if_exists: bool=False) -> Collection:
    return _create_text_collection(COLLECTION_TEXT, {'index_type': 'HNSW', 'params': hnsw_index_params()}, '文本证据向量 — Dense(BGE-M3) + Sparse(BM25)', drop_if_exists=drop_if_exists)

def create_papers_collection(drop_if_exists: bool=False) -> Collection:
    return _create_text_collection(COLLECTION_PAPERS, {'index_type': papers_index_type(), 'params': papers_index_params()}, '论文语料向量（饮食/运动营养 OA 论文）— Dense(IVF) + Sparse(BM25)', drop_if_exists=drop_if_exists)

def create_image_collection(drop_if_exists: bool=False) -> Optional[Collection]:
    connect()
    if drop_if_exists and utility.has_collection(COLLECTION_IMAGE):
        utility.drop_collection(COLLECTION_IMAGE)
    if utility.has_collection(COLLECTION_IMAGE):
        logger.info(f'Collection {COLLECTION_IMAGE} 已存在，跳过创建')
        return Collection(COLLECTION_IMAGE)
    from app.gateway.adapters.clip import clip_dim
    dim = clip_dim()
    fields = [FieldSchema('id', DataType.VARCHAR, is_primary=True, max_length=64), FieldSchema('doc_id', DataType.VARCHAR, max_length=64), FieldSchema('tenant_id', DataType.VARCHAR, max_length=64), FieldSchema('image_url', DataType.VARCHAR, max_length=1024), FieldSchema('phash', DataType.VARCHAR, max_length=32, description='感知哈希，去重用'), FieldSchema('embedding', DataType.FLOAT_VECTOR, dim=dim, description='多模态图像向量（CLIP_DIM 可配，默认 4096）')]
    schema = CollectionSchema(fields, description=f'图像证据向量 — {dim}-dim', enable_dynamic_field=False)
    collection = Collection(COLLECTION_IMAGE, schema)
    for scalar_field in ['tenant_id', 'phash']:
        collection.create_index(field_name=scalar_field, index_name=f'idx_{scalar_field}')
    hnsw = hnsw_index_params()
    collection.create_index(field_name='embedding', index_params={'index_type': 'HNSW', 'metric_type': 'COSINE', 'params': hnsw}, index_name='idx_embedding')
    collection.load()
    logger.info(f'✅ {COLLECTION_IMAGE} 创建完成（{dim}-dim HNSW + pHash）')
    return collection

def _load_parsed_docs(knowledge_version: str, papers: bool) -> list[dict]:
    from app.factory.repository import DATABASE_URL
    import psycopg2
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor(cursor_factory=RealDictCursor)
    kind_filter = "kind = 'paper'" if papers else "kind != 'paper'"
    cur.execute(f'SELECT id, source_id, kind, content, content_hash, knowledge_version\n            FROM parsed_documents\n            WHERE knowledge_version = %s AND {kind_filter}', (knowledge_version,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    parsed_docs = []
    for row in rows:
        parsed_docs.append({'id': str(row['id']), 'source_id': str(row['source_id']), 'source_level': row.get('source_level', 1) or 1, 'knowledge_version': row.get('knowledge_version') or '', 'content': row['content']})
    return parsed_docs

def _chunk_embed_insert(coll: Collection, collection_name: str, parsed_docs: list[dict], strategy: str, use_parent_child: bool) -> dict:
    from collections import Counter
    from app.retrieval.chunker import build_index_chunks, chunks_to_index_rows
    if not parsed_docs:
        logger.warning('[Index] %s 无待索引文档（parsed_documents 为空）', collection_name)
        return {'collection': collection_name, 'count': 0, 'parent_count': 0, 'child_count': 0, 'parent_child_enabled': use_parent_child, 'strategies': []}
    embedder = None
    try:
        from app.gateway.adapters.embedding import EmbeddingAdapter
        embedder = EmbeddingAdapter()
    except Exception as e:
        logger.warning('[Index] Embedding 适配器不可用，语义切分将回退窗口切分: %s', e)

    def _embed_fn(texts):
        if embedder is None:
            raise RuntimeError('embedding adapter unavailable')
        return embedder.embed([t if t and t.strip() else ' ' for t in texts])
    chunks, parents = build_index_chunks(parsed_docs, strategy=strategy, embed_fn=_embed_fn, use_parent_child=use_parent_child)
    strategies = sorted({c.strategy for c in chunks})
    roles = Counter((c.role for c in chunks))
    logger.info('[Index] %s chunking 完成: %d chunks（父块 %d / 子块 %d，策略: %s）', collection_name, len(chunks), roles.get('parent', 0), roles.get('child', 0), strategies)
    if use_parent_child:
        logger.info('[Index] 父子块已启用: %d 个父块（不参与召回，仅命中后扩展上下文）', len(parents))
    batch = chunks_to_index_rows(chunks, tenant_id='dev-tenant', dim=embedding_dim())
    for row, c in zip(batch, chunks):
        row['source_type'] = (c.source_type or '')[:32]
    embed_bs = 32
    done = 0
    failed_batches = 0
    for i in range(0, len(batch), embed_bs):
        chunk = batch[i:i + embed_bs]
        texts = [b['text'] if b['text'].strip() else ' ' for b in chunk]
        try:
            vectors = _embed_fn(texts)
        except Exception as e:
            logger.warning('[Index] Embedding 批次失败（跳过该批，保留零向量）: %s', e)
            vectors = None
            failed_batches += 1
        if not vectors or len(vectors) != len(chunk):
            logger.warning('Embedding 返回数量不符（%s != %d），该批保留零向量', None if not vectors else len(vectors), len(chunk))
        else:
            got_dim = len(vectors[0])
            if got_dim != embedding_dim():
                raise ValueError(f'Embedding 维度不一致：模型实际输出 {got_dim} 维，而配置 EMBEDDING_DIM={embedding_dim()}。切换模型后必须同步 EMBEDDING_DIM 并重建索引。')
            for b, vec in zip(chunk, vectors):
                b['embedding'] = vec
        done += len(chunk)
        if done % 512 == 0 or done == len(batch):
            logger.info('[%s] Embedding 进度: %d/%d（失败批次 %d）', collection_name, done, len(batch), failed_batches)
    zero_vectors = sum((1 for b in batch if not b.get('embedding')))
    if zero_vectors:
        logger.warning('[Index] %d/%d 条仍为零向量（Embedding 未成功），Dense 召回会受影响', zero_vectors, len(batch))
    insert_bs = 500
    for i in range(0, len(batch), insert_bs):
        chunk_rows = batch[i:i + insert_bs]
        for r in chunk_rows:
            r.pop('sparse_vector', None)
        coll.insert(chunk_rows)
    coll.flush()
    logger.info(f'索引重建完成: {len(batch)} 条 → {collection_name}')
    return {'collection': collection_name, 'count': len(batch), 'parent_count': roles.get('parent', 0), 'child_count': roles.get('child', 0), 'parent_child_enabled': use_parent_child, 'strategies': strategies}

def rebuild_from_pg(knowledge_version: str, strategy: str='auto', use_parent_child: bool=True) -> dict:
    parsed_docs = _load_parsed_docs(knowledge_version, papers=False)
    logger.info('[Index] evidence_text 待索引文档 %d 条（健康知识条目）', len(parsed_docs))
    text_coll = create_text_collection(drop_if_exists=True)
    if text_coll is None:
        return {'error': 'text collection not found'}
    return _chunk_embed_insert(text_coll, COLLECTION_TEXT, parsed_docs, strategy, use_parent_child)

def rebuild_papers_from_pg(knowledge_version: str, strategy: str='auto', use_parent_child: bool=True) -> dict:
    parsed_docs = _load_parsed_docs(knowledge_version, papers=True)
    logger.info('[Index] papers_lib 待索引文档 %d 篇（OA 论文）', len(parsed_docs))
    papers_coll = create_papers_collection(drop_if_exists=True)
    if papers_coll is None:
        return {'error': 'papers collection not found'}
    return _chunk_embed_insert(papers_coll, COLLECTION_PAPERS, parsed_docs, strategy, use_parent_child)

def fetch_parent_texts(keys: list[str], tenant_id: str='dev-tenant') -> dict[str, str]:
    if not keys:
        return {}
    try:
        connect()
        quoted = ', '.join((f'"{k}"' for k in sorted(set(keys)) if k))
        if not quoted:
            return {}
        out: dict[str, str] = {}
        for coll_name in (COLLECTION_TEXT, COLLECTION_PAPERS):
            try:
                coll = Collection(coll_name)
                coll.load()
            except Exception as e:
                logger.warning('[Index] 集合 %s 不可用（跳过父块取回）: %s', coll_name, e)
                continue
            rows = coll.query(expr=f'id in [{quoted}] and tenant_id == "{tenant_id}"', output_fields=['id', 'text'])
            out.update({str(r['id']): str(r.get('text', '')) for r in rows})
        return out
    except Exception as e:
        logger.warning('[Index] 父块取回失败（本次不做上下文扩展）: %s', e)
        return {}

def rebuild_image_index(image_entries: list[dict]) -> dict:
    image_coll = create_image_collection()
    if image_coll is None:
        return {'error': 'image collection not found'}
    if not image_entries:
        return {'collection': COLLECTION_IMAGE, 'count': 0}
    try:
        from app.gateway.adapters.clip import CLIPAdapter
        clip = CLIPAdapter()
        embeddings = []
        for entry in image_entries:
            path = str(entry.get('image_path', '') or '')
            url = str(entry.get('image_url', '') or '')
            if path:
                with open(path, 'rb') as f:
                    data = f.read()
                ct = 'image/png' if path.lower().endswith('.png') else 'image/jpeg'
                embeddings.append(clip.embed_image(data, ct))
            elif url:
                embeddings.append(clip.embed_url(url))
            else:
                raise ValueError(f"图片条目缺少 image_path / image_url: {entry.get('id')}")
        logger.info('[ImageIndex] 图像向量化完成: %d 张（dim=%s）', len(embeddings), len(embeddings[0]) if embeddings else 0)
    except Exception as e:
        logger.error('[ImageIndex] 图像向量化失败，本次不写入索引（避免零向量污染）: %s', e)
        return {'collection': COLLECTION_IMAGE, 'count': 0, 'error': str(e)}
    batch = []
    for entry, emb in zip(image_entries, embeddings):
        batch.append({'id': entry['id'], 'doc_id': entry.get('doc_id', ''), 'tenant_id': entry.get('tenant_id', 'dev-tenant'), 'image_url': entry.get('image_url', ''), 'phash': entry.get('phash', ''), 'embedding': emb})
    image_coll.insert(batch)
    image_coll.flush()
    logger.info('✅ 图像索引重建完成: %d 张 → %s', len(batch), COLLECTION_IMAGE)
    return {'collection': COLLECTION_IMAGE, 'count': len(batch)}

def rebuild_image_index_from_dir(images_dir: str, tenant_id: str='dev-tenant') -> dict:
    import glob
    import hashlib
    files: list[str] = []
    for ext in ('*.png', '*.jpg', '*.jpeg'):
        files.extend(glob.glob(os.path.join(images_dir, ext)))
    files.sort()
    entries = []
    for p in files:
        with open(p, 'rb') as f:
            digest = hashlib.sha256(f.read()).hexdigest()[:32]
        entries.append({'id': f'img_{digest}', 'doc_id': os.path.basename(p), 'image_path': p, 'tenant_id': tenant_id, 'phash': digest[:16]})
    logger.info('[ImageIndex] 目录 %s 发现 %d 张图片', images_dir, len(entries))
    return rebuild_image_index(entries)
if __name__ == '__main__':
    import argparse
    import sys
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    parser = argparse.ArgumentParser(description='Milvus 索引构建')
    parser.add_argument('--rebuild', action='store_true', help='从 PG 全量重建文本索引（evidence_text + papers_lib 两表）')
    parser.add_argument('--papers-only', action='store_true', help='只重建论文库 papers_lib（调参后快速重跑用）')
    parser.add_argument('--version', type=str, default='', help='知识版本号（默认取当前发布版）')
    parser.add_argument('--strategy', type=str, default='auto', help='chunk 策略：auto / evidence_row / semantic_split / semantic_window（亮点2）')
    parser.add_argument('--flat', action='store_true', help='关闭父子块（退化为单层 chunk，用于 A/B 对照）')
    parser.add_argument('--rebuild-images', action='store_true', help='从图片目录重建图像索引（Image 召回通道）')
    parser.add_argument('--images-dir', type=str, default='tests/fixtures/report_images', help='图片目录（--rebuild-images 时使用）')
    args = parser.parse_args()
    if args.rebuild_images:
        logger.info('重建图像索引 images_dir=%s', args.images_dir)
        result = rebuild_image_index_from_dir(args.images_dir)
        logger.info('完成: %s', result)
        sys.exit(1 if result.get('error') else 0)
    if not args.rebuild and (not args.papers_only):
        parser.print_help()
        sys.exit(0)
    version = args.version
    if not version:
        from app.factory.repository import get_current_version
        kv = get_current_version()
        if not kv:
            logger.error('无已发布知识版本，请先 version publish')
            sys.exit(1)
        version = kv.version
    logger.info('重建索引 knowledge_version=%s strategy=%s 父子块=%s', version, args.strategy, 'off' if args.flat else 'on')
    if args.papers_only:
        result = rebuild_papers_from_pg(version, strategy=args.strategy, use_parent_child=not args.flat)
        logger.info('完成: %s', result)
        sys.exit(1 if result.get('error') else 0)
    results = [rebuild_from_pg(version, strategy=args.strategy, use_parent_child=not args.flat), rebuild_papers_from_pg(version, strategy=args.strategy, use_parent_child=not args.flat)]
    logger.info('完成: %s', results)
    sys.exit(1 if any((r.get('error') for r in results)) else 0)
