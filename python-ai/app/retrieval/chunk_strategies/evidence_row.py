from __future__ import annotations
from app.retrieval.chunk_strategies.base import _field
SOURCE_GUIDELINE = 'guideline'
SOURCE_CASE = 'case'
SOURCE_METRIC = 'metric_catalog'
EVIDENCE_SOURCE_TYPES = (SOURCE_GUIDELINE, SOURCE_CASE, SOURCE_METRIC)

def naturalize_metric_row(row: dict) -> str:
    if not isinstance(row, dict):
        return ''
    unit = _field(row, 'unit')
    ref = _field(row, 'ref_text')
    if not ref:
        low, high = (row.get('ref_low'), row.get('ref_high'))
        if low is not None and high is not None:
            ref = f'{low}~{high} {unit}'.strip()
        elif high is not None:
            ref = f'<{high} {unit}'.strip()
        elif low is not None:
            ref = f'>{low} {unit}'.strip()
    parts = [f"体检指标 {_field(row, 'name_cn') or _field(row, 'metric_name')}", f"编码 {_field(row, 'metric_code')}", f"类别 {_field(row, 'category')}", f'单位 {unit}', f'参考区间 {ref}']
    if row.get('advice_hint'):
        parts.append(f"异常提示 {_field(row, 'advice_hint')}")
    return ' | '.join((p for p in parts if p.split(' ', 1)[-1].strip()))

def naturalize_guideline_row(row: dict) -> str:
    if not isinstance(row, dict):
        return ''
    head = _field(row, 'title')
    meta = ' '.join((x for x in (_field(row, 'org'), _field(row, 'year'), f"证据等级{_field(row, 'evidence_level')}" if row.get('evidence_level') else '', _field(row, 'topic')) if x))
    body = _field(row, 'content')
    prefix = f'{head}（{meta}）' if head and meta else head or meta
    return f'{prefix}{body}'.strip()

def naturalize_case_row(row: dict) -> str:
    if not isinstance(row, dict):
        return ''
    metrics = row.get('metrics')
    metrics_text = ''
    if isinstance(metrics, dict) and metrics:
        metrics_text = '、'.join((f'{k}={v}' for k, v in metrics.items()))
    parts = [f"病历案例 {_field(row, 'case_code')}", f"{_field(row, 'sex')} {_field(row, 'age_band')}".strip(), f"主诉 {_field(row, 'chief_complaint')}" if row.get('chief_complaint') else '', f"检查发现 {_field(row, 'findings')}" if row.get('findings') else '', f'关键指标 {metrics_text}' if metrics_text else '', f"诊断 {_field(row, 'diagnosis')}" if row.get('diagnosis') else '', f"干预 {_field(row, 'intervention')}" if row.get('intervention') else '', f"结局 {_field(row, 'outcome')}" if row.get('outcome') else '', f"证据等级 {_field(row, 'evidence_level')}" if row.get('evidence_level') else '']
    return ' | '.join((p for p in parts if p.strip()))

def is_evidence_row(content: dict) -> bool:
    if not isinstance(content, dict):
        return False
    source_type = (_field(content, 'source_type') or _field(content, 'kind')).lower()
    if source_type in EVIDENCE_SOURCE_TYPES:
        return True
    return bool(content.get('metric_code') or content.get('name_cn'))

def naturalize_content(content: dict) -> str:
    if not isinstance(content, dict):
        return str(content)
    source_type = (_field(content, 'source_type') or _field(content, 'kind')).lower()
    if source_type == SOURCE_GUIDELINE:
        return naturalize_guideline_row(content)
    if source_type == SOURCE_CASE:
        return naturalize_case_row(content)
    if source_type == SOURCE_METRIC:
        return naturalize_metric_row(content)
    if content.get('metric_code') or content.get('name_cn'):
        return naturalize_metric_row(content)
    raw = _field(content, 'raw_text') or _field(content, 'text')
    if raw:
        return raw
    if content.get('title') or content.get('content'):
        return naturalize_guideline_row(content)
    if content.get('case_code'):
        return naturalize_case_row(content)
    raw_row = content.get('raw_row')
    if isinstance(raw_row, list):
        cells = [str(c).strip() for c in raw_row if c is not None and str(c).strip()]
        return ' | '.join(cells)
    return ''
