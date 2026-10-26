"""Recover the PDF with an incompatible page tree using installed PDFium."""
from pathlib import Path
import csv
from datetime import datetime
import io
import json
import logging
import sys
import tempfile
import time
import zipfile

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'实验2_解析结果'
sys.path.insert(0,str(ROOT/'LLMHealthyAssistant/python-ai'))
from dotenv import load_dotenv
load_dotenv(ROOT/'LLMHealthyAssistant/.env')
from app.factory import ingest_papers as parser
from app.factory.repository import _conn
import pypdfium2

summary=json.loads((OUT/'summary.json').read_text())
assert 'finished_at' in summary
logging.basicConfig(level=logging.INFO,format='%(asctime)s %(levelname)s %(message)s',handlers=[logging.FileHandler(OUT/'recovery.log',mode='w'),logging.StreamHandler()])
version=summary['version']
pmcid='PMC13131944'
original=parser._extract_text_pdf

def extract(z,name):
    text=original(z,name)
    if text.strip():
        return text
    doc=pypdfium2.PdfDocument(z.read(name))
    parts=[]
    try:
        for page in doc:
            textpage=page.get_textpage()
            try:
                parts.append(textpage.get_text_range())
            finally:
                textpage.close()
                page.close()
    finally:
        doc.close()
    return '\n'.join(parts)

started=time.monotonic()
with zipfile.ZipFile(ROOT/'papers_200.zip') as source:
    rows=parser._load_index(source)
    selected=[r for r in rows if r['pmcid']==pmcid]
    assert len(selected)==1
    index=io.StringIO()
    writer=csv.DictWriter(index,fieldnames=list(rows[0]))
    writer.writeheader();writer.writerows(selected)
    with tempfile.TemporaryDirectory(prefix='lha-paper-recovery-') as tmp:
        archive=Path(tmp)/'recovery.zip'
        with zipfile.ZipFile(archive,'w') as target:
            target.writestr('_index.csv',index.getvalue())
            for row in selected:
                name=parser._resolve_file_name(source,row['file_name'])
                target.writestr(name,source.read(name))
        parser._extract_text_pdf=extract
        result=parser.ingest_papers(str(archive),version)
assert result['ingested']==1,result
(OUT/'primary_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
summary['recovery']={'pmcid':pmcid,'engine':'pypdfium2','reason':'pdfplumber reports zero pages; PDFium reads 19 pages','elapsed_seconds':round(time.monotonic()-started,3),**result}
with _conn() as conn,conn.cursor() as cur:
    cur.execute("SELECT id::text,source_id::text,content,content_hash FROM parsed_documents WHERE kind='paper' AND knowledge_version=%s ORDER BY content->>'pmcid'",(version,))
    records=cur.fetchall()
    cur.execute("SELECT count(*) FROM parsed_documents p JOIN sources s ON p.source_id=s.id WHERE p.kind='paper' AND p.knowledge_version=%s",(version,))
    summary['linked_sources']=cur.fetchone()[0]
by_id={}
with (OUT/'parsed_papers.jsonl').open('w') as f:
    for doc_id,source_id,content,content_hash in records:
        by_id[content['pmcid']]=content
        f.write(json.dumps({'id':doc_id,'source_id':source_id,'knowledge_version':version,'content':content,'content_hash':content_hash},ensure_ascii=False)+'\n')
rows=[json.loads(line) for line in (OUT/'paper_results.jsonl').read_text().splitlines()]
for row in rows:
    if row['pmcid']==pmcid:
        row.update(status='stored',characters=len(by_id[pmcid]['raw_text']),recovery_engine='pypdfium2')
(OUT/'paper_results.jsonl').write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))
lengths=[len(c['raw_text']) for c in by_id.values()]
summary.update(finished_at=datetime.now().astimezone().isoformat(),database_papers=len(records),unique_pmcids=len(by_id),empty_stored_texts=sum(not c['raw_text'].strip() for c in by_id.values()),total_characters=sum(lengths),min_characters=min(lengths),max_characters=max(lengths))
assert summary['database_papers']==500 and summary['unique_pmcids']==500
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
logging.info('Recovery completed: %s',json.dumps(summary['recovery'],ensure_ascii=False))
