import os
import hashlib
import json
from datetime import datetime
from uuid import UUID, uuid4
from typing import Optional
import psycopg2
from psycopg2.extras import RealDictCursor, Json, register_uuid
from app.factory.models import Source, KnowledgeVersion, ParsedDocument, MetricCatalogRow, HealthReport, HealthMetric, HealthGuideline, MedicalCase
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://lha:lha_dev@localhost:5432/lha')
register_uuid()

def _conn():
    return psycopg2.connect(DATABASE_URL)

def _parse_uuid_list(raw) -> list[UUID]:
    if raw is None:
        return []
    if isinstance(raw, (list, tuple)):
        out = []
        for item in raw:
            if isinstance(item, UUID):
                out.append(item)
            else:
                out.append(UUID(str(item)))
        return out
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith('{') and s.endswith('}'):
            inner = s[1:-1].strip()
            if not inner:
                return []
            return [UUID(p.strip().strip('"')) for p in inner.split(',') if p.strip()]
        return [UUID(s)]
    if isinstance(raw, UUID):
        return [raw]
    return [UUID(str(x)) for x in list(raw)]

def init_tables():
    sql = "\n    CREATE TABLE IF NOT EXISTS sources (\n        id UUID PRIMARY KEY,\n        name TEXT NOT NULL,\n        level SMALLINT NOT NULL CHECK (level BETWEEN 1 AND 4),\n        license TEXT DEFAULT '',\n        url TEXT DEFAULT '',\n        hash TEXT NOT NULL,\n        status TEXT NOT NULL DEFAULT 'pending',\n        created_at TIMESTAMPTZ NOT NULL DEFAULT now()\n    );\n\n    CREATE TABLE IF NOT EXISTS knowledge_versions (\n        version TEXT PRIMARY KEY,\n        source_ids UUID[] NOT NULL DEFAULT '{}',\n        published_at TIMESTAMPTZ,\n        rollback_of TEXT\n    );\n\n    CREATE TABLE IF NOT EXISTS parsed_documents (\n        id UUID PRIMARY KEY,\n        source_id UUID NOT NULL REFERENCES sources(id),\n        knowledge_version TEXT DEFAULT '',\n        kind TEXT NOT NULL,\n        content JSONB NOT NULL,\n        content_hash TEXT NOT NULL,\n        created_at TIMESTAMPTZ NOT NULL DEFAULT now()\n    );\n\n    CREATE TABLE IF NOT EXISTS metric_catalog (\n        id UUID PRIMARY KEY,\n        metric_code TEXT NOT NULL,\n        name_cn TEXT NOT NULL,\n        name_en TEXT DEFAULT '',\n        category TEXT DEFAULT '',\n        unit TEXT DEFAULT '',\n        ref_low DOUBLE PRECISION,\n        ref_high DOUBLE PRECISION,\n        ref_text TEXT DEFAULT '',\n        direction TEXT DEFAULT 'both',\n        advice_hint TEXT DEFAULT '',\n        source_id UUID NOT NULL REFERENCES sources(id),\n        knowledge_version TEXT DEFAULT ''\n    );\n\n    CREATE TABLE IF NOT EXISTS health_reports (\n        id UUID PRIMARY KEY,\n        user_id TEXT NOT NULL,\n        report_date TEXT NOT NULL,\n        institution TEXT DEFAULT '',\n        report_type TEXT DEFAULT 'physical_exam',\n        source_id UUID REFERENCES sources(id),\n        knowledge_version TEXT DEFAULT '',\n        content_hash TEXT DEFAULT '',\n        created_at TIMESTAMPTZ NOT NULL DEFAULT now()\n    );\n\n    CREATE INDEX IF NOT EXISTS idx_health_reports_user\n        ON health_reports (user_id, report_date DESC);\n\n    CREATE TABLE IF NOT EXISTS health_metrics (\n        id UUID PRIMARY KEY,\n        report_id UUID NOT NULL REFERENCES health_reports(id) ON DELETE CASCADE,\n        user_id TEXT NOT NULL,\n        metric_code TEXT NOT NULL,\n        metric_name TEXT NOT NULL,\n        category TEXT DEFAULT '',\n        value_num DOUBLE PRECISION,\n        value_text TEXT DEFAULT '',\n        unit TEXT DEFAULT '',\n        ref_low DOUBLE PRECISION,\n        ref_high DOUBLE PRECISION,\n        ref_text TEXT DEFAULT '',\n        flag TEXT DEFAULT 'unknown',\n        measured_at TEXT DEFAULT '',\n        source_page INT\n    );\n\n    CREATE INDEX IF NOT EXISTS idx_health_metrics_user_code\n        ON health_metrics (user_id, metric_code, measured_at);\n\n    CREATE TABLE IF NOT EXISTS health_guidelines (\n        id UUID PRIMARY KEY,\n        doc_type TEXT NOT NULL,\n        evidence_level TEXT DEFAULT 'B',\n        title TEXT NOT NULL,\n        org TEXT DEFAULT '',\n        year INT,\n        topic TEXT DEFAULT '',\n        content TEXT NOT NULL,\n        url TEXT DEFAULT '',\n        source_id UUID NOT NULL REFERENCES sources(id),\n        knowledge_version TEXT DEFAULT ''\n    );\n\n    CREATE TABLE IF NOT EXISTS medical_cases (\n        id UUID PRIMARY KEY,\n        case_code TEXT NOT NULL,\n        age_band TEXT DEFAULT '',\n        sex TEXT DEFAULT '',\n        chief_complaint TEXT DEFAULT '',\n        findings TEXT DEFAULT '',\n        metrics JSONB NOT NULL DEFAULT '{}',\n        diagnosis TEXT DEFAULT '',\n        intervention TEXT DEFAULT '',\n        outcome TEXT DEFAULT '',\n        evidence_level TEXT DEFAULT 'C',\n        source_id UUID NOT NULL REFERENCES sources(id),\n        knowledge_version TEXT DEFAULT ''\n    );\n    "
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()

def insert_source(s: Source) -> Source:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO sources (id, name, level, license, url, hash, status, created_at)\n                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)\n                   ON CONFLICT (id) DO NOTHING', (str(s.id), s.name, s.level, s.license_, s.url, s.hash, s.status, s.created_at))
        conn.commit()
    return s

def delete_by_source(source_id: str):
    sid = str(source_id)
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM parsed_documents WHERE source_id = %s', (sid,))
            cur.execute('DELETE FROM health_metrics WHERE report_id IN\n                   (SELECT id FROM health_reports WHERE source_id = %s)', (sid,))
            cur.execute('DELETE FROM health_reports WHERE source_id = %s', (sid,))
            cur.execute('DELETE FROM metric_catalog WHERE source_id = %s', (sid,))
            cur.execute('DELETE FROM health_guidelines WHERE source_id = %s', (sid,))
            cur.execute('DELETE FROM medical_cases WHERE source_id = %s', (sid,))
            cur.execute('DELETE FROM sources WHERE id = %s', (sid,))
        conn.commit()

def get_source(source_id: UUID) -> Optional[Source]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM sources WHERE id = %s', (str(source_id),))
            row = cur.fetchone()
    return Source(**dict(row)) if row else None

def list_sources(status: str='approved') -> list[Source]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM sources WHERE status = %s ORDER BY created_at DESC', (status,))
            rows = cur.fetchall()
    return [Source(**dict(r)) for r in rows]

def approve_source(source_id: UUID) -> Source:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE sources SET status='approved' WHERE id=%s", (str(source_id),))
        conn.commit()
    return get_source(source_id)

def publish_version(version: str, source_ids: list[UUID]) -> KnowledgeVersion:
    kv = KnowledgeVersion(version=version, source_ids=source_ids, published_at=datetime.utcnow())
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO knowledge_versions (version, source_ids, published_at)\n                   VALUES (%s,%s::uuid[],%s)\n                   ON CONFLICT (version) DO UPDATE SET\n                     source_ids = EXCLUDED.source_ids,\n                     published_at = EXCLUDED.published_at', (kv.version, [str(s) for s in source_ids], kv.published_at))
            for table in ('metric_catalog', 'health_guidelines', 'medical_cases', 'parsed_documents'):
                cur.execute(f"UPDATE {table} SET knowledge_version = %s WHERE knowledge_version = 'draft'", (version,))
        conn.commit()
    materialize_knowledge_docs(version)
    return kv

def _metric_raw_text(row: dict) -> str:
    ref = row.get('ref_text') or ''
    if not ref:
        lo, hi = (row.get('ref_low'), row.get('ref_high'))
        if lo is not None and hi is not None:
            ref = f"{lo}~{hi} {row.get('unit') or ''}".strip()
        elif hi is not None:
            ref = f"<{hi} {row.get('unit') or ''}".strip()
        elif lo is not None:
            ref = f">{lo} {row.get('unit') or ''}".strip()
    parts = [f"体检指标 {row.get('name_cn') or ''}", f"编码 {row.get('metric_code') or ''}", f"类别 {row.get('category') or ''}", f"单位 {row.get('unit') or ''}", f'参考区间 {ref}']
    if row.get('advice_hint'):
        parts.append(f"异常提示 {row['advice_hint']}")
    return ' | '.join((p for p in parts if p.split(' ', 1)[-1].strip()))

def _guideline_raw_text(row: dict) -> str:
    head = f"{row.get('title') or ''}"
    meta = ' '.join((x for x in [row.get('org') or '', str(row.get('year') or ''), f"证据等级{row.get('evidence_level')}" if row.get('evidence_level') else '', row.get('topic') or ''] if x))
    return f"{head}（{meta}）{row.get('content') or ''}".strip()

def _case_raw_text(row: dict) -> str:
    parts = [f"病历案例 {row.get('case_code') or ''}", f"{row.get('sex') or ''} {row.get('age_band') or ''}".strip(), f"主诉 {row.get('chief_complaint') or ''}" if row.get('chief_complaint') else '', f"检查发现 {row.get('findings') or ''}" if row.get('findings') else '', f"诊断 {row.get('diagnosis') or ''}" if row.get('diagnosis') else '', f"干预 {row.get('intervention') or ''}" if row.get('intervention') else '', f"结局 {row.get('outcome') or ''}" if row.get('outcome') else '']
    return ' | '.join((p for p in parts if p.strip()))

def materialize_knowledge_docs(knowledge_version: str) -> int:
    specs = [('metric_catalog', 'metric_catalog', 'SELECT * FROM metric_catalog WHERE knowledge_version = %s', _metric_raw_text), ('guideline', 'health_guidelines', 'SELECT * FROM health_guidelines WHERE knowledge_version = %s', _guideline_raw_text), ('case', 'medical_cases', 'SELECT * FROM medical_cases WHERE knowledge_version = %s', _case_raw_text)]
    count = 0
    with _conn() as conn:
        for kind, _table, query, render in specs:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(query, (knowledge_version,))
                rows = cur.fetchall()
            with conn.cursor() as cur:
                for row in rows:
                    data = dict(row)
                    for key in ('id', 'source_id'):
                        if isinstance(data.get(key), UUID):
                            data[key] = str(data[key])
                    content = {'kind': kind, 'source_type': kind, 'raw_text': render(data), **{k: v for k, v in data.items() if k != 'id'}}
                    content_hash = hashlib.md5(json.dumps(content, sort_keys=True, ensure_ascii=False, default=str).encode()).hexdigest()
                    cur.execute('INSERT INTO parsed_documents\n                           (id, source_id, knowledge_version, kind, content, content_hash)\n                           VALUES (%s,%s,%s,%s,%s,%s)\n                           ON CONFLICT (id) DO UPDATE SET\n                             knowledge_version = EXCLUDED.knowledge_version,\n                             content = EXCLUDED.content,\n                             content_hash = EXCLUDED.content_hash', (str(row['id']), str(row['source_id']), knowledge_version, kind, json.dumps(content, ensure_ascii=False, default=str), content_hash))
                    count += 1
        conn.commit()
    return count

def get_current_version() -> Optional[KnowledgeVersion]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM knowledge_versions ORDER BY published_at DESC LIMIT 1')
            row = cur.fetchone()
    if row:
        d = dict(row)
        d['source_ids'] = _parse_uuid_list(d.get('source_ids'))
        return KnowledgeVersion(**d)
    return None

def rollback_version(version: str) -> KnowledgeVersion:
    current = get_current_version()
    new_v = f"{version}_rb_{datetime.utcnow().strftime('%Y%m%d_%H%M')}"
    return publish_version(new_v, current.source_ids)

def insert_parsed(doc: ParsedDocument) -> ParsedDocument:
    if not doc.content_hash:
        doc.content_hash = hashlib.md5(json.dumps(doc.content, sort_keys=True).encode()).hexdigest()
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO parsed_documents (id, source_id, knowledge_version, kind, content, content_hash)\n                   VALUES (%s,%s,%s,%s,%s,%s)\n                   ON CONFLICT (id) DO NOTHING', (str(doc.id), str(doc.source_id), doc.knowledge_version, doc.kind, json.dumps(doc.content), doc.content_hash))
        conn.commit()
    return doc

def find_parsed_by_hash(content_hash: str) -> Optional[ParsedDocument]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM parsed_documents WHERE content_hash = %s LIMIT 1', (content_hash,))
            row = cur.fetchone()
    if row:
        d = dict(row)
        d['content'] = d.get('content', {}) if isinstance(d.get('content'), dict) else json.loads(d.get('content', '{}'))
        return ParsedDocument(**d)
    return None

def insert_metric_catalog(row: MetricCatalogRow) -> MetricCatalogRow:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO metric_catalog\n                   (id, metric_code, name_cn, name_en, category, unit, ref_low, ref_high,\n                    ref_text, direction, advice_hint, source_id, knowledge_version)\n                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)\n                   ON CONFLICT (id) DO NOTHING', (str(row.id), row.metric_code, row.name_cn, row.name_en, row.category, row.unit, row.ref_low, row.ref_high, row.ref_text, row.direction, row.advice_hint, str(row.source_id), row.knowledge_version))
        conn.commit()
    return row

def get_metric_by_code(metric_code: str, knowledge_version: Optional[str]=None) -> Optional[MetricCatalogRow]:
    sql = 'SELECT * FROM metric_catalog WHERE metric_code = %s'
    params: list = [metric_code]
    if knowledge_version:
        sql += ' AND knowledge_version = %s'
        params.append(knowledge_version)
    sql += ' LIMIT 1'
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, tuple(params))
            row = cur.fetchone()
    return MetricCatalogRow(**dict(row)) if row else None

def find_metric_by_name(name: str) -> Optional[MetricCatalogRow]:
    n = (name or '').strip()
    if not n:
        return None
    from app.factory.metric_aliases import resolve_metric_alias
    code = resolve_metric_alias(n)
    if code:
        row = get_metric_by_code(code)
        if row:
            return row
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM metric_catalog\n                   WHERE name_cn = %s OR name_en = %s OR metric_code = %s\n                   LIMIT 1', (n, n, n.upper()))
            row = cur.fetchone()
    if row:
        return MetricCatalogRow(**dict(row))
    like = f'%{n}%'
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM metric_catalog\n                   WHERE name_cn ILIKE %s OR name_en ILIKE %s OR metric_code ILIKE %s\n                   LIMIT 1', (like, like, like))
            row = cur.fetchone()
    return MetricCatalogRow(**dict(row)) if row else None

def list_metric_catalog(knowledge_version: Optional[str]=None) -> list[MetricCatalogRow]:
    sql = 'SELECT * FROM metric_catalog'
    params: tuple = ()
    if knowledge_version:
        sql += ' WHERE knowledge_version = %s'
        params = (knowledge_version,)
    sql += ' ORDER BY category, metric_code'
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [MetricCatalogRow(**dict(r)) for r in rows]

def insert_guideline(g: HealthGuideline) -> HealthGuideline:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO health_guidelines\n                   (id, doc_type, evidence_level, title, org, year, topic, content, url,\n                    source_id, knowledge_version)\n                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)\n                   ON CONFLICT (id) DO NOTHING', (str(g.id), g.doc_type, g.evidence_level, g.title, g.org, g.year, g.topic, g.content, g.url, str(g.source_id), g.knowledge_version))
        conn.commit()
    return g

def list_guidelines(knowledge_version: Optional[str]=None) -> list[HealthGuideline]:
    sql = 'SELECT * FROM health_guidelines'
    params: tuple = ()
    if knowledge_version:
        sql += ' WHERE knowledge_version = %s'
        params = (knowledge_version,)
    sql += ' ORDER BY evidence_level, year DESC NULLS LAST'
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [HealthGuideline(**dict(r)) for r in rows]

def insert_case(c: MedicalCase) -> MedicalCase:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO medical_cases\n                   (id, case_code, age_band, sex, chief_complaint, findings, metrics,\n                    diagnosis, intervention, outcome, evidence_level, source_id, knowledge_version)\n                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)\n                   ON CONFLICT (id) DO NOTHING', (str(c.id), c.case_code, c.age_band, c.sex, c.chief_complaint, c.findings, Json(c.metrics or {}), c.diagnosis, c.intervention, c.outcome, c.evidence_level, str(c.source_id), c.knowledge_version))
        conn.commit()
    return c

def list_cases(knowledge_version: Optional[str]=None) -> list[MedicalCase]:
    sql = 'SELECT * FROM medical_cases'
    params: tuple = ()
    if knowledge_version:
        sql += ' WHERE knowledge_version = %s'
        params = (knowledge_version,)
    sql += ' ORDER BY case_code'
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
    return [MedicalCase(**dict(r)) for r in rows]

def insert_health_report(r: HealthReport) -> HealthReport:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('INSERT INTO health_reports\n                   (id, user_id, report_date, institution, report_type, source_id,\n                    knowledge_version, content_hash, created_at)\n                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)\n                   ON CONFLICT (id) DO NOTHING', (str(r.id), r.user_id, r.report_date, r.institution, r.report_type, str(r.source_id) if r.source_id else None, r.knowledge_version, r.content_hash, r.created_at))
        conn.commit()
    return r

def find_report_by_hash(user_id: str, content_hash: str) -> Optional[HealthReport]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM health_reports WHERE user_id = %s AND content_hash = %s LIMIT 1', (user_id, content_hash))
            row = cur.fetchone()
    return HealthReport(**dict(row)) if row else None

def list_reports_by_user(user_id: str) -> list[HealthReport]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM health_reports WHERE user_id = %s ORDER BY report_date DESC', (user_id,))
            rows = cur.fetchall()
    return [HealthReport(**dict(r)) for r in rows]

def get_health_report(report_id: str) -> Optional[HealthReport]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM health_reports WHERE id = %s', (str(report_id),))
            row = cur.fetchone()
    return HealthReport(**dict(row)) if row else None

def delete_report(report_id: str):
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute('DELETE FROM health_reports WHERE id = %s', (str(report_id),))
        conn.commit()

def insert_metrics(metrics: list[HealthMetric]) -> int:
    if not metrics:
        return 0
    with _conn() as conn:
        with conn.cursor() as cur:
            for m in metrics:
                cur.execute('INSERT INTO health_metrics\n                       (id, report_id, user_id, metric_code, metric_name, category,\n                        value_num, value_text, unit, ref_low, ref_high, ref_text,\n                        flag, measured_at, source_page)\n                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)\n                       ON CONFLICT (id) DO NOTHING', (str(m.id), str(m.report_id), m.user_id, m.metric_code, m.metric_name, m.category, m.value_num, m.value_text, m.unit, m.ref_low, m.ref_high, m.ref_text, m.flag, m.measured_at, m.source_page))
        conn.commit()
    return len(metrics)

def list_metrics_by_report(report_id: str) -> list[HealthMetric]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM health_metrics WHERE report_id = %s ORDER BY category, metric_code', (str(report_id),))
            rows = cur.fetchall()
    return [HealthMetric(**dict(r)) for r in rows]

def list_metric_history(user_id: str, metric_code: str, limit: int=10) -> list[HealthMetric]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM health_metrics\n                   WHERE user_id = %s AND metric_code = %s\n                   ORDER BY measured_at DESC\n                   LIMIT %s', (user_id, metric_code, limit))
            rows = cur.fetchall()
    return [HealthMetric(**dict(r)) for r in rows]

def latest_metrics(user_id: str, report_id: Optional[str]=None) -> list[HealthMetric]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if report_id is None:
                cur.execute('SELECT id FROM health_reports WHERE user_id = %s\n                       ORDER BY report_date DESC LIMIT 1', (user_id,))
                row = cur.fetchone()
                if not row:
                    return []
                report_id = str(row['id'])
            cur.execute('SELECT * FROM health_metrics WHERE report_id = %s ORDER BY category, metric_code', (str(report_id),))
            rows = cur.fetchall()
    return [HealthMetric(**dict(r)) for r in rows]

def search_metrics_by_keyword(user_id: str, keyword: str, limit: int=20) -> list[HealthMetric]:
    like = f'%{keyword.strip()}%'
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT * FROM health_metrics\n                   WHERE user_id = %s\n                     AND (metric_name ILIKE %s OR category ILIKE %s OR metric_code ILIKE %s)\n                   ORDER BY measured_at DESC\n                   LIMIT %s', (user_id, like, like, like, limit))
            rows = cur.fetchall()
    return [HealthMetric(**dict(r)) for r in rows]
