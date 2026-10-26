from app.observability.runtime import timed
import os
import logging
import json
from typing import Optional
from pymilvus import Collection
logger = logging.getLogger(__name__)
MILVUS_HOST = os.getenv('MILVUS_HOST', 'localhost')
MILVUS_PORT = os.getenv('MILVUS_PORT', '19530')
TENANT_ID = os.getenv('TENANT_ID', 'dev-tenant')
CACHE_TTL_RETRIEVAL = int(os.getenv('CACHE_TTL_RETRIEVAL', '3600'))

def _result_to_cache(r: 'ChannelResult') -> dict:
    return {'channel': r.channel, 'doc_ids': r.doc_ids, 'scores': r.scores, 'snippets': r.snippets, 'metadata': r.metadata}

def _cache_to_result(d: dict) -> 'ChannelResult':
    return ChannelResult(channel=d.get('channel', ''), doc_ids=d.get('doc_ids', []), scores=d.get('scores', []), snippets=d.get('snippets', []), metadata=d.get('metadata', []), latency_ms=0.0)

def _append_source_type_expr(expr_parts: list[str], source_types: Optional[list[str]]) -> None:
    values = [str(s).strip() for s in source_types or [] if str(s).strip()]
    if not values:
        return
    quoted = ', '.join((f'"{v}"' for v in values))
    expr_parts.append(f'source_type in [{quoted}]')

def _append_role_expr(expr_parts: list[str]) -> None:
    expr_parts.append('chunk_role == "child"')
COLLECTION_TEXT = 'evidence_text'
COLLECTION_PAPERS = 'papers_lib'

def _resolve_collections(source_types: Optional[list[str]]) -> list[tuple[str, Optional[list[str]]]]:
    values = [str(s).strip() for s in source_types or [] if str(s).strip()]
    if not values:
        return [(COLLECTION_TEXT, None), (COLLECTION_PAPERS, None)]
    if 'paper' not in values:
        return [(COLLECTION_TEXT, values)]
    others = [v for v in values if v != 'paper']
    if not others:
        return [(COLLECTION_PAPERS, ['paper'])]
    return [(COLLECTION_TEXT, others), (COLLECTION_PAPERS, ['paper'])]

def _interleave_results(per_route: list[tuple[list, list, list, list]]) -> tuple[list, list, list, list]:
    docs: list = []
    scores: list = []
    snippets: list = []
    meta: list = []
    iters = [iter(zip(d, s, sn, m)) for d, s, sn, m in per_route if d]
    while iters:
        for it in list(iters):
            try:
                did, sc, sn, mt = next(it)
            except StopIteration:
                iters.remove(it)
                continue
            docs.append(did)
            scores.append(sc)
            snippets.append(sn)
            meta.append(mt)
    return (docs, scores, snippets, meta)

def _channel_cache_sig(channel: str, source_types: Optional[list[str]]) -> str:
    values = sorted((str(s).strip() for s in source_types or [] if str(s).strip()))
    parts = [channel] + values + [name for name, _ in _resolve_collections(values)]
    return '|'.join(parts)
from dataclasses import dataclass, field

@dataclass
class ChannelResult:
    channel: str
    doc_ids: list[str] = field(default_factory=list)
    scores: list[float] = field(default_factory=list)
    snippets: list[str] = field(default_factory=list)
    metadata: list[dict] = field(default_factory=list)
    latency_ms: float = 0.0

def search_bm25(query: str, top_k: int=20, knowledge_version: Optional[str]=None, source_types: Optional[list[str]]=None) -> ChannelResult:
    import time
    start = time.time()
    from app.cache import get_cache, retrieval_key
    cache = get_cache()
    ckey = retrieval_key(query, TENANT_ID, knowledge_version or '', _channel_cache_sig('bm25', source_types), top_k) if cache.enabled else None
    if ckey:
        hit = cache.get(ckey)
        if hit is not None:
            logger.info('[BM25] 缓存命中 query=%s', query[:30])
            return _cache_to_result(hit)
    try:
        from app.retrieval.index_builder import connect
        connect()
    except Exception as e:
        logger.warning('[BM25] Milvus 连接失败: %s', e)
        return ChannelResult(channel='bm25', latency_ms=(time.time() - start) * 1000)
    routes = _resolve_collections(source_types)
    per_route: list[tuple[list, list, list, list]] = []
    for coll_name, types_filter in routes:
        try:
            coll = Collection(coll_name)
            coll.load()
        except Exception as e:
            logger.warning('[BM25] 集合 %s 不可用（跳过）: %s', coll_name, e)
            continue
        try:
            per_route.append(_bm25_fulltext(coll, query, top_k, knowledge_version, types_filter))
        except Exception as e:
            logger.warning('[BM25] %s 全文检索失败，回退 LIKE: %s', coll_name, e)
            fb = _search_bm25_fallback(coll, query, top_k, knowledge_version, start, types_filter)
            if fb.snippets:
                per_route.append((fb.doc_ids, fb.scores, fb.snippets, fb.metadata))
    docs, scores, snippets, meta = _interleave_results(per_route)
    logger.info('[BM25] 全文检索 BM25 命中 %d 条（分区=%s，集合=%s）', len(docs), source_types or '全部', [n for n, _ in routes])
    result = ChannelResult(channel='bm25', doc_ids=docs, scores=scores, snippets=snippets, metadata=meta, latency_ms=(time.time() - start) * 1000)
    if ckey and result.snippets:
        cache.set(ckey, _result_to_cache(result), ttl=CACHE_TTL_RETRIEVAL)
    return result

def _bm25_fulltext(coll: Collection, query: str, top_k: int, knowledge_version: Optional[str], source_types: Optional[list[str]]) -> tuple[list, list, list, list]:
    expr_parts = [f'tenant_id == "{TENANT_ID}"']
    if knowledge_version:
        expr_parts.append(f'knowledge_version == "{knowledge_version}"')
    _append_source_type_expr(expr_parts, source_types)
    _append_role_expr(expr_parts)
    expr = ' and '.join(expr_parts)
    results = coll.search(data=[query], anns_field='sparse_vector', param={'metric_type': 'BM25'}, limit=top_k, expr=expr, output_fields=['text', 'doc_id', 'source_level', 'knowledge_version', 'source_type', 'parent_key'])
    docs, scores, snippets, meta = ([], [], [], [])
    for hits in results:
        for h in hits:
            docs.append(h.id)
            scores.append(h.score)
            snippets.append(str(h.entity.get('text', ''))[:200])
            meta.append({'source_level': h.entity.get('source_level'), 'knowledge_version': h.entity.get('knowledge_version'), 'source_type': h.entity.get('source_type'), 'parent_key': h.entity.get('parent_key') or ''})
    return (docs, scores, snippets, meta)

def _search_bm25_fallback(coll: Collection, query: str, top_k: int, knowledge_version: Optional[str], start: float, source_types: Optional[list[str]]=None) -> ChannelResult:
    import time
    expr_parts = [f'tenant_id == "{TENANT_ID}"']
    if knowledge_version:
        expr_parts.append(f'knowledge_version == "{knowledge_version}"')
    _append_source_type_expr(expr_parts, source_types)
    _append_role_expr(expr_parts)
    keywords = [w for w in query.replace('参考区间', '').replace('指标', '').replace('正常', '').replace('偏高', '').strip().split() if len(w) >= 2]
    if not keywords:
        keywords = [query.strip()]
    expr_parts.append(' or '.join([f'text like "%{kw}%"' for kw in keywords[:5]]))
    expr = ' and '.join(expr_parts)
    try:
        results = coll.query(expr=expr, output_fields=['text', 'doc_id', 'source_level', 'knowledge_version', 'source_type', 'parent_key'], limit=top_k)
    except Exception as e:
        logger.warning('[BM25] Milvus query 失败: %s', e)
        return ChannelResult(channel='bm25', latency_ms=(time.time() - start) * 1000)
    docs, scores, snippets, meta = ([], [], [], [])
    for r in results:
        docs.append(r.get('id', ''))
        score = sum((1.0 for kw in keywords if kw in r.get('text', '')))
        scores.append(score)
        snippets.append(str(r.get('text', ''))[:200])
        meta.append({'source_level': r.get('source_level'), 'knowledge_version': r.get('knowledge_version'), 'source_type': r.get('source_type'), 'parent_key': r.get('parent_key') or ''})
    logger.info('[BM25] LIKE 回退命中 %d 条', len(docs))
    return ChannelResult(channel='bm25', doc_ids=docs, scores=scores, snippets=snippets, metadata=meta, latency_ms=(time.time() - start) * 1000)

def search_dense(query: str, embedding: Optional[list[float]]=None, top_k: int=20, knowledge_version: Optional[str]=None, use_hyde: bool=False, source_types: Optional[list[str]]=None) -> ChannelResult:
    import time
    start = time.time()
    from app.cache import get_cache, retrieval_key
    cache = get_cache()
    ckey = retrieval_key(query, TENANT_ID, knowledge_version or '', _channel_cache_sig('dense', source_types), top_k) if cache.enabled else None
    if ckey:
        hit = cache.get(ckey)
        if hit is not None:
            logger.info('[Dense] 缓存命中 query=%s', query[:30])
            return _cache_to_result(hit)
    if embedding is None or all((v == 0.0 for v in embedding)):
        from app.retrieval.hyde import HYDE_DEFAULT_ON, build_hyde_query, should_use_hyde
        embed_text = query
        used_hyde = False
        if use_hyde or (HYDE_DEFAULT_ON and should_use_hyde(query)):
            embed_text = build_hyde_query(query)
            used_hyde = embed_text != query
        try:
            from app.gateway.adapters.embedding import EmbeddingAdapter
            embedder = EmbeddingAdapter()
            vectors = embedder.embed([embed_text])
            embedding = vectors[0]
            logger.info('[Dense] 查询已向量化 dim=%d%s', len(embedding), ' (HyDE)' if used_hyde else '')
        except Exception as e:
            logger.warning('[Dense] Embedding 失败，本通道降级为空结果: %s', e)
            return ChannelResult(channel='dense', latency_ms=(time.time() - start) * 1000)
    if not embedding or all((v == 0.0 for v in embedding)):
        logger.warning('[Dense] 无效查询向量，跳过检索')
        return ChannelResult(channel='dense', latency_ms=(time.time() - start) * 1000)
    try:
        from app.retrieval.index_builder import connect
        connect()
    except Exception as e:
        logger.warning('[Dense] Milvus 连接失败: %s', e)
        return ChannelResult(channel='dense', latency_ms=(time.time() - start) * 1000)
    from app.retrieval.index_builder import papers_search_params, search_ef
    routes = _resolve_collections(source_types)
    per_route: list[tuple[list, list, list, list]] = []
    for coll_name, types_filter in routes:
        try:
            coll = Collection(coll_name)
            coll.load()
        except Exception as e:
            logger.warning('[Dense] 集合 %s 不可用（跳过）: %s', coll_name, e)
            continue
        expr_parts = [f'tenant_id == "{TENANT_ID}"']
        if knowledge_version:
            expr_parts.append(f'knowledge_version == "{knowledge_version}"')
        _append_source_type_expr(expr_parts, types_filter)
        _append_role_expr(expr_parts)
        expr = ' and '.join(expr_parts)
        search_params = papers_search_params() if coll_name == COLLECTION_PAPERS else {'metric_type': 'COSINE', 'params': {'ef': search_ef()}}
        try:
            results = coll.search(data=[embedding], anns_field='embedding', param=search_params, limit=top_k, expr=expr, output_fields=['text', 'doc_id', 'source_level', 'source_type', 'parent_key'])
        except Exception as e:
            logger.warning('[Dense] %s ANN 失败（跳过该集合）: %s', coll_name, e)
            continue
        docs, scores, snippets, meta = ([], [], [], [])
        for hits in results:
            for h in hits:
                docs.append(h.id)
                scores.append(h.score)
                snippets.append(str(h.entity.get('text', ''))[:200])
                meta.append({'source_level': h.entity.get('source_level'), 'source_type': h.entity.get('source_type'), 'parent_key': h.entity.get('parent_key') or ''})
        if docs:
            per_route.append((docs, scores, snippets, meta))
    docs, scores, snippets, meta = _interleave_results(per_route)
    logger.info('[Dense] ANN 命中 %d 条（分区=%s，集合=%s）', len(docs), source_types or '全部', [n for n, _ in routes])
    result = ChannelResult(channel='dense', doc_ids=docs, scores=scores, snippets=snippets, metadata=meta, latency_ms=(time.time() - start) * 1000)
    if ckey and result.snippets:
        cache.set(ckey, _result_to_cache(result), ttl=CACHE_TTL_RETRIEVAL)
    return result

def search_image(query_image_data: Optional[bytes]=None, image_url: Optional[str]=None, image_embedding: Optional[list[float]]=None, top_k: int=10) -> ChannelResult:
    import time
    start = time.time()
    if image_embedding is None or all((v == 0.0 for v in image_embedding)):
        try:
            from app.gateway.adapters.clip import CLIPAdapter
            clip = CLIPAdapter()
            if image_url:
                image_embedding = clip.embed_url(image_url)
            elif query_image_data:
                image_embedding = clip.embed_image(query_image_data)
            else:
                logger.info('[Image] 无图片输入，跳过')
                return ChannelResult(channel='image', latency_ms=(time.time() - start) * 1000)
        except ImportError:
            logger.warning('[Image] CLIP 适配器不可用，跳过')
            return ChannelResult(channel='image', latency_ms=(time.time() - start) * 1000)
        except Exception as e:
            logger.warning('[Image] CLIP 向量化失败: %s', e)
            return ChannelResult(channel='image', latency_ms=(time.time() - start) * 1000)
    if image_embedding is None or all((v == 0.0 for v in image_embedding)):
        logger.info('[Image] 零向量（API 不可达或兜底），跳过')
        return ChannelResult(channel='image', latency_ms=(time.time() - start) * 1000)
    try:
        from app.retrieval.index_builder import connect, search_ef
        connect()
        coll = Collection('evidence_image')
        coll.load()
    except Exception as e:
        logger.warning('[Image] Milvus 连接失败: %s', e)
        return ChannelResult(channel='image', latency_ms=(time.time() - start) * 1000)
    results = coll.search(data=[image_embedding], anns_field='embedding', param={'metric_type': 'COSINE', 'params': {'ef': search_ef()}}, limit=top_k, expr=f'tenant_id == "{TENANT_ID}"', output_fields=['image_url', 'doc_id'])
    docs, scores, snippets, meta = ([], [], [], [])
    for hits in results:
        for h in hits:
            docs.append(h.id)
            scores.append(h.score)
            snippets.append(str(h.entity.get('image_url', '')))
            meta.append({'doc_id': h.entity.get('doc_id')})
    logger.info('[Image] CLIP ANN 命中 %d 条', len(docs))
    return ChannelResult(channel='image', doc_ids=docs, scores=scores, snippets=snippets, metadata=meta, latency_ms=(time.time() - start) * 1000)

def _metric_ref_text(row) -> str:
    ref = (getattr(row, 'ref_text', '') or '').strip()
    if ref:
        return ref
    lo, hi = (getattr(row, 'ref_low', None), getattr(row, 'ref_high', None))
    unit = (getattr(row, 'unit', '') or '').strip()
    if lo is not None and hi is not None:
        return f'{lo}~{hi} {unit}'.strip()
    if hi is not None:
        return f'<{hi} {unit}'.strip()
    if lo is not None:
        return f'>{lo} {unit}'.strip()
    return ''

def _flag_cn(flag: str) -> str:
    return {'low': '偏低', 'high': '偏高', 'critical': '显著异常', 'normal': '正常', 'unknown': '未知'}.get((flag or '').lower(), '未知')

def search_sql(query: str='', user_id: str='', metric_code: str='', metric_name: str='', include_history: bool=True, top_k: int=10) -> ChannelResult:
    import time
    start = time.time()
    try:
        from app.factory import repository
        from app.evidence.sources import source_level_of
        from app.health.trends import build_trends
    except Exception as e:
        logger.warning('[SQL] 依赖不可用，本通道降级为空结果: %s', e)
        return ChannelResult(channel='sql', latency_ms=(time.time() - start) * 1000)
    level_catalog = source_level_of('metric_catalog')
    level_user = source_level_of('user_report')
    doc_ids: list[str] = []
    scores: list[float] = []
    snippets: list[str] = []
    meta: list[dict] = []
    catalog_rows = []
    try:
        if metric_code:
            row = repository.get_metric_by_code(metric_code)
            if row:
                catalog_rows.append(row)
        if not catalog_rows:
            name = (metric_name or query).strip()
            if name:
                row = repository.find_metric_by_name(name)
                if row:
                    catalog_rows.append(row)
    except Exception as e:
        logger.warning('[SQL] 指标目录查询失败（降级）: %s', e)
    for row in catalog_rows[:top_k]:
        name = getattr(row, 'name_cn', '') or getattr(row, 'name_en', '')
        snippets.append(json.dumps({'type': 'metric_catalog', 'metric_code': getattr(row, 'metric_code', ''), 'name': name, 'category': getattr(row, 'category', '') or '', 'unit': getattr(row, 'unit', '') or '', 'ref_text': _metric_ref_text(row), 'advice_hint': getattr(row, 'advice_hint', '') or ''}, ensure_ascii=False))
        doc_ids.append(str(getattr(row, 'id', '')))
        scores.append(1.0)
        meta.append({'source_type': 'metric_catalog', 'source_name': name, 'source_level': level_catalog, 'metric_code': getattr(row, 'metric_code', '')})
    if user_id:
        user_metrics = []
        try:
            if metric_code:
                user_metrics = repository.list_metric_history(user_id, metric_code, limit=top_k)
            else:
                keyword = (metric_name or query).strip()
                if keyword:
                    user_metrics = repository.search_metrics_by_keyword(user_id, keyword, limit=top_k)
                else:
                    user_metrics = repository.latest_metrics(user_id)[:top_k]
        except Exception as e:
            logger.warning('[SQL] 用户指标查询失败 user=%s（降级）: %s', user_id, e)
        for m in user_metrics:
            mname = getattr(m, 'metric_name', '') or getattr(m, 'metric_code', '')
            flag = (getattr(m, 'flag', '') or 'unknown').lower()
            snippets.append(json.dumps({'type': 'health_metric', 'metric_code': getattr(m, 'metric_code', ''), 'name': mname, 'category': getattr(m, 'category', '') or '', 'value': getattr(m, 'value_num', None), 'value_text': getattr(m, 'value_text', '') or '', 'unit': getattr(m, 'unit', '') or '', 'ref_text': _metric_ref_text(m), 'flag': flag, 'flag_cn': _flag_cn(flag), 'measured_at': getattr(m, 'measured_at', '') or ''}, ensure_ascii=False))
            doc_ids.append(str(getattr(m, 'id', '')))
            scores.append(1.0)
            meta.append({'source_type': 'health_metric', 'source_name': mname, 'source_level': level_user, 'metric_code': getattr(m, 'metric_code', '')})
        if include_history:
            codes = list(dict.fromkeys((getattr(m, 'metric_code', '') for m in user_metrics if getattr(m, 'metric_code', ''))))[:5]
            if not codes and metric_code:
                codes = [metric_code]
            if codes:
                try:
                    for t in build_trends(user_id, codes, limit=10):
                        snippets.append(json.dumps({'type': 'metric_trend', 'metric_code': t.get('metric_code', ''), 'name': t.get('metric_name', ''), 'unit': t.get('unit', ''), 'direction': t.get('direction', ''), 'first_value': t.get('first_value'), 'last_value': t.get('last_value'), 'abnormal_now': t.get('abnormal_now', False), 'summary': t.get('summary', '')}, ensure_ascii=False))
                        doc_ids.append('')
                        scores.append(1.0)
                        meta.append({'source_type': 'metric_trend', 'source_name': t.get('metric_name', ''), 'source_level': level_user, 'metric_code': t.get('metric_code', '')})
                except Exception as e:
                    logger.warning('[SQL] 趋势生成失败 user=%s（降级）: %s', user_id, e)
    else:
        logger.debug('[SQL] 未提供 user_id，跳过用户指标与趋势（禁止跨用户查询）')
    logger.info('[SQL] 命中 %d 条（指标目录 %d 项，user=%s）', len(snippets), len(catalog_rows), user_id or '—')
    return ChannelResult(channel='sql', doc_ids=doc_ids, scores=scores, snippets=snippets, metadata=meta, latency_ms=(time.time() - start) * 1000)
RERANK_ENABLED = os.getenv('RERANK_ENABLED', 'true').strip().lower() not in ('0', 'false', 'no', 'off')
RERANK_SKIP_MAX_QUERY_CHARS = int(os.getenv('RERANK_SKIP_MAX_QUERY_CHARS', '12'))

def _channel_weights() -> dict[str, float]:
    raw = os.getenv('RRF_CHANNEL_WEIGHTS', '').strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError('期望 JSON 对象')
        return {str(k): float(v) for k, v in data.items()}
    except Exception as e:
        logger.warning('[Fuse] RRF_CHANNEL_WEIGHTS 解析失败，按等权处理: %s', e)
        return {}

def should_rerank(query: str, items: list[dict], enabled: Optional[bool]=None) -> tuple[bool, str]:
    if enabled is None:
        enabled = RERANK_ENABLED
    if not enabled:
        return (False, '精排开关已关闭')
    if len(items) <= 1:
        return (False, '候选不足 2 条')
    q = (query or '').strip()
    if q and len(q) <= RERANK_SKIP_MAX_QUERY_CHARS:
        top = str(items[0].get('snippet', ''))
        if q in top:
            return (False, f'短查询且原词已命中首位（≤{RERANK_SKIP_MAX_QUERY_CHARS} 字），粗排已准')
    return (True, '语义 / 意译查询，交由 Cross-Encoder 精排')

def _expand_and_dedupe_parents(items: list[dict]) -> list[dict]:
    from app.retrieval.index_builder import fetch_parent_texts
    keys = []
    for it in items:
        meta = it.get('metadata') if isinstance(it.get('metadata'), dict) else {}
        pk = str(it.get('parent_key') or meta.get('parent_key') or '')
        if pk:
            it['parent_key'] = pk
            keys.append(pk)
    if not keys:
        return items
    parents = fetch_parent_texts(keys)
    if not parents:
        return items
    from app.retrieval.chunk_strategies import expand_to_parent
    expanded = expand_to_parent(items, parents)
    seen: set[str] = set()
    out: list[dict] = []
    for it in expanded:
        pk = str(it.get('parent_key') or '')
        if it.get('parent_expanded') and pk:
            if pk in seen:
                continue
            seen.add(pk)
        out.append(it)
    logger.info('[Fuse] 父子块扩展: %d → %d 条（按父块去重）', len(items), len(out))
    return out

@timed('retrieval.fuse_rerank')
def fuse_and_rerank(results: list[ChannelResult], query: str, reranker=None, top_k: int=10, rrf_k: Optional[int]=None, expand_parents: bool=True, rerank_enabled: Optional[bool]=None, channel_weights: Optional[dict[str, float]]=None) -> list[dict]:
    from app.retrieval.rrf import rrf_fuse
    weights = channel_weights if channel_weights is not None else _channel_weights()
    rrf_k = int(os.getenv('RRF_K', '60')) if rrf_k is None else rrf_k
    if rrf_k <= 0:
        raise ValueError('RRF_K must be positive')
    fused = rrf_fuse(results, k=rrf_k, weights=weights)
    if not fused:
        return []
    all_items = fused
    if expand_parents:
        all_items = _expand_and_dedupe_parents(all_items)
    documents = [str(it.get('snippet', '')) for it in all_items]
    do_rerank, why = should_rerank(query, all_items, enabled=rerank_enabled)
    if not do_rerank:
        logger.info('[Fuse] 跳过精排：%s → 直接返回 RRF 排序 top%d', why, top_k)
        return all_items[:top_k]
    logger.info('[Fuse] 执行精排：%s', why)
    try:
        if reranker is None:
            from app.gateway.adapters.reranker import RerankerAdapter
            reranker = RerankerAdapter()
        ranked = reranker.rerank(query, documents, top_k=top_k)
        if ranked:
            reranked = []
            for r in ranked:
                idx = r.get('index', 0)
                if idx < len(all_items):
                    item = all_items[idx]
                    item['rerank_score'] = r.get('relevance_score', 0)
                    reranked.append(item)
            logger.info('[Fuse] RRF %d 候选 → Reranker 精排: %d → %d', len(all_items), len(all_items), len(reranked))
            return reranked[:top_k]
    except Exception as e:
        logger.warning('[Fuse] Reranker 失败，使用 RRF 排序: %s', e)
    return all_items[:top_k]
