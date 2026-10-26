from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys

import pytest

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE));sys.path.insert(0,str(BASE/'client'))
from test_bounded_concurrency import readiness,make_archive
from concurrency_evidence import validate_batch
from high_step_campaign import reserve_state,CAMPAIGN
from load_client import validate


def config(n):return json.loads((BASE/f'config/concurrency-{n}.json').read_text())


def ready(n):
    report=readiness();report['bounded_concurrency_authorization']={'campaign':CAMPAIGN,'reserved_run_id':f'{CAMPAIGN}_c{n}',
        'max_batch_tasks':n,'max_concurrency':n};return report


@pytest.mark.parametrize('count',[6,8])
def test_high_steps_need_exact_authorization(count):
    cfg=config(count);validate(cfg,'https://www.smproject.site',ready(count))
    with pytest.raises(ValueError):validate(cfg,'https://www.smproject.site',ready(14-count))
    with pytest.raises(ValueError):validate(cfg,'https://www.smproject.site',readiness())
    wrong=ready(count);wrong['bounded_concurrency_authorization']['campaign']='mac_c34_20261019'
    with pytest.raises(ValueError):validate(cfg,'https://www.smproject.site',wrong)


@pytest.mark.parametrize('count',[6,8])
@pytest.mark.parametrize('field,value',[('max_tasks',16),('max_inflight',16),('concurrency',16),('sse_reconnects',1),('task_timeout_seconds',301),('max_total_tokens',240001)])
def test_high_steps_remain_bounded(count,field,value):
    cfg=config(count);cfg[field]=value
    with pytest.raises(ValueError):validate(cfg,'https://www.smproject.site',ready(count))


def test_high_ledger_requires_passed_six_before_eight_and_cannot_replay():
    state={'campaign':CAMPAIGN,'authorized':True,'batches':[]}
    with pytest.raises(ValueError):reserve_state(state,2,readiness())
    reserve_state(state,1,readiness())
    assert state['batches'][0]['task_slots_consumed']==6
    with pytest.raises(ValueError):reserve_state(state,1,readiness())
    with pytest.raises(ValueError):reserve_state(state,2,readiness())
    state['batches'][0].update(status='failed',observed_tokens=60000)
    with pytest.raises(ValueError):reserve_state(state,2,readiness())
    state['batches'][0]['status']='passed';reserve_state(state,2,readiness())
    assert sum(e['task_slots_consumed'] for e in state['batches'])==14
    with pytest.raises(ValueError):reserve_state(state,2,readiness())


@pytest.mark.parametrize('count',[6,8])
@pytest.mark.parametrize('overlap',[True,False])
def test_all_six_or_eight_tasks_need_common_server_overlap(tmp_path,count,overlap):
    rows,events=make_archive(tmp_path)
    for i in range(2,count):
        row=deepcopy(rows[0]);row.update(task_id=f'task{i}',report_id=f'report{i}');rows.append(row)
        for e in events[:5]:
            e=deepcopy(e);e['task_id']=f'task{i}'
            second=20 if overlap else 40
            e['ts']=f'1970-01-01T00:00:{second:02d}.{i:06d}+00:00';events.append(e)
    p=tmp_path/'client/run-config.json';cfg=json.loads(p.read_text());cfg['config']=config(count);p.write_text(json.dumps(cfg))
    p=tmp_path/'client/summary.json';summary=json.loads(p.read_text());summary.update(submitted_tasks=count,successful_expected_results=count,readable_reports=count,observed_tokens=count*11000);p.write_text(json.dumps(summary))
    (tmp_path/'client/tasks.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    with gzip.open(tmp_path/'task-events.jsonl.gz','wt') as f:f.write(''.join(json.dumps(e)+'\n' for e in events))
    checked=validate_batch(tmp_path,expected_tasks=count)
    assert checked['healthy_concurrency_passed']==overlap and checked['tasks']==count


@pytest.mark.parametrize('first_result,expected',[(0,[1,2]),(2,[1])])
def test_high_coordinator_stops_before_eight_if_six_fails(monkeypatch,first_result,expected):
    import run_high_steps
    called=[]
    monkeypatch.setattr(run_high_steps.sys,'platform','darwin');monkeypatch.setattr(run_high_steps.sys,'argv',['run_high_steps.py'])
    monkeypatch.setattr(run_high_steps,'run',lambda args:called.append(args.batch) or (first_result if args.batch==1 else 0))
    assert run_high_steps.main()==first_result and called==expected
