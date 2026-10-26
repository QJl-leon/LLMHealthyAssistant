from app.observability.runtime import timed
import logging
from typing import TypedDict
from langgraph.graph import StateGraph, START, END
logger = logging.getLogger(__name__)
_EVIDENCE_BUCKET = {'metric_catalog': 'metric_catalog', 'guideline': 'guideline', 'paper': 'guideline', 'case': 'case', 'health_metric': 'user_report', 'metric_trend': 'user_report'}

class RetrievalState(TypedDict):
    trace_id: str
    task_id: str
    user_id: str
    query: str
    query_plan: dict
    retrieval_results: list
    evidence: list
    metric_trends: list
    parsed_metrics: list
    abnormal_metrics: list
    user_profile: dict
    knowledge_version: str
    image_urls: list
    errors: list

@timed('retrieval.plan')
def _plan_query(state: RetrievalState) -> RetrievalState:
    abnormal = state.get('abnormal_metrics', [])
    logger.info('[Retrieval] plan_query abnormal_metrics=%d', len(abnormal))
    from app.retrieval.query_planner import QueryPlanner
    user_profile = state.get('user_profile', {})
    query = state.get('query', '')
    planner = QueryPlanner(user_profile=user_profile)
    query_plan = planner.plan(abnormal_metrics=abnormal, query=query)
    plans = []
    for p in query_plan.plans:
        plans.append({'subject': p.subject, 'metric_code': p.metric_code, 'category': p.category, 'query': p.query, 'enriched_query': p.enriched_query, 'channels': p.channels, 'source_types': p.source_types, 'priority': p.priority})
    state['query_plan'] = {'plans': plans, 'total_queries': query_plan.total_queries, 'channels_used': sorted(query_plan.channels_used), 'source_types_used': sorted(query_plan.source_types_used)}
    logger.info('[Retrieval] 生成 %d 条查询计划（通道=%s 知识库=%s）', len(plans), sorted(query_plan.channels_used), sorted(query_plan.source_types_used))
    return state

@timed('retrieval.channels')
def _parallel_retrieve(state: RetrievalState) -> RetrievalState:
    logger.info('[Retrieval] parallel_retrieve')
    from app.retrieval.channels import search_sql, search_dense, search_bm25, search_image, fuse_and_rerank, ChannelResult
    from app.retrieval.hyde import prepare_dense_query
    current_kv = state.get('knowledge_version') or None
    if not current_kv:
        try:
            from app.factory.repository import get_current_version
            cv = get_current_version()
            if cv:
                current_kv = cv.version
        except Exception:
            current_kv = None
    if current_kv:
        logger.info('[Retrieval] 检索知识版本: %s', current_kv)
    user_id = state.get('user_id', '')
    errors: list[dict] = list(state.get('errors') or [])

    def _record_error(stage: str, subject: str, exc: Exception) -> None:
        message = f'{stage} 通道失败 [{subject}]: {exc}'
        if not any((e.get('message') == message for e in errors)):
            errors.append({'error_code': 'RETRIEVAL_CHANNEL_FAILED', 'message': message, 'retryable': True})
    all_channel_results: list[ChannelResult] = []
    for plan_item in state.get('query_plan', {}).get('plans', []):
        subject = plan_item.get('subject', '')
        metric_code = plan_item.get('metric_code', '')
        query = plan_item.get('query') or subject
        enriched_query = plan_item.get('enriched_query') or query
        source_types = plan_item.get('source_types') or None
        enabled_channels = set(plan_item.get('channels', ['bm25', 'dense']))
        if 'sql' in enabled_channels:
            try:
                sql_result = search_sql(query=query, user_id=user_id, metric_code=metric_code, metric_name=subject, include_history=True)
                if sql_result.snippets:
                    all_channel_results.append(sql_result)
                    logger.info('[Retrieval] SQL 命中: %s → %d 条', subject, len(sql_result.snippets))
            except Exception as e:
                logger.warning('[Retrieval] SQL 通道异常（已降级）: %s → %s', subject, e)
                _record_error('sql', subject, e)
        if 'bm25' in enabled_channels:
            try:
                bm25_result = search_bm25(query, top_k=10, knowledge_version=current_kv, source_types=source_types)
                if bm25_result.snippets:
                    all_channel_results.append(bm25_result)
                    logger.info('[Retrieval] BM25 命中: %s → %d 条', subject, len(bm25_result.snippets))
            except Exception as e:
                logger.warning('[Retrieval] BM25 通道异常（已降级）: %s → %s', subject, e)
                _record_error('bm25', subject, e)
        if 'dense' in enabled_channels:
            try:
                dense_query, dense_vec = prepare_dense_query(enriched_query)
                dense_result = search_dense(dense_query, embedding=dense_vec, top_k=10, knowledge_version=current_kv, source_types=source_types)
                if dense_result.snippets:
                    all_channel_results.append(dense_result)
                    logger.info('[Retrieval] Dense 命中: %s → %d 条', subject, len(dense_result.snippets))
            except Exception as e:
                logger.warning('[Retrieval] Dense 通道异常（已降级）: %s → %s', subject, e)
                _record_error('dense', subject, e)
        if 'image' in enabled_channels:
            try:
                image_urls = state.get('image_urls', [])
                if image_urls:
                    image_result = search_image(image_url=image_urls[0], top_k=10)
                    if image_result.snippets:
                        all_channel_results.append(image_result)
                        logger.info('[Retrieval] Image 命中: %d 条', len(image_result.snippets))
                else:
                    logger.debug('[Retrieval] Image 通道跳过（无图片 URL）')
            except Exception as e:
                logger.warning('[Retrieval] Image 通道异常（已降级）: %s', e)
                _record_error('image', subject, e)
    raw_count = sum((len(r.snippets) for r in all_channel_results))
    fused = []
    if all_channel_results:
        try:
            fused = fuse_and_rerank(all_channel_results, query=_aggregate_query(state), top_k=20)
            logger.info('[Retrieval] Reranker 融合: %d 条 → %d 条', raw_count, len(fused))
        except Exception as e:
            logger.warning('[Retrieval] Reranker 融合失败，使用原始结果: %s', e)
            _record_error('fuse', 'all', e)
            for r in all_channel_results:
                for did, score, snippet in zip(r.doc_ids, r.scores, r.snippets):
                    fused.append({'doc_id': did, 'channel': r.channel, 'score': score, 'snippet': snippet})
    metric_trends: list[dict] = []
    if user_id:
        codes = list(dict.fromkeys((m.get('metric_code', '') for m in state.get('abnormal_metrics', []) if m.get('metric_code'))))
        try:
            from app.health.trends import build_trends
            metric_trends = build_trends(user_id, codes or None, limit=10)
        except Exception as e:
            logger.warning('[Retrieval] 指标趋势生成失败（已降级）: %s', e)
            _record_error('trends', user_id, e)
    else:
        logger.debug('[Retrieval] 无 user_id，跳过指标趋势（禁止跨用户查询）')
    state['knowledge_version'] = current_kv or ''
    state['metric_trends'] = metric_trends
    state['retrieval_results'] = fused
    state['errors'] = errors
    logger.info('[Retrieval] 最终召回 %d 条结果（通道 %d，趋势 %d）', len(fused), len(all_channel_results), len(metric_trends))
    return state

def _aggregate_query(state: RetrievalState) -> str:
    query = (state.get('query') or '').strip()
    if query:
        return query
    names = [m.get('metric_name', '') for m in state.get('abnormal_metrics', []) if m.get('metric_name')]
    if names:
        return f"{' '.join(names[:5])} 异常 参考区间 运动干预 生活方式 循证建议"
    return '体检指标 异常 参考区间 运动干预 生活方式 循证建议'

@timed('retrieval.evidence')
def _build_evidence(state: RetrievalState) -> RetrievalState:
    logger.info('[Retrieval] build_evidence')
    import json as _json
    from uuid import uuid4
    from app.evidence.sources import resolve_source_url, source_label, source_level_of

    def _bucket(ev_type: str, channel: str) -> str:
        bucket = _EVIDENCE_BUCKET.get((ev_type or '').lower())
        if bucket:
            return bucket
        return 'metric_catalog' if channel == 'sql' else 'guideline'

    def _parse_snippet(raw: str, source_type_hint: str='') -> tuple[str, str, str]:
        data = None
        try:
            data = _json.loads(raw)
        except (_json.JSONDecodeError, TypeError):
            data = None
        if isinstance(data, dict):
            ev_type = str(data.get('type') or source_type_hint or '').lower()
            if ev_type == 'metric_catalog':
                name = data.get('name', '')
                code = data.get('metric_code', '')
                ref = data.get('ref_text', '')
                advice = data.get('advice_hint', '')
                head = f'{name}（{code}）' if code else name
                quote = f'{head} 参考区间 {ref}' if ref else head
                if advice:
                    quote += f'；异常提示：{advice}'
                return (quote, f'{name} 指标目录' if name else '体检指标目录', 'metric_catalog')
            if ev_type == 'health_metric':
                name = data.get('name', '')
                unit = data.get('unit', '')
                value = data.get('value')
                value_text = data.get('value_text', '')
                flag_cn = data.get('flag_cn', '')
                measured_at = data.get('measured_at', '')
                ref = data.get('ref_text', '')
                shown = value if value is not None else value_text or '—'
                quote = f'{name} {shown}{unit}（{flag_cn}'
                quote += f'，{measured_at}）' if measured_at else '）'
                if ref:
                    quote += f' 参考区间 {ref}'
                return (quote, f'{name} 体检记录' if name else '本人体检记录', 'health_metric')
            if ev_type == 'metric_trend':
                summary = data.get('summary', '')
                name = data.get('name', '')
                return (summary, f'{name} 趋势' if name else '本人指标趋势', 'metric_trend')
            if ev_type in ('guideline', 'case'):
                quote, source_name = _clean_milvus_text(raw)
                return (quote, source_name, ev_type)
            return (_clean_milvus_text(raw)[0], _clean_milvus_text(raw)[1], (source_type_hint or '').lower())
        hint = (source_type_hint or '').lower()
        quote, source_name = _clean_milvus_text(raw)
        if not hint and ('病历案例' in raw or raw.strip().startswith('案例')):
            hint = 'case'
        return (quote, source_name, hint)

    def _clean_milvus_text(raw: str) -> tuple[str, str]:
        import re
        text = raw.strip()
        text = re.sub('\\s*—\\s*[A-Z][a-zA-Z]*(\\s+[A-Z][a-zA-Z]*)*\\s*$', '', text)
        text = re.sub('\\s*—\\s*$', '', text)
        text = text.replace('—  —', '—')
        name_match = re.match('^([^\\(（]+)', text)
        source_name = name_match.group(1).strip() if name_match else text.split('\n')[0][:50]
        return (text[:200], source_name)
    evidence = []
    seen_snippets = set()
    kv_default = state.get('knowledge_version', '')
    for result in state.get('retrieval_results', []):
        if isinstance(result, dict):
            snippet_str = result.get('snippet', '')
            if not snippet_str or snippet_str in seen_snippets:
                continue
            seen_snippets.add(snippet_str)
            metadata = result.get('metadata') if isinstance(result.get('metadata'), dict) else {}
            source_type_hint = str(metadata.get('source_type') or '')
            quote, source_name, ev_type = _parse_snippet(snippet_str, source_type_hint)
            channel = result.get('channel', 'unknown')
            doc_id = result.get('doc_id', 'unknown')
            bucket = _bucket(ev_type, channel)
            level = source_level_of(bucket)
            evidence.append({'evidence_id': str(uuid4()), 'doc_id': doc_id, 'source_name': source_name, 'source_level': level, 'source_type': ev_type, 'source_label': source_label(bucket), 'quote': quote, 'confidence': result.get('rerank_score', result.get('score', 0.5)), 'channel': channel, 'knowledge_version': metadata.get('knowledge_version') or kv_default, 'source_url': resolve_source_url(channel=channel, source_level=level, source_name=source_name, doc_id=doc_id, evidence_type=bucket), 'page': result.get('page') or 0})
            continue
        if hasattr(result, 'snippets'):
            channel = getattr(result, 'channel', 'sql')
            metas = getattr(result, 'metadata', []) or []
            for idx, snippet_str in enumerate(result.snippets):
                if not snippet_str or snippet_str in seen_snippets:
                    continue
                seen_snippets.add(snippet_str)
                metadata = metas[idx] if idx < len(metas) and isinstance(metas[idx], dict) else {}
                source_type_hint = str(metadata.get('source_type') or '')
                quote, source_name, ev_type = _parse_snippet(snippet_str, source_type_hint)
                bucket = _bucket(ev_type, channel)
                level = source_level_of(bucket)
                evidence.append({'evidence_id': str(uuid4()), 'doc_id': metadata.get('doc_id') or channel, 'source_name': source_name, 'source_level': level, 'source_type': ev_type, 'source_label': source_label(bucket), 'quote': quote, 'confidence': 1.0, 'channel': channel, 'knowledge_version': metadata.get('knowledge_version') or kv_default, 'source_url': resolve_source_url(channel=channel, source_level=level, source_name=source_name, evidence_type=bucket), 'page': metadata.get('page') or 0})
    if evidence:
        evidence.sort(key=lambda e: int(e.get('source_level') or 3))
    if evidence:
        from app.evidence.concentration import check_concentration, annotate_evidence
        conc_result = check_concentration(evidence)
        if conc_result.needs_diversification:
            logger.warning('[Retrieval] 来源集中度过高 level=%s max_ratio=%.0f%% dominant=%s', conc_result.level, conc_result.max_source_ratio * 100, conc_result.dominant_source)
        evidence = annotate_evidence(evidence, conc_result)
    state['evidence'] = evidence
    logger.info('[Retrieval] built %d evidence items', len(evidence))
    return state

def build_retrieval_agent() -> StateGraph:
    graph = StateGraph(RetrievalState)
    graph.add_node('plan_query', _plan_query)
    graph.add_node('parallel_retrieve', _parallel_retrieve)
    graph.add_node('build_evidence', _build_evidence)
    graph.add_edge(START, 'plan_query')
    graph.add_edge('plan_query', 'parallel_retrieve')
    graph.add_edge('parallel_retrieve', 'build_evidence')
    graph.add_edge('build_evidence', END)
    return graph
retrieval_agent = build_retrieval_agent().compile()
