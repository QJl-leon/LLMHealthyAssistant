"""Independently verify final database and exported experiment artifacts."""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'实验2_解析结果'
sys.path.insert(0,str(ROOT/'LLMHealthyAssistant/python-ai'))
from dotenv import load_dotenv
load_dotenv(ROOT/'LLMHealthyAssistant/.env')
from app.factory.repository import _conn

summary=json.loads((OUT/'summary.json').read_text())
records=[json.loads(line) for line in (OUT/'parsed_papers.jsonl').read_text().splitlines()]
statuses=[json.loads(line) for line in (OUT/'paper_results.jsonl').read_text().splitlines()]
assert len(records)==len(statuses)==500
assert len({r['id'] for r in records})==len({r['content']['pmcid'] for r in records})==500
for record in records:
    assert record['content']['raw_text'].strip()
    assert record['knowledge_version']==summary['version']
    assert hashlib.md5(json.dumps(record['content'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()==record['content_hash']
assert all(row['status']=='stored' for row in statuses)
with _conn() as conn,conn.cursor() as cur:
    cur.execute("SELECT id::text,content,content_hash FROM parsed_documents WHERE kind='paper' AND knowledge_version=%s",(summary['version'],))
    database={doc_id:(content,content_hash) for doc_id,content,content_hash in cur.fetchall()}
assert len(database)==500
assert all(database[r['id']]==(r['content'],r['content_hash']) for r in records)
assert sum(len(r['content']['raw_text']) for r in records)==summary['total_characters']
checks={'status':'passed','database_papers':len(database),'exported_papers':len(records),'index_status_rows':len(statuses),'unique_pmcids':500,'nonempty_texts':500,'matching_content_hashes':500,'database_export_equal':True,'total_characters':summary['total_characters']}
(OUT/'verification.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(checks,ensure_ascii=False))
