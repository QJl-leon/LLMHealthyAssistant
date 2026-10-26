import gzip
import json
from pathlib import Path
import sys
from copy import deepcopy

import pytest

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE));sys.path.insert(0,str(BASE/'client'))
from test_bounded_concurrency import readiness,make_archive
from load_client import validate
from concurrency_evidence import validate_batch
from step_campaign import reserve_state,CAMPAIGN


def config(count):return json.loads((BASE/f'config/concurrency-{count}.json').read_text())


def ready(count):
    report=readiness();report['bounded_concurrency_authorization']={'campaign':CAMPAIGN,
        'reserved_run_id':f'{CAMPAIGN}_c{count}','max_batch_tasks':count,'max_concurrency':count}
    return report


@pytest.mark.parametrize('count',[3,4])
def test_step_authorization_accepts_only_matching_count(count):
    validate(config(count),'https://www.smproject.site',ready(count))
    with pytest.raises(ValueError):validate(config(count),'https://www.smproject.site',ready(7-count))
    with pytest.raises(ValueError):validate(config(count),'https://www.smproject.site',readiness())


@pytest.mark.parametrize('count',[3,4])
@pytest.mark.parametrize('field,value',[('max_tasks',8),('max_inflight',8),('concurrency',8),('sse_reconnects',1),('max_total_tokens',120001)])
def test_step_limits_cannot_be_raised(count,field,value):
    cfg=config(count);cfg[field]=value
    with pytest.raises(ValueError):validate(cfg,'https://www.smproject.site',ready(count))


def test_step_ledger_orders_batches_and_caps_total_at_seven():
    state={'campaign':CAMPAIGN,'authorized':True,'batches':[]}
    with pytest.raises(ValueError):reserve_state(state,2,readiness())
    report=reserve_state(state,1,readiness());assert report['bounded_concurrency_authorization']['max_batch_tasks']==3
    with pytest.raises(ValueError):reserve_state(state,1,readiness())
    with pytest.raises(ValueError):reserve_state(state,2,readiness())
    state['batches'][0].update(status='failed',observed_tokens=1000)
    with pytest.raises(ValueError):reserve_state(state,2,readiness())
    state['batches'][0]['status']='passed';reserve_state(state,2,readiness())
    assert sum(e['task_slots_consumed'] for e in state['batches'])==7
    with pytest.raises(ValueError):reserve_state(state,2,readiness())


@pytest.mark.parametrize('count',[3,4])
@pytest.mark.parametrize('overlap',[True,False])
def test_stage_evidence_requires_all_expected_tasks_to_overlap(tmp_path,count,overlap):
    rows,events=make_archive(tmp_path)
    for i in range(2,count):
        row=deepcopy(rows[0]);row.update(task_id=f'task{i}',report_id=f'report{i}');rows.append(row)
        for e in list(events[:5]):
            e=deepcopy(e);e['task_id']=f'task{i}'
            second=24+i if overlap else 40+i
            e['ts']=f'1970-01-01T00:00:{second:02d}+00:00';events.append(e)
    cfgpath=tmp_path/'client/run-config.json';cfg=json.loads(cfgpath.read_text());cfg['config']=config(count);cfgpath.write_text(json.dumps(cfg))
    p=tmp_path/'client/summary.json';summary=json.loads(p.read_text());summary.update(submitted_tasks=count,successful_expected_results=count,readable_reports=count,observed_tokens=count*11000);p.write_text(json.dumps(summary))
    (tmp_path/'client/tasks.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    with gzip.open(tmp_path/'task-events.jsonl.gz','wt') as stream:stream.write(''.join(json.dumps(e)+'\n' for e in events))
    checked=validate_batch(tmp_path,expected_tasks=count)
    assert checked['healthy_concurrency_passed']==overlap
    assert checked['tasks']==count


def test_automatic_steps_stop_before_four_if_three_fails(monkeypatch):
    import run_steps
    called=[]
    monkeypatch.setattr(run_steps.sys,'platform','darwin')
    monkeypatch.setattr(run_steps.sys,'argv',['run_steps.py'])
    monkeypatch.setattr(run_steps,'run',lambda args:called.append(args.batch) or 2)
    assert run_steps.main()==2 and called==[1]


def test_automatic_steps_run_only_three_then_four(monkeypatch):
    import run_steps
    called=[]
    monkeypatch.setattr(run_steps.sys,'platform','darwin')
    monkeypatch.setattr(run_steps.sys,'argv',['run_steps.py'])
    monkeypatch.setattr(run_steps,'run',lambda args:called.append(args.batch) or 0)
    assert run_steps.main()==0 and called==[1,2]


def test_mac_dns_failure_happens_before_campaign_reservation(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import httpx
    import run_steps
    commands=[]
    class OfflineHTTP:
        def __init__(self,**kwargs):pass
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def get(self,url,**kwargs):raise httpx.ConnectError('test DNS failure')
    monkeypatch.setattr(run_steps.httpx,'Client',OfflineHTTP)
    monkeypatch.setattr(run_steps,'dotenv_values',lambda p:{'RAG_BASE_URL':'https://www.smproject.site'})
    monkeypatch.setattr(run_steps,'remote',lambda *args,**kwargs:commands.append(args))
    args=SimpleNamespace(batch=1,out=tmp_path,env_file=tmp_path/'unused',finalize=False,prometheus_url='http://127.0.0.1:9190')
    with pytest.raises(httpx.ConnectError):run_steps.run(args)
    assert not commands and not (tmp_path/'mac_c34_20261019_c3').exists()
