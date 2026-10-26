import asyncio
from copy import deepcopy
import gzip
import importlib.util
import json
from pathlib import Path
import sys
import time

import httpx
import pytest

BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'client'))
sys.path.insert(0,str(BASE))
from load_client import LoadClient,validate
from concurrency_evidence import validate_batch,SAMPLE_SHA256
from bounded_campaign import reserve_state,CAMPAIGN


def config():return json.loads((BASE/'config/concurrency-two.json').read_text())


def readiness():
    return {'ready_for_single_report':True,'ready_for_load':False,'base_url':'https://www.smproject.site',
            'configured_vlm_model':'qwen3-vl-plus','checked_unix':time.time(),
            'checks':{'real_report_chain_verified':True},
            'bounded_concurrency_authorization':{'reserved_run_id':CAMPAIGN+'_batch_01'}}


def test_bounded_production_does_not_enable_formal_load():
    report=readiness();validate(config(),report['base_url'],report)
    formal=json.loads((BASE/'config/capacity.json').read_text())
    with pytest.raises(ValueError):validate(formal,report['base_url'],report)


@pytest.mark.parametrize('field,value',[('max_tasks',4),('concurrency',3),('max_inflight',3),('max_total_tokens',60001),('task_timeout_seconds',301),('sse_reconnects',1),('duplicate_create',True),('required_vlm_model','other')])
def test_bounded_refuses_escalation(field,value):
    cfg=config();cfg[field]=value
    with pytest.raises(ValueError):validate(cfg,readiness()['base_url'],readiness())


@pytest.mark.parametrize('case',['no_reservation','stale','wrong_model','unverified_chain'])
def test_bounded_requires_reservation_and_current_healthy_model(case):
    report=readiness()
    if case=='no_reservation':report.pop('bounded_concurrency_authorization')
    if case=='stale':report['checked_unix']-=601
    if case=='wrong_model':report['configured_vlm_model']='wrong'
    if case=='unverified_chain':report['checks']['real_report_chain_verified']=False
    with pytest.raises(ValueError):validate(config(),report['base_url'],report)


def test_campaign_reservations_are_ordered_and_never_retried():
    state={'campaign':CAMPAIGN,'authorized':True,'batches':[]}
    with pytest.raises(ValueError):reserve_state(state,2,readiness())
    result=reserve_state(state,1,readiness());assert result['bounded_concurrency_authorization']['reserved_run_id'].endswith('_01')
    with pytest.raises(ValueError):reserve_state(state,1,readiness())
    with pytest.raises(ValueError):reserve_state(state,2,readiness())
    state['batches'][0].update(status='failed',observed_tokens=1000)
    with pytest.raises(ValueError):reserve_state(state,2,readiness())
    state['batches'][0]['status']='passed';reserve_state(state,2,readiness())
    assert sum(e['task_slots_consumed'] for e in state['batches'])==4
    with pytest.raises(ValueError):reserve_state(state,2,readiness())


def make_archive(tmp_path,overlap=True):
    (tmp_path/'client').mkdir()
    cfg={'measurement_origin':'remote-client','sample_files_sha256':{'fixture.png':SAMPLE_SHA256},'config':config()}
    (tmp_path/'client/run-config.json').write_text(json.dumps(cfg))
    env={'files_sha256':{'app.py':'same'},'model_config':{'VLM_MODEL':'qwen3-vl-plus'}}
    manifest={'run_id':'run','start_unix':0,'end_unix':60,'environment':env,'end_environment':env,'export_complete':True,'metric_export_errors':[],'log_export_warnings':[]}
    (tmp_path/'run.json').write_text(json.dumps(manifest))
    rows=[];events=[]
    for i in range(2):
        rows.append({'task_id':f'task{i}','report_id':f'report{i}','run_id':'run','success':True,'unresolved':False,'status':'published','saved_status':'published','metrics_count':7,'nonempty_sections':11,'model_call_count':3,'total_tokens':11000,'report_readable_seconds':22,'report_versions':1})
        for stage in ['model.ocr','model.vlm','orchestrator.report_draft','save_report','orchestrator.vision_observe']:
            second=20 if i==0 else (22 if overlap else 40)
            events.append({'task_id':f'task{i}','run_id':'run','event':'stage_end','stage':stage,'outcome':'ok','ts':f'1970-01-01T00:00:{second:02d}+00:00','duration_ms':10000})
    (tmp_path/'client/tasks.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    summary={'submitted_tasks':2,'successful_expected_results':2,'readable_reports':2,'unresolved_tasks':0,'stop_reasons':[],'observed_tokens':22000}
    (tmp_path/'client/summary.json').write_text(json.dumps(summary))
    with gzip.open(tmp_path/'task-events.jsonl.gz','wt') as stream:stream.write(''.join(json.dumps(e)+'\n' for e in events))
    return rows,events


def test_server_evidence_proves_overlap(tmp_path):
    make_archive(tmp_path);result=validate_batch(tmp_path)
    assert result['healthy_concurrency_passed'] and result['server_vision_overlap_seconds']==8


def test_sequential_success_does_not_pass_concurrency(tmp_path):
    make_archive(tmp_path,overlap=False);result=validate_batch(tmp_path)
    assert not result['healthy_concurrency_passed'] and any('overlapping' in e for e in result['errors'])


@pytest.mark.parametrize('fault',['fallback','missing_task_stage','incomplete_export','duplicate_report','slow'])
def test_failed_or_incomplete_task_blocks_next_batch(tmp_path,fault):
    rows,events=make_archive(tmp_path)
    if fault=='fallback':events[0]['outcome']='error'
    if fault=='missing_task_stage':events=[e for e in events if not(e['task_id']=='task1' and e['stage']=='model.vlm')]
    if fault=='incomplete_export':
        p=tmp_path/'run.json';m=json.loads(p.read_text());m['export_complete']=False;p.write_text(json.dumps(m))
    if fault=='duplicate_report':rows[1]['report_id']=rows[0]['report_id']
    if fault=='slow':
        for row in rows:row['report_readable_seconds']=40
    (tmp_path/'client/tasks.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in rows))
    with gzip.open(tmp_path/'task-events.jsonl.gz','wt') as stream:stream.write(''.join(json.dumps(e)+'\n' for e in events))
    assert not validate_batch(tmp_path)['healthy_concurrency_passed']


@pytest.mark.asyncio
@pytest.mark.parametrize('count',[2,3,4,6,8])
async def test_scheduler_really_runs_bounded_tasks_and_stops_at_limit(tmp_path,count):
    streams=0;active=0;peak=0;created=0;barrier=asyncio.Event()
    async def handler(request):
        nonlocal streams,active,peak,created
        path=request.url.path;data={}
        if path.endswith('/auth/login'):data={'access_token':'test-only'}
        elif path.endswith('/uploads'):data={'image_key':'synthetic.png'}
        elif path=='/api/v1/tasks':
            created+=1;data={'task_id':f'task{created}'}
        elif path.endswith('/events'):
            active+=1;peak=max(peak,active);streams+=1
            if streams==count:barrier.set()
            await asyncio.wait_for(barrier.wait(),timeout=2)
            await asyncio.sleep(0.01);active-=1
            return httpx.Response(200,headers={'Content-Type':'text/event-stream'},text='data: {"result":{"status":"published"}}\n\n')
        elif path.endswith('/versions'):
            task=path.split('/')[-2];data={'items':[{'id':task,'version':1}]}
        elif path.startswith('/api/v1/reports/'):
            task=path.split('/')[-1];data={'id':task,'task_id':task,'status':'published','metrics':[{}],'sections':{'content':'synthetic'}}
        elif path.endswith('/cost'):data={'total_tokens':11000,'call_count':3}
        else:raise AssertionError(path)
        return httpx.Response(200,json={'code':0,'data':data})
    credentials={'RAG_BASE_URL':'https://www.smproject.site','RAG_TEST_EMAIL':'test','RAG_TEST_PASSWORD':'test','RAG_TEST_TENANT_ID':'test'}
    thresholds=json.loads((BASE/'config/thresholds.json').read_text())
    cfg=config();cfg.update(concurrency=count,max_inflight=count,max_tasks=count,max_total_tokens=30000*count)
    runner=LoadClient(cfg,credentials,tmp_path,'run',thresholds,transport=httpx.MockTransport(handler))
    runner.samples=[{'name':'synthetic','expected':'published','images':[{'path':'synthetic:1x1'}]}]
    async def fake_monitor():
        runner.metrics_ready.set();await runner.stop.wait()
    runner.monitor=fake_monitor
    result=await runner.run()
    assert peak==count and created==count and result['successful_expected_results']==count and not result['stop_reasons']
    assert all('started_run_seconds' in row for row in runner.rows)


def test_finalize_only_exports_and_never_reserves_or_submits(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import run_concurrency as coordinator
    calls=[]
    def fake_remote(command,check=True):
        calls.append(command)
        if any('preflight.py' in s for s in command):return SimpleNamespace(stdout=json.dumps({'checks':{'no_active_tasks':True}}),returncode=0)
        if 'complete' in command:return SimpleNamespace(stdout=json.dumps({'healthy_concurrency_passed':True,'errors':[]}),returncode=0)
        return SimpleNamespace(stdout='',returncode=0)
    def fake_process(command,**kwargs):
        calls.append(command);return SimpleNamespace(returncode=0)
    monkeypatch.setattr(coordinator,'remote',fake_remote)
    monkeypatch.setattr(coordinator.subprocess,'run',fake_process)
    monkeypatch.setattr(coordinator,'dotenv_values',lambda p:{'RAG_BASE_URL':'https://www.smproject.site'})
    args=SimpleNamespace(batch=1,out=tmp_path,env_file=tmp_path/'unused',finalize=True,prometheus_url='http://127.0.0.1:9190')
    assert coordinator.run(args)==0
    assert not any('reserve' in call or any('load_client.py' in arg for arg in call) for call in calls)


def test_finalize_leaves_active_tasks_untouched(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import run_concurrency as coordinator
    calls=[]
    def fake_remote(command,check=True):
        calls.append(command);return SimpleNamespace(stdout=json.dumps({'checks':{'no_active_tasks':False}}),returncode=0)
    monkeypatch.setattr(coordinator,'remote',fake_remote)
    monkeypatch.setattr(coordinator,'dotenv_values',lambda p:{'RAG_BASE_URL':'https://www.smproject.site'})
    args=SimpleNamespace(batch=1,out=tmp_path,env_file=tmp_path/'unused',finalize=True,prometheus_url='http://127.0.0.1:9190')
    assert coordinator.run(args)==2 and len(calls)==1
