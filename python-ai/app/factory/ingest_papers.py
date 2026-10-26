import argparse
import csv
import hashlib
import io
import json
import logging
import zipfile
from pathlib import Path
from uuid import uuid5, NAMESPACE_URL
import pdfplumber
from app.factory.repository import init_tables, insert_source, delete_by_source, _conn
from app.factory.models import Source
logger = logging.getLogger(__name__)
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_DIET_ZIP = _PROJECT_ROOT / 'papers_diet_advice_300.zip'
_OLD_ZIP = _PROJECT_ROOT / 'papers_200.zip'
ZIP_PATH = _DIET_ZIP if _DIET_ZIP.exists() else _OLD_ZIP
KNOWLEDGE_VERSION = 'kv_20260915_001'
_PAPER_NAMESPACE = 'lha-papers'

def _paper_uuid(pmcid: str):
    return uuid5(NAMESPACE_URL, f'{_PAPER_NAMESPACE}::{pmcid}')

def _load_index(z: zipfile.ZipFile) -> list[dict]:
    for candidate in ('_index.csv', 'papers_200/_index.csv'):
        try:
            data = z.read(candidate).decode('utf-8-sig')
            logger.info('[papers] 索引文件: %s', candidate)
            return list(csv.DictReader(io.StringIO(data)))
        except KeyError:
            continue
    raise FileNotFoundError('zip 中未找到 _index.csv（支持根目录或 papers_200/ 前缀布局）')

def _resolve_file_name(z: zipfile.ZipFile, file_name: str) -> str:
    names = set(z.namelist())
    base = (file_name or '').lstrip('/').split('/')[-1]
    if file_name in names:
        return file_name
    if base in names:
        return base
    matches = [n for n in names if n.split('/')[-1] == base]
    return matches[0] if len(matches) == 1 else file_name

def _is_bad(row: dict) -> bool:
    title = str(row.get('title') or '')
    pub_type = str(row.get('pub_type') or '')
    return 'Retract' in title or 'Retract' in pub_type or 'Erratum' in pub_type or title.startswith('Correction')

def _extract_text_pdf(z: zipfile.ZipFile, file_name: str) -> str:
    raw = z.read(file_name)
    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        parts = []
        for page in pdf.pages:
            try:
                t = page.extract_text()
            except Exception:
                t = ''
            if t:
                parts.append(t)
        return '\n'.join(parts)

def _extract_text_xml(z: zipfile.ZipFile, file_name: str) -> str:
    import xml.etree.ElementTree as ET
    raw = z.read(file_name)
    text = raw.decode('utf-8', errors='ignore')
    if '<!DOCTYPE' in text:
        head, _, rest = text.partition('<!DOCTYPE')
        _, _, tail = rest.partition('>')
        text = head + tail
    root = ET.fromstring(text)
    parts: list[str] = []
    for section in root.iter():
        tag = section.tag.rpartition('}')[-1].lower()
        if tag in ('abstract', 'body'):
            for block in section.iter():
                block_tag = block.tag.rpartition('}')[-1].lower()
                if block_tag in ('p', 'title', 'caption', 'td', 'th', 'list-item'):
                    t = ''.join(block.itertext()).strip()
                    if t:
                        parts.append(t)
    return '\n'.join(parts)

def _sanitize_text(text: str) -> str:
    return ''.join((ch for ch in text if ch >= ' ' or ch in '\n\t\r'))

def _extract_text(z: zipfile.ZipFile, file_name: str, file_format: str='') -> str:
    is_xml = file_format.strip().lower() == 'xml' or file_name.lower().endswith('.xml')
    if is_xml:
        text = _extract_text_xml(z, file_name)
    else:
        text = _extract_text_pdf(z, file_name)
    return _sanitize_text(text)

def ingest_papers(zip_path: str, knowledge_version: str, limit: int=0) -> dict:
    init_tables()
    with zipfile.ZipFile(zip_path) as z:
        rows = _load_index(z)
        good = [r for r in rows if not _is_bad(r)]
        bad = [r for r in rows if _is_bad(r)]
        logger.info('索引 %d 篇，剔除撤稿/勘误 %d 篇，待摄入 %d 篇', len(rows), len(bad), len(good))
        if limit > 0:
            good = good[:limit]
            logger.info('（--limit=%d，仅处理前 %d 篇）', limit, len(good))
        ingested = 0
        empty = 0
        failed = 0
        for r in good:
            pmcid = str(r.get('pmcid') or '').strip()
            title = str(r.get('title') or '').strip()
            if not pmcid:
                continue
            doc_id = _paper_uuid(pmcid)
            source_id = doc_id
            try:
                file_name = _resolve_file_name(z, str(r.get('file_name') or ''))
                text = _extract_text(z, file_name, str(r.get('file_format') or ''))
            except Exception as e:
                logger.warning('[papers] 解析失败 %s: %s', pmcid, e)
                failed += 1
                continue
            if not text or not text.strip():
                logger.warning('[papers] 文本为空（可能扫描件）%s', pmcid)
                empty += 1
                continue
            delete_by_source(source_id)
            insert_source(Source(id=source_id, name=title[:200] or pmcid, level=2, license=str(r.get('license') or 'CC BY'), url=f"https://doi.org/{r.get('doi')}" if r.get('doi') else '', hash=hashlib.sha256(f'{pmcid}|{title}'.encode('utf-8')).hexdigest(), status='approved'))
            content = {'kind': 'paper', 'source_type': 'paper', 'raw_text': text, 'pmcid': pmcid, 'pmid': str(r.get('pmid') or ''), 'doi': str(r.get('doi') or ''), 'title': title, 'journal': str(r.get('journal') or ''), 'year': int(r.get('year') or 0), 'topic': str(r.get('topic') or ''), 'license': str(r.get('license') or '')}
            content_hash = hashlib.md5(json.dumps(content, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            with _conn() as conn:
                with conn.cursor() as cur:
                    cur.execute('INSERT INTO parsed_documents\n                           (id, source_id, knowledge_version, kind, content, content_hash)\n                           VALUES (%s,%s,%s,%s,%s,%s)\n                           ON CONFLICT (id) DO UPDATE SET\n                             knowledge_version = EXCLUDED.knowledge_version,\n                             content = EXCLUDED.content,\n                             content_hash = EXCLUDED.content_hash', (str(doc_id), str(source_id), knowledge_version, 'paper', json.dumps(content, ensure_ascii=False), content_hash))
                conn.commit()
            ingested += 1
            if ingested % 20 == 0 or ingested == len(good):
                logger.info('[papers] 进度 %d/%d（空文本 %d，失败 %d）', ingested, len(good), empty, failed)
        return {'total': len(rows), 'removed_retracted': len(bad), 'ingested': ingested, 'empty_text': empty, 'failed': failed}

def main():
    parser = argparse.ArgumentParser(description='摄入 OA 论文到知识库')
    parser.add_argument('--zip', default=str(ZIP_PATH), help='论文 zip 路径')
    parser.add_argument('--version', default=KNOWLEDGE_VERSION, help='知识版本')
    parser.add_argument('--limit', type=int, default=0, help='只处理前 N 篇（调试用）')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    result = ingest_papers(args.zip, args.version, args.limit)
    print(json.dumps(result, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    main()
