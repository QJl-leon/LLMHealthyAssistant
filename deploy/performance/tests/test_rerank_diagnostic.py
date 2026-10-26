from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys

import pytest

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE));sys.path.insert(0,str(BASE/'client'))
from test_bounded_concurrency import make_archive,readiness
from rerank_diagnostic_evidence import validate_diagnostic
from rerank_diagnostic_campaign import reserve_state,CAMPAIGN


def diagnostic_archive(path,status=200,missing=False):
    rows,events=make_archive(path)
    for i in range(2,6):
        row=deepcopy(rows[0]);row.update(task_id=f'task{i}',report_id=f'report{i}');rows.append(row)
        for event in events[:5]:
            event=deepcopy(event);event['task_id']=f'task{i}';events.append(event)
    for i in range(6):
        fields={'task_id':f'task{i}','run_id':'run'}
        events.append({**fields,'event':'rerank_cache','cache_status':'bypass'})
        if not(missing and i==5):
            events.append({**fields,'event':'rerank_http','provider':'jina','model':'jina-reranker-v3','attempt':1,'attempt_id':str(i),'http_status':status,'duration_ms':100,'outcome':'ok' if status==200 else 'error','error_type':'' if status==200 else 'HTTPStatusError'})
        events.append({**fields,'event':'stage_end','stage':'model.rerank','outcome':'ok' if status==200 else 'error','error_type':'' if status==200 else 'HTTPStatusError'})
    p=path/'client/run-config.json';cfg=json.loads(p.read_text());cfg['config']=json.loads((BASE/'config/concurrency-6-diagnostic.json').read_text());p.write_text(json.dumps(cfg))
    p=path/'client/summary.json';summary=json.loads(p.read_text());summary.update(submitted_tasks=6,successful_expected_results=6,readable_reports=6,observed_tokens=66000);p.write_text(json.dumps(summary))
    (path/'client/tasks.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    with gzip.open(path/'task-events.jsonl.gz','wt') as f:f.write(''.join(json.dumps(e)+'\n' for e in events))


@pytest.mark.parametrize('status',[200,400,429,503,None])
def test_status_evidence_is_complete_even_when_healthy_gate_fails(tmp_path,status):
    diagnostic_archive(tmp_path,status=status);result=validate_diagnostic(tmp_path)
    assert result['diagnostic_evidence_complete']
    assert result['healthy_concurrency_passed']==(status==200)
    assert result['rerank_http_status_counts']=={str(status) if status is not None else 'no_response':6}


def test_cached_success_cannot_pass_as_http_diagnosis(tmp_path):
    diagnostic_archive(tmp_path,missing=True);result=validate_diagnostic(tmp_path)
    assert not result['healthy_concurrency_passed'] and not result['diagnostic_evidence_complete']


def test_diagnostic_campaign_is_six_tasks_only_and_cannot_be_replayed():
    state={'campaign':CAMPAIGN,'authorized':True,'batches':[]}
    with pytest.raises(ValueError):reserve_state(state,2,readiness())
    report=reserve_state(state,1,readiness())
    assert report['bounded_concurrency_authorization']['max_campaign_tasks']==6
    with pytest.raises(ValueError):reserve_state(state,1,readiness())
    state['batches'][0]['status']='passed'
    with pytest.raises(ValueError):reserve_state(state,2,readiness())


def test_diagnostic_coordinator_only_runs_one_batch(monkeypatch):
    import run_rerank_diagnostic
    called=[]
    monkeypatch.setattr(run_rerank_diagnostic.sys,'platform','darwin')
    monkeypatch.setattr(run_rerank_diagnostic.sys,'argv',['run_rerank_diagnostic.py'])
    monkeypatch.setattr(run_rerank_diagnostic,'run',lambda args:called.append(args.batch) or 0)
    assert run_rerank_diagnostic.main()==0 and called==[1]
