from __future__ import annotations
import json
import logging
import re
from typing import Any, Optional
logger = logging.getLogger(__name__)

def _ref_text(row: Any) -> str:
    text = getattr(row, 'ref_text', '') or ''
    if text:
        return text
    lo, hi = (getattr(row, 'ref_low', None), getattr(row, 'ref_high', None))
    unit = getattr(row, 'unit', '') or ''
    if lo is not None and hi is not None:
        return f'{lo}~{hi} {unit}'.strip()
    if hi is not None:
        return f'<{hi} {unit}'.strip()
    if lo is not None:
        return f'>{lo} {unit}'.strip()
    return ''

def _keywords(query: str) -> list[str]:
    return [t for t in re.split('[\\s,，、;；/|]+', (query or '').strip()) if t]

def _match_metric_rows(query: str, knowledge_version: Optional[str], limit: int) -> list[Any]:
    from app.factory.repository import find_metric_by_name, list_metric_catalog
    keyword = (query or '').strip()
    rows = list_metric_catalog(knowledge_version) or []
    if not keyword:
        return rows[:limit]
    matched: list[Any] = []
    seen: set[str] = set()
    hit = find_metric_by_name(keyword)
    if hit is not None:
        matched.append(hit)
        seen.add(str(hit.id))
    terms = _keywords(keyword)
    for row in rows:
        if str(row.id) in seen:
            continue
        text = ' '.join(filter(None, [row.name_cn, row.name_en, row.metric_code, row.category, row.advice_hint]))
        if any((t in text for t in terms)) or (row.name_cn and row.name_cn in keyword) or (row.category and row.category in keyword):
            matched.append(row)
            seen.add(str(row.id))
        if len(matched) >= limit:
            break
    return matched[:limit]

def _search_metric_catalog(query: str, knowledge_version: Optional[str]=None, limit: int=10):
    from app.retrieval.channels import ChannelResult
    rows = _match_metric_rows(query, knowledge_version, limit)
    snippets: list[str] = []
    doc_ids: list[str] = []
    for row in rows:
        snippets.append(json.dumps({'type': 'metric_catalog', 'metric_code': row.metric_code, 'name': row.name_cn, 'name_en': row.name_en, 'category': row.category, 'unit': row.unit, 'ref_text': _ref_text(row), 'advice_hint': row.advice_hint}, ensure_ascii=False))
        doc_ids.append(str(row.id))
    return ChannelResult(channel='sql', doc_ids=doc_ids, scores=[1.0] * len(snippets), snippets=snippets)

def _infer_source_type(snippet: str) -> str:
    text = snippet or ''
    if '病历案例' in text or text.strip().startswith('案例'):
        return 'case'
    if '体检指标' in text or '参考区间' in text:
        return 'metric_catalog'
    return 'guideline'

def search_evidence(query: str, channels: Optional[list[str]]=None, knowledge_version: Optional[str]=None, top_k: int=10) -> str:
    logger.info('[MCP] search_evidence query=%s channels=%s', query, channels)
    from app.retrieval.channels import ChannelResult, fuse_and_rerank, search_bm25, search_dense
    ch = channels or ['bm25', 'dense', 'sql']
    channel_results: list[ChannelResult] = []
    errors: list[str] = []
    if 'sql' in ch:
        try:
            idx_result = _search_metric_catalog(query, knowledge_version=knowledge_version, limit=top_k)
            if idx_result.snippets:
                channel_results.append(idx_result)
        except Exception as e:
            errors.append(f'metric_catalog: {e}')
            logger.warning('[MCP] metric catalog channel failed: %s', e)
    if 'bm25' in ch:
        try:
            channel_results.append(search_bm25(query))
        except Exception as e:
            errors.append(f'bm25: {e}')
            logger.warning('[MCP] bm25 channel failed: %s', e)
    if 'dense' in ch:
        try:
            channel_results.append(search_dense(query))
        except Exception as e:
            errors.append(f'dense: {e}')
            logger.warning('[MCP] dense channel failed: %s', e)
    fused: list[dict[str, Any]] = []
    if channel_results:
        try:
            fused = fuse_and_rerank(channel_results, query, top_k=top_k)
        except Exception as e:
            errors.append(f'fuse: {e}')
            for r in channel_results:
                for sn in (r.snippets or [])[:top_k]:
                    fused.append({'snippet': sn, 'channel': r.channel, 'doc_id': getattr(r, 'doc_ids', [None])[0] if getattr(r, 'doc_ids', None) else r.channel, 'score': 0.5})
    items = []
    for i, row in enumerate(fused[:top_k]):
        snippet = str(row.get('snippet', ''))
        channel = row.get('channel', 'unknown')
        items.append({'rank': i + 1, 'channel': channel, 'source_type': _infer_source_type(snippet), 'doc_id': row.get('doc_id', ''), 'snippet': snippet[:500], 'score': row.get('rerank_score', row.get('score', 0)), 'knowledge_version': knowledge_version or 'current'})
    output = {'query': query, 'total': len(items), 'results': items, 'channels_used': [r.channel for r in channel_results], 'errors': errors}
    return json.dumps(output, ensure_ascii=False, indent=2)

def get_metric_profile(metric_code: str='', name: str='') -> str:
    logger.info('[MCP] get_metric_profile code=%s name=%s', metric_code, name)
    if not metric_code and (not name):
        return json.dumps({'error': 'metric_code 或 name 至少提供一个'}, ensure_ascii=False)
    from app.factory.repository import find_metric_by_name, get_metric_by_code
    row = get_metric_by_code(metric_code) if metric_code else None
    if row is None and name:
        row = find_metric_by_name(name)
    if row is None:
        return json.dumps({'query': {'metric_code': metric_code, 'name': name}, 'found': False, 'results': [], 'message': '指标目录中未找到该指标'}, ensure_ascii=False, indent=2)
    return json.dumps({'query': {'metric_code': metric_code, 'name': name}, 'found': True, 'results': [{'metric_code': row.metric_code, 'name_cn': row.name_cn, 'name_en': row.name_en, 'category': row.category, 'unit': row.unit, 'ref_text': _ref_text(row), 'ref_low': row.ref_low, 'ref_high': row.ref_high, 'direction': row.direction, 'advice_hint': row.advice_hint, 'knowledge_version': row.knowledge_version}]}, ensure_ascii=False, indent=2)

def get_metric_trend(user_id: str, metric_code: str, limit: int=10) -> str:
    logger.info('[MCP] get_metric_trend user=%s code=%s', user_id, metric_code)
    if not user_id or not metric_code:
        return json.dumps({'error': 'user_id 与 metric_code 均不可为空'}, ensure_ascii=False)
    from app.factory.repository import list_metric_history
    rows = list_metric_history(user_id, metric_code, limit=limit)
    points: list[dict[str, Any]] = []
    for r in reversed(rows):
        if r.value_num is None and (not r.value_text):
            continue
        points.append({'date': r.measured_at, 'value': r.value_num if r.value_num is not None else r.value_text, 'unit': r.unit, 'flag': r.flag})
    direction = 'unknown'
    numeric = [p['value'] for p in points if isinstance(p['value'], (int, float))]
    if len(numeric) >= 2:
        first, last = (float(numeric[0]), float(numeric[-1]))
        scale = abs(first) or 1.0
        delta = (last - first) / scale
        direction = 'stable' if abs(delta) < 0.05 else 'rising' if delta > 0 else 'falling'
    return json.dumps({'user_id': user_id, 'metric_code': metric_code, 'total': len(points), 'first': points[0] if points else None, 'last': points[-1] if points else None, 'direction': direction, 'points': points}, ensure_ascii=False, indent=2)

def validate_claims(claims_json: str) -> str:
    logger.info('[MCP] validate_claims payload=%s', claims_json[:120])
    from app.evidence.validator import refuse_if_no_evidence, validate_existence, validate_name
    try:
        payload = json.loads(claims_json)
    except json.JSONDecodeError:
        return json.dumps({'error': 'Invalid JSON format'}, ensure_ascii=False)
    if isinstance(payload, list):
        claims = payload
        evidence = []
    elif isinstance(payload, dict):
        claims = payload.get('claims') or []
        evidence = payload.get('evidence') or []
    else:
        return json.dumps({'error': 'claims_json 须为数组或 {claims, evidence}'}, ensure_ascii=False)
    registered = {str(e.get('evidence_id') or e.get('id') or '') for e in evidence if isinstance(e, dict)}
    registered.discard('')
    if isinstance(payload, dict):
        for eid in payload.get('registered_evidence_ids') or []:
            if eid:
                registered.add(str(eid))
    results = []
    for claim in claims:
        if not isinstance(claim, dict):
            continue
        cid = claim.get('claim_id', '')
        evidence_ids = [str(x) for x in claim.get('evidence_ids') or [] if x]
        text = str(claim.get('text') or claim.get('claim') or '')
        exist_result = validate_existence(cid, evidence_ids, registered_ids=registered if registered else None)
        name_result = validate_name(cid, text) if text and len(text) < 40 else None
        results.append({'claim_id': cid, 'existence': exist_result.passed, 'name_check': None if name_result is None else name_result.passed, 'failures': exist_result.failures + (name_result.failures if name_result else [])})
    if evidence:
        refuse, reason = refuse_if_no_evidence(claims, evidence)
    else:
        refuse = bool(results) and (not all((r['existence'] for r in results)))
        reason = '存在性校验未全部通过' if refuse else ''
    return json.dumps({'results': results, 'refuse': refuse, 'refuse_reason': reason}, ensure_ascii=False, indent=2)

def read_evidence_recent(limit: int=20) -> str:
    import os
    import psycopg2
    from psycopg2.extras import RealDictCursor
    db = os.getenv('DATABASE_URL', 'postgresql://lha:lha_dev@localhost:5432/lha')
    try:
        conn = psycopg2.connect(db)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT id::text, source_id::text, knowledge_version, kind,\n                      left(content, 200) AS excerpt\n               FROM parsed_documents\n               ORDER BY id DESC\n               LIMIT %s', (limit,))
        rows = [dict(r) for r in cur.fetchall()]
        cur.close()
        conn.close()
        return json.dumps({'items': rows, 'total': len(rows)}, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning('[MCP] evidence://recent failed: %s', e)
        return json.dumps({'items': [], 'error': str(e)}, ensure_ascii=False)

def read_sources_catalog() -> str:
    try:
        from app.factory.repository import list_sources
        sources = list_sources(status='approved')
        items = [{'id': str(s.id), 'name': s.name, 'level': s.level, 'url': s.url, 'status': s.status} for s in sources]
        return json.dumps({'items': items, 'total': len(items)}, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning('[MCP] sources://catalog failed: %s', e)
        return json.dumps({'items': [], 'error': str(e)}, ensure_ascii=False)
