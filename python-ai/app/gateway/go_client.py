from __future__ import annotations
from app.observability.runtime import timed
import logging
import os
from typing import Any
from httpx import Client, HTTPError
logger = logging.getLogger(__name__)

def _go_base() -> str:
    return os.getenv('GO_BASE_URL', 'http://localhost:8080').rstrip('/')

@timed('save_report')
def persist_report(task_id: str, *, sections: dict[str, str] | None=None, citations: list[dict[str, Any]] | None=None, knowledge_version: str='unknown', status: str='published', metadata: dict[str, str] | None=None, metrics: list[dict[str, Any]] | None=None, metric_trends: list[dict[str, Any]] | None=None) -> dict[str, Any] | None:
    payload = {'task_id': task_id, 'knowledge_version': knowledge_version or 'unknown', 'status': status or 'published', 'sections': sections or {}, 'citations': citations or [], 'metadata': metadata or {}, 'metrics': metrics or [], 'metric_trends': metric_trends or []}
    from app.observability.runtime import CORRELATION
    from app.context import ctx as call_ctx
    headers = {'X-Trace-Id': call_ctx.get_trace_id(), 'X-Run-Id': CORRELATION.get().get('run_id', '')}
    token = os.getenv('INTERNAL_API_TOKEN', '')
    if token:
        headers['X-Internal-Token'] = token
    url = f'{_go_base()}/internal/reports'
    try:
        with Client(timeout=15.0) as client:
            resp = client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            body = resp.json()
            if body.get('code') != 0:
                logger.error('[go_client] persist_report rejected: %s', body)
                return None
            data = body.get('data') or {}
            logger.info('[go_client] report persisted id=%s task=%s v%s', data.get('id'), task_id, data.get('version'))
            return data
    except HTTPError as e:
        logger.error('[go_client] persist_report HTTP error: %s', e)
        return None
    except Exception as e:
        logger.error('[go_client] persist_report failed: %s', e, exc_info=True)
        return None

def build_report_payload_from_state(state: dict[str, Any]) -> dict[str, Any]:
    draft = state.get('report_draft') or {}
    if not isinstance(draft, dict):
        draft = {}
    sections_raw = draft.get('sections') or {}
    if not isinstance(sections_raw, dict):
        sections_raw = {}
    sections = {str(k): str(v) if v is not None else '' for k, v in sections_raw.items()}
    citations: list[dict[str, Any]] = []
    for ev in state.get('evidence') or []:
        if not isinstance(ev, dict):
            continue
        citations.append({'claim_id': str(ev.get('claim_id') or ''), 'evidence_id': str(ev.get('evidence_id') or ev.get('id') or ''), 'source_name': str(ev.get('source_name') or ev.get('source') or ''), 'quote': str(ev.get('quote') or ''), 'source_url': str(ev.get('source_url') or '')})
    kv = state.get('knowledge_version')
    if not kv:
        evidence = state.get('evidence') or []
        if evidence and isinstance(evidence[0], dict):
            kv = evidence[0].get('knowledge_version')
    if not kv:
        kv = 'unknown'
    meta: dict[str, str] = {}
    if state.get('report_version'):
        meta['report_version'] = str(state['report_version'])
    metrics = state.get('parsed_metrics') or []
    if metrics:
        meta['metrics_count'] = str(len(metrics))
    abnormal = state.get('abnormal_metrics') or []
    if abnormal:
        meta['abnormal_metrics_count'] = str(len(abnormal))
    return {'sections': sections, 'citations': citations, 'knowledge_version': str(kv), 'metadata': meta, 'metrics': _metric_items_from_state(state), 'metric_trends': _metric_trends_from_state(state)}

def _metric_items_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in state.get('parsed_metrics') or []:
        if not isinstance(m, dict):
            continue
        out.append({'metric_code': str(m.get('metric_code') or ''), 'metric_name': str(m.get('metric_name') or ''), 'category': str(m.get('category') or ''), 'value_num': float(m.get('value_num') or 0.0), 'value_text': str(m.get('value_text') or ''), 'unit': str(m.get('unit') or ''), 'ref_low': float(m.get('ref_low') or 0.0), 'ref_high': float(m.get('ref_high') or 0.0), 'ref_text': str(m.get('ref_text') or ''), 'flag': str(m.get('flag') or 'unknown'), 'measured_at': str(m.get('measured_at') or '')})
    return out

def _metric_trends_from_state(state: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for t in state.get('metric_trends') or []:
        if not isinstance(t, dict):
            continue
        points = []
        for p in t.get('points') or []:
            if not isinstance(p, dict):
                continue
            points.append({'date': str(p.get('date') or ''), 'value': float(p.get('value') or 0.0), 'flag': str(p.get('flag') or 'unknown')})
        out.append({'metric_code': str(t.get('metric_code') or ''), 'metric_name': str(t.get('metric_name') or ''), 'unit': str(t.get('unit') or ''), 'points': points, 'first_value': float(t.get('first_value') or 0.0), 'last_value': float(t.get('last_value') or 0.0), 'delta': float(t.get('delta') or 0.0), 'direction': str(t.get('direction') or '')})
    return out
