"""Rerun the existing paper parser and retain auditable local results."""
from pathlib import Path
import collections
from datetime import datetime
import hashlib
import json
import logging
import platform
import sys
import time
import zipfile

PROJECT = Path(__file__).resolve().parents[2]
ROOT = PROJECT.parent
OUT = ROOT / '实验2_解析结果'
sys.path.insert(0, str(PROJECT / 'python-ai'))
from dotenv import load_dotenv
load_dotenv(PROJECT / '.env')
from app.factory.ingest_papers import ingest_papers, _load_index, _is_bad
from app.factory.repository import _conn, init_tables
import pdfplumber

VERSION = 'kv_20260928_001'
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s', handlers=[logging.FileHandler(OUT / 'parse.log', mode='w'), logging.StreamHandler()])
summary = {'version': VERSION, 'started_at': datetime.now().astimezone().isoformat(), 'python': platform.python_version(), 'pdfplumber': pdfplumber.__version__, 'archives': []}
init_tables()
with _conn() as conn, conn.cursor() as cur:
    cur.execute("SELECT count(*) FROM parsed_documents WHERE kind='paper'")
    summary['papers_before'] = cur.fetchone()[0]
indexes = {}
for name in ('papers_200.zip', 'papers_diet_advice_300.zip'):
    archive = ROOT / name
    with zipfile.ZipFile(archive) as z:
        rows = _load_index(z)
        formats = collections.Counter(Path(i.filename).suffix.lower() for i in z.infolist() if not i.is_dir())
    indexes[name] = rows
    started = time.monotonic()
    result = ingest_papers(str(archive), VERSION)
    record = {'archive': name, 'sha256': hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest(), 'pdf_files': formats['.pdf'], 'xml_files': formats['.xml'], 'elapsed_seconds': round(time.monotonic()-started, 3), **result}
    summary['archives'].append(record)
    (OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
    logging.info('ARCHIVE_RESULT %s', json.dumps(record, ensure_ascii=False))

with _conn() as conn, conn.cursor() as cur:
    cur.execute("SELECT id::text, source_id::text, content, content_hash FROM parsed_documents WHERE kind='paper' AND knowledge_version=%s ORDER BY content->>'pmcid'", (VERSION,))
    records = cur.fetchall()
    cur.execute("SELECT count(*) FROM parsed_documents p JOIN sources s ON p.source_id=s.id WHERE p.kind='paper' AND p.knowledge_version=%s", (VERSION,))
    summary['linked_sources'] = cur.fetchone()[0]
by_id = {}
with (OUT / 'parsed_papers.jsonl').open('w') as output:
    for doc_id, source_id, content, content_hash in records:
        by_id[content['pmcid']] = content
        output.write(json.dumps({'id': doc_id, 'source_id': source_id, 'knowledge_version': VERSION, 'content': content, 'content_hash': content_hash}, ensure_ascii=False)+'\n')

with (OUT / 'paper_results.jsonl').open('w') as output:
    for name, rows in indexes.items():
        for row in rows:
            pmcid = str(row.get('pmcid') or '').strip()
            content = by_id.get(pmcid)
            status = 'filtered' if _is_bad(row) else 'stored' if content else 'not_stored'
            output.write(json.dumps({'archive': name, 'pmcid': pmcid, 'title': row.get('title'), 'file_name': row.get('file_name'), 'status': status, 'characters': len(content['raw_text']) if content else 0}, ensure_ascii=False)+'\n')
lengths = [len(c['raw_text']) for c in by_id.values()]
summary.update({'finished_at': datetime.now().astimezone().isoformat(), 'database_papers': len(records), 'unique_pmcids': len(by_id), 'empty_stored_texts': sum(not c['raw_text'].strip() for c in by_id.values()), 'total_characters': sum(lengths), 'min_characters': min(lengths, default=0), 'max_characters': max(lengths, default=0), 'cross_archive_overlap': sorted(set(r['pmcid'] for r in indexes['papers_200.zip']) & set(r['pmcid'] for r in indexes['papers_diet_advice_300.zip']))})
(OUT / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2)+'\n')
logging.info('FINAL_RESULT %s', json.dumps(summary, ensure_ascii=False))
indexed_ids = {r['pmcid'] for rows in indexes.values() for r in rows if not _is_bad(r)}
minimum_stored = sum(r['ingested'] for r in summary['archives']) - len(summary['cross_archive_overlap'])
if not (minimum_stored <= summary['database_papers'] <= len(indexed_ids) and set(by_id) <= indexed_ids):
    raise RuntimeError('Database count requires investigation')
