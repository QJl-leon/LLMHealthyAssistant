from __future__ import annotations
LEVEL_AUTHORITY = 1
LEVEL_SOCIETY = 2
LEVEL_OPEN = 3
LEVEL_USER = 4
NHC_PORTAL = 'https://www.nhc.gov.cn/'
CMA_PORTAL = 'https://www.cma.org.cn/'
CMCR_CASE_BASE = 'https://cmcr.yiigle.com/'
PUBMED_PORTAL = 'https://pubmed.ncbi.nlm.nih.gov/'
_SOURCES: dict[str, dict] = {'metric_catalog': {'url': NHC_PORTAL, 'level': LEVEL_AUTHORITY, 'label': '体检指标目录'}, 'guideline': {'url': CMA_PORTAL, 'level': LEVEL_SOCIETY, 'label': '健康指南'}, 'case': {'url': CMCR_CASE_BASE, 'level': LEVEL_SOCIETY, 'label': '病历案例'}, 'open_research': {'url': PUBMED_PORTAL, 'level': LEVEL_OPEN, 'label': '开放研究文献'}, 'user_report': {'url': '', 'level': LEVEL_USER, 'label': '用户体检报告'}}
_FALLBACK_TYPE = 'open_research'
_ALIASES: dict[str, str] = {'metric_catalog': 'metric_catalog', 'metriccatalog': 'metric_catalog', 'metric': 'metric_catalog', 'metric_row': 'metric_catalog', '指标目录': 'metric_catalog', '体检指标': 'metric_catalog', '参考区间': 'metric_catalog', 'guideline': 'guideline', 'health_guideline': 'guideline', 'paper': 'guideline', 'literature': 'guideline', '指南': 'guideline', '共识': 'guideline', '论文': 'guideline', '文献': 'guideline', 'case': 'case', 'medical_case': 'case', 'case_report': 'case', '病历': 'case', '病例': 'case', '案例': 'case', 'open_research': 'open_research', 'preprint': 'open_research', '开放研究': 'open_research', '预印本': 'open_research', 'exam_report': 'user_report', 'user_report': 'user_report', 'report': 'user_report', '体检报告': 'user_report'}
_NAME_KEYWORDS: tuple[tuple[str, str], ...] = (('指标', 'metric_catalog'), ('参考区间', 'metric_catalog'), ('指南', 'guideline'), ('共识', 'guideline'), ('论文', 'guideline'), ('文献', 'guideline'), ('病例', 'case'), ('病历', 'case'), ('案例', 'case'), ('体检报告', 'user_report'))

def _normalize_type(evidence_type: str='', channel: str='', source_name: str='') -> str:
    et = (evidence_type or '').strip().lower()
    if et in _ALIASES:
        return _ALIASES[et]
    name = source_name or ''
    for keyword, bucket in _NAME_KEYWORDS:
        if keyword in name:
            return bucket
    ch = (channel or '').strip().lower()
    if ch == 'sql':
        return 'metric_catalog'
    if ch in ('dense', 'bm25', 'vector', 'keyword'):
        return 'guideline'
    return _FALLBACK_TYPE

def source_label(evidence_type: str) -> str:
    return _SOURCES[_normalize_type(evidence_type)]['label']

def source_level_of(evidence_type: str) -> int:
    return _SOURCES[_normalize_type(evidence_type)]['level']

def resolve_source_url(*, channel: str='', source_level: int=1, source_name: str='', doc_id: str='', explicit_url: str='', evidence_type: str='') -> str:
    if explicit_url and explicit_url.startswith(('http://', 'https://')):
        return explicit_url
    bucket = _normalize_type(evidence_type=evidence_type, channel=channel, source_name=(source_name or '') + (doc_id or ''))
    return _SOURCES[bucket]['url']
