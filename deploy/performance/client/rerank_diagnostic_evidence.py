"""Review six real rerank attempts, including unsuccessful provider responses."""
from collections import Counter
import gzip
import json
from pathlib import Path
from concurrency_evidence import validate_batch


def validate_diagnostic(directory):
    directory=Path(directory)
    result=validate_batch(directory,expected_tasks=6)
    rows=[json.loads(line) for line in (directory/'client/tasks.jsonl').read_text().splitlines()]
    with gzip.open(directory/'task-events.jsonl.gz','rt') as stream:events=[json.loads(line) for line in stream]
    run_id=result['run_id'];http=[];coverage_errors=[]
    allowed=['task_id','provider','model','attempt_id','http_status','duration_ms','outcome','error_type','retry_after_seconds','document_count','attempt']
    for row in rows:
        task=row.get('task_id')
        selected=[e for e in events if e.get('task_id')==task and e.get('run_id')==run_id]
        bypass=[e for e in selected if e.get('event')=='rerank_cache' and e.get('cache_status')=='bypass']
        attempts=[e for e in selected if e.get('event')=='rerank_http']
        if len(bypass)!=1 or len(attempts)!=1:
            coverage_errors.append(str(task)+': Expected one scoped cache bypass and one HTTP attempt')
        for e in attempts:
            if e.get('provider')!='jina' or e.get('model')!='jina-reranker-v3' or e.get('attempt')!=1:
                coverage_errors.append(str(task)+': Unexpected provider/model/attempt')
            status=e.get('http_status')
            if status is not None and (type(status) is not int or not 100<=status<=599):
                coverage_errors.append(str(task)+': Invalid HTTP status')
            if e.get('outcome') not in ('ok','error') or e.get('duration_ms',-1)<0:
                coverage_errors.append(str(task)+': Incomplete HTTP observation')
            http.append({key:e.get(key) for key in allowed})
    complete=len(rows)==6 and len(http)==6 and not coverage_errors
    result['diagnostic_evidence_complete']=complete
    result['diagnostic_errors']=coverage_errors
    result['rerank_http_observations']=http
    result['rerank_http_status_counts']=dict(Counter(str(e['http_status']) if e['http_status'] is not None else 'no_response' for e in http))
    result['healthy_concurrency_passed']=result['healthy_concurrency_passed'] and complete and all(e['outcome']=='ok' for e in http)
    result['scope']='Six diagnostic reports with rerank cache bypass; no retries or automatic concurrency 8'
    return result
