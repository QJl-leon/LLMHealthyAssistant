import hashlib
import json
from pathlib import Path
from uuid import UUID, uuid5, NAMESPACE_URL
from app.factory.models import Source, MetricCatalogRow, HealthGuideline, MedicalCase
from app.factory.repository import init_tables, insert_source, insert_metric_catalog, insert_guideline, insert_case, delete_by_source
CORPUS_DIR = Path(__file__).resolve().parent / 'corpus'
CORPUS_FILES = {'metric_catalog': CORPUS_DIR / 'metric_catalog.json', 'guidelines': CORPUS_DIR / 'guidelines.json', 'cases': CORPUS_DIR / 'cases.json'}
_SOURCE_NAMESPACE = 'lha-health-corpus'

def _source_uuid(key: str) -> UUID:
    return uuid5(NAMESPACE_URL, f'{_SOURCE_NAMESPACE}::{key}')

def _load_corpus(name: str) -> dict:
    path = CORPUS_FILES[name]
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _register_sources(data: dict) -> dict[str, UUID]:
    ids: dict[str, UUID] = {}
    for item in data.get('_sources', []):
        key = item['key']
        if key in ids:
            continue
        sid = _source_uuid(key)
        name = item['name']
        url = item.get('url', '')
        delete_by_source(sid)
        insert_source(Source(id=sid, name=name, level=int(item.get('level', 2)), license=item.get('license', 'public'), url=url, hash=hashlib.sha256(f'{key}|{name}|{url}'.encode('utf-8')).hexdigest(), status='approved'))
        ids[key] = sid
    return ids

def seed_corpus(knowledge_version: str='draft') -> dict:
    init_tables()
    metric_corpus = _load_corpus('metric_catalog')
    guideline_corpus = _load_corpus('guidelines')
    case_corpus = _load_corpus('cases')
    counts = {'sources': 0, 'metric_catalog': 0, 'health_guidelines': 0, 'medical_cases': 0}
    metric_sources = _register_sources(metric_corpus)
    counts['sources'] += len(metric_sources)
    for row in metric_corpus.get('metrics', []):
        insert_metric_catalog(MetricCatalogRow(metric_code=row['metric_code'], name_cn=row['name_cn'], name_en=row.get('name_en', ''), category=row.get('category', ''), unit=row.get('unit', ''), ref_low=row.get('ref_low'), ref_high=row.get('ref_high'), ref_text=row.get('ref_text', ''), direction=row.get('direction', 'both'), advice_hint=row.get('advice_hint', ''), source_id=metric_sources[row['source']], knowledge_version=knowledge_version))
        counts['metric_catalog'] += 1
    guideline_sources = _register_sources(guideline_corpus)
    counts['sources'] += len(guideline_sources)
    for row in guideline_corpus.get('guidelines', []):
        insert_guideline(HealthGuideline(doc_type=row['doc_type'], evidence_level=row.get('evidence_level', 'B'), title=row['title'], org=row.get('org', ''), year=row.get('year'), topic=row.get('topic', ''), content=row['content'], url=row.get('url', ''), source_id=guideline_sources[row['source']], knowledge_version=knowledge_version))
        counts['health_guidelines'] += 1
    case_sources = _register_sources(case_corpus)
    counts['sources'] += len(case_sources)
    for row in case_corpus.get('cases', []):
        insert_case(MedicalCase(case_code=row['case_code'], age_band=row.get('age_band', ''), sex=row.get('sex', ''), chief_complaint=row.get('chief_complaint', ''), findings=row.get('findings', ''), metrics=row.get('metrics', {}), diagnosis=row.get('diagnosis', ''), intervention=row.get('intervention', ''), outcome=row.get('outcome', ''), evidence_level=row.get('evidence_level', 'C'), source_id=case_sources[row['source']], knowledge_version=knowledge_version))
        counts['medical_cases'] += 1
    return counts

def ingest_sample(knowledge_version: str='draft') -> dict:
    return seed_corpus(knowledge_version)
if __name__ == '__main__':
    results = seed_corpus()
    for table, count in results.items():
        print(f'{table}: {count}')
