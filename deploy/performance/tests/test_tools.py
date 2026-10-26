import asyncio
import gzip
import importlib.util
import json
from pathlib import Path
import time

import httpx
import pytest

BASE = Path(__file__).resolve().parents[1]


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


client = module('perf_client', BASE / 'client/load_client.py')
record = module('perf_record', BASE.parent / 'observability/run_record.py')


def config(name='smoke'):
    return json.loads((BASE / 'config' / (name + '.json')).read_text())


def test_production_load_is_disabled():
    cfg = config('capacity')
    with pytest.raises(ValueError, match='production'):
        client.validate(cfg, 'https://www.smproject.site', {'ready_for_load': True})
    client.validate(config(), 'https://www.smproject.site')


def test_load_requires_recent_matching_readiness():
    cfg = config('capacity')
    with pytest.raises(ValueError, match='readiness'):
        client.validate(cfg, 'https://test.example.com')
    report = {'ready_for_load': True, 'checked_unix': time.time(), 'base_url': 'https://test.example.com'}
    client.validate(cfg, report['base_url'], report)
    report['checked_unix'] -= 7200
    with pytest.raises(ValueError, match='stale'):
        client.validate(cfg, report['base_url'], report)


@pytest.mark.parametrize('key,value', [('max_inflight', 0), ('max_tasks', 1000000), ('duration_seconds', float('nan'))])
def test_load_limits(key, value):
    cfg = config()
    cfg[key] = value
    with pytest.raises(ValueError):
        client.validate(cfg, 'https://test.example.com')


def test_credentials_not_allowed_in_url():
    with pytest.raises(ValueError):
        client.validate(config(), 'https://user:password@test.example.com')


def test_sample_validation(tmp_path):
    path = tmp_path / 'samples.json'
    path.write_text(json.dumps([{'name':'x','expected':'published','images':[{'path':'missing.png'}]}]))
    with pytest.raises(ValueError, match='missing'):
        client.load_samples(path)


@pytest.mark.asyncio
async def test_sse_multiline_and_heartbeats():
    async def lines():
        for line in [': heartbeat', '', 'id: 7', 'data: {"result":', 'data: {"status":"published"}}', '']:
            yield line
    events = [v async for v in client.sse_events(lines())]
    assert len(events) == 1 and events[0]['id'] == '7'
    assert events[0]['data']['result']['status'] == 'published'


def credentials():
    return {'RAG_BASE_URL':'https://test.example.com', 'RAG_TEST_EMAIL':'test@example.com',
            'RAG_TEST_PASSWORD':'never-log-this-secret', 'RAG_TEST_TENANT_ID':'tenant'}


def fake_transport(status='awaiting_images', publish=False, broken=False, slow=False, metrics_count=0, model_calls=0, tokens=0):
    state = {'streams':0, 'resumes':0, 'requests':[]}
    async def handler(request):
        state['requests'].append((request.method, request.url.path, request.headers.get('Last-Event-ID')))
        path = request.url.path
        data = {}
        if path.endswith('/auth/login'):
            data = {'access_token':'never-log-token'}
        elif path == '/api/v1/uploads':
            data = {'image_key':'key.png'}
        elif path == '/api/v1/tasks':
            data = {'task_id':'task'}
        elif path.endswith('/events'):
            state['streams'] += 1
            if slow:
                await asyncio.sleep(0.03)
            if broken:
                content = 'id: 1\ndata: {"stage": {"name":"observing"}}\n\n'
            else:
                actual = 'awaiting_publish_confirm' if publish and not state['resumes'] else status
                content = 'id: 1\ndata: ' + json.dumps({'result':{'status':actual}}) + '\n\n'
            return httpx.Response(200, headers={'Content-Type':'text/event-stream'}, text=content)
        elif path.endswith('/resume'):
            state['resumes'] += 1
            data = {'status':'published'}
        elif path.endswith('/versions'):
            data = {'items':[{'id':'report','version':1}]}
        elif path == '/api/v1/reports/report':
            data = {'id':'report','task_id':'task','status':status,'metrics':[{}]*metrics_count,'sections':{'observation':'synthetic'}}
        elif path.endswith('/cost'):
            data = {'total_tokens':tokens,'call_count':model_calls}
        else:
            raise AssertionError(path)
        return httpx.Response(200, json={'code':0,'data':data})
    return httpx.MockTransport(handler), state


def runner(tmp_path, cfg=None, **kwargs):
    cfg = cfg or config()
    transport,state = fake_transport(**kwargs)
    thresholds = json.loads((BASE/'config/thresholds.json').read_text())
    return client.LoadClient(cfg, credentials(), tmp_path, 'test-run', thresholds, transport=transport),state


@pytest.mark.asyncio
async def test_smoke_result_and_no_secrets(tmp_path):
    load, state = runner(tmp_path)
    summary = await load.run()
    assert summary['successful_expected_results'] == 1
    assert summary['readable_reports'] == 0
    assert summary['observed_tokens'] == 0
    text = ''.join(p.read_text() for p in tmp_path.iterdir())
    assert 'never-log' not in text


@pytest.mark.asyncio
async def test_report_requires_readback_and_publish_confirmation(tmp_path):
    cfg = config('baseline')
    load,state = runner(tmp_path, cfg, status='published', publish=True)
    load.samples = [{'name':'report','expected':'published','images':[{'path':'synthetic:1x1'}]}]
    await load.login()
    row = await load.one(0)
    assert row['success'] and row['report_id'] == 'report' and state['resumes'] == 1
    await load.http.aclose()
    load.log.close(); load.result_log.close()


@pytest.mark.asyncio
async def test_broken_stream_halts_further_tasks(tmp_path):
    load,state = runner(tmp_path, broken=True)
    summary = await load.run()
    assert summary['unresolved_tasks'] == 1
    assert 'unresolved_task_requires_server_check' in summary['stop_reasons']


@pytest.mark.asyncio
async def test_reconnect_carries_last_event_id(tmp_path):
    cfg = config(); cfg['sse_reconnects'] = 1
    load,state = runner(tmp_path, cfg, broken=True)
    await load.run()
    streams = [r for r in state['requests'] if r[1].endswith('/events')]
    assert len(streams) == 2 and streams[1][2] == '1'


@pytest.mark.asyncio
async def test_arrival_overflow_is_recorded(tmp_path):
    cfg = config('arrival'); cfg.update(max_tasks=6, max_inflight=1, arrival_per_minute=6000)
    load,state = runner(tmp_path, cfg, slow=True)
    async def guard():
        load.metrics_ready.set()
        await load.stop.wait()
    load.monitor = guard
    result = await load.run()
    assert result['planned_arrivals'] == 6
    assert 'arrival_not_dispatched' in (tmp_path/'client-events.jsonl').read_text()
    assert result['submitted_tasks'] < 6


def test_export_logs_join_and_time_filter(tmp_path):
    logs=tmp_path/'logs';logs.mkdir()
    (logs/'task-events.jsonl').write_text('\n'.join(json.dumps(r) for r in [
        {'ts_unix':10,'run_id':'run','task_id':'task'},
        {'ts_unix':11,'task_id':'task','event':'joined'},
        {'ts_unix':12,'task_id':'other'}, {'ts_unix':30,'run_id':'run'}]))
    (logs/'resource-samples.jsonl').write_text(json.dumps({'ts_unix':12,'values':{}}))
    nginx=tmp_path/'nginx.log';nginx.write_text(json.dumps({'ts_unix':12,'run_id':'run'}))
    out=tmp_path/'out';out.mkdir()
    counts=record.export_logs(tmp_path,out,'run',9,20,nginx)
    assert counts['task-events']['records']==2
    with gzip.open(out/'task-events.jsonl.gz','rt') as stream:
        assert len(stream.readlines())==2
    assert counts['nginx-events']['records']==1


def test_metric_export_includes_milvus_chunks_and_partial_errors(tmp_path,monkeypatch):
    calls=[]
    def api(base,path,params):
        calls.append(params)
        if 'lha-milvus' in params['query']:
            raise OSError('down')
        return {'result':[]}
    monkeypatch.setattr(record,'api',api)
    errors=record.export_metrics('http://localhost',tmp_path,0,3600)
    assert errors and len(calls)==4
    assert all(c['end']-c['start']<=1800 for c in calls)
    with gzip.open(tmp_path/'metrics.jsonl.gz','rt') as stream:
        records=[json.loads(line) for line in stream]
    assert len(records)==4 and any('lha-milvus' in r['query'] for r in records)


def test_nginx_second_precision_does_not_lose_first_requests(tmp_path):
    (tmp_path/'logs').mkdir()
    nginx=tmp_path/'nginx.log'
    nginx.write_text(json.dumps({'ts_unix':10,'run_id':'run'}))
    out=tmp_path/'out';out.mkdir()
    counts=record.export_logs(tmp_path,out,'run',10.8,20,nginx)
    assert counts['nginx-events']['records']==1


@pytest.mark.asyncio
@pytest.mark.parametrize('failure,expected', [('memory','low_memory'),('disk','low_disk'),('dependency','dependency_down'),('queue','queue_high'),('cpu','cpu_with_queue'),('oom','container_oom'),('missing','metrics_unavailable')])
async def test_guard_stops_on_server_conditions(tmp_path,monkeypatch,failure,expected):
    cfg=config('baseline')
    load,_=runner(tmp_path,cfg)
    load.credentials['RAG_PROMETHEUS_URL']='http://localhost:9190'
    load.thresholds.update(memory_hold_seconds=0,queue_hold_seconds=0,cpu_hold_seconds=0,metrics_unavailable_seconds=0,poll_seconds=0.001)
    rows=[]
    data={'lha_host_memory_available_bytes':5e9,'lha_host_disk_free_bytes':20e9,'lha_host_cpu_percent':0,'lha_executor_queued':0,'lha_dependency_up':1,'up':1}
    if failure=='memory':data['lha_host_memory_available_bytes']=1
    if failure=='disk':data['lha_host_disk_free_bytes']=1
    if failure=='dependency':data['lha_dependency_up']=0
    if failure=='queue':data['lha_executor_queued']=20
    if failure=='cpu':data.update(lha_host_cpu_percent=99,lha_executor_queued=1)
    if failure=='missing':data.pop('lha_executor_queued')
    for name,value in data.items():rows.append({'metric':{'__name__':name},'value':[time.time(),str(value)]})
    rows.append({'metric':{'__name__':'lha_container_state','measure':'oom_killed','container':'test'},'value':[time.time(),'1' if failure=='oom' else '0']})
    original=httpx.AsyncClient
    def create(**kwargs):
        return original(transport=httpx.MockTransport(lambda request:httpx.Response(200,json={'status':'success','data':{'result':rows}})),**kwargs)
    monkeypatch.setattr(client.httpx,'AsyncClient',create)
    await asyncio.wait_for(load.monitor(),timeout=2)
    assert expected in load.stop_reasons
    await load.http.aclose();load.log.close();load.result_log.close()


def single_ready():
    return {'ready_for_single_report':True,'ready_for_load':False,'configured_vlm_model':'qwen3-vl-plus','checked_unix':time.time(),'base_url':'https://www.smproject.site'}


def test_single_report_allows_bounded_production_check_without_load_readiness():
    client.validate(config('single-report'),'https://www.smproject.site',single_ready())


@pytest.mark.parametrize('key,value',[('max_tasks',2),('max_inflight',2),('concurrency',2),('task_timeout_seconds',301),('max_total_tokens',30001),('sse_reconnects',1),('duplicate_create',True),('disconnect_after_events',1)])
def test_single_report_rejects_escalation(key,value):
    cfg=config('single-report');cfg[key]=value
    with pytest.raises(ValueError):
        client.validate(cfg,'https://www.smproject.site',single_ready())


def test_single_report_requires_fresh_readiness():
    report=single_ready();report['checked_unix']-=601
    with pytest.raises(ValueError,match='Fresh'):
        client.validate(config('single-report'),'https://www.smproject.site',report)


@pytest.mark.asyncio
async def test_single_report_requires_saved_metrics_and_real_usage(tmp_path):
    load,_=runner(tmp_path,config('single-report'),status='published',metrics_count=6,model_calls=4,tokens=1000)
    load.samples=[{'name':'synthetic','expected':'published','images':[{'path':'synthetic:1x1'}]}]
    await load.login()
    row=await load.one(0)
    assert row['success'] and row['metrics_count']==6 and row['model_call_count']==4
    assert 'create_api_seconds' in row
    await load.http.aclose();load.log.close();load.result_log.close()


@pytest.mark.asyncio
async def test_single_report_zero_usage_is_not_success(tmp_path):
    load,_=runner(tmp_path,config('single-report'),status='published',metrics_count=6)
    load.samples=[{'name':'synthetic','expected':'published','images':[{'path':'synthetic:1x1'}]}]
    await load.login()
    row=await load.one(0)
    assert not row['success'] and 'real_model_usage_not_observed' in load.stop_reasons
    await load.http.aclose();load.log.close();load.result_log.close()


def test_baseline_report_rejects_fallback_as_healthy(tmp_path):
    analyzer=module('baseline_analyzer',BASE/'client/baseline_report.py')
    c=tmp_path/'client';c.mkdir();server=tmp_path/'server'/'run';server.mkdir(parents=True)
    (c/'run-config.json').write_text(json.dumps({'measurement_origin':'server-local','sample_files_sha256':{'sample.png':'hash'}}))
    row={'run_id':'run','task_id':'task','success':True,'status':'published','model_call_count':7,'total_tokens':17854,'report_readable_seconds':18.2}
    (c/'tasks.jsonl').write_text(json.dumps(row)+'\n')
    with gzip.open(server/'task-events.jsonl.gz','wt') as stream:
        stream.write(json.dumps({'event':'stage_end','task_id':'task','stage':'model.vlm','outcome':'error','error_type':'HTTPStatusError','duration_ms':1200})+'\n')
    rows,stages=analyzer.collect([c],tmp_path/'server',set())
    assert not rows[0]['healthy_baseline']
    assert 'HTTPStatusError' in analyzer.render(rows,stages,'server-local')


def test_fixed_baseline_fixture_is_pinned_and_passes_quality_check():
    import sys
    sys.path.insert(0,str(BASE.parents[1]/'python-ai'))
    from unittest.mock import patch
    from app.agents.image_quality import assess_images
    fixture=BASE/'fixtures/baseline_synthetic.png'
    data=fixture.read_bytes()
    import hashlib
    assert hashlib.sha256(data).hexdigest()==config('single-report')['sample_sha256']
    with patch('app.agents.image_quality._load_image_bytes',return_value=data):
        assert assess_images([{'key':fixture.name,'position':'lab_sheet'}])==[]


def test_live_executor_idle_does_not_depend_on_prometheus_lag():
    preflight=module('perf_preflight',BASE/'preflight.py')
    assert preflight.executor_idle('lha_executor_busy 0\nlha_executor_queued 0\n')
    assert not preflight.executor_idle('lha_executor_busy 1\nlha_executor_queued 0\n')
    assert not preflight.executor_idle('lha_executor_busy 0\nlha_executor_queued 1\n')
    assert not preflight.executor_idle('lha_executor_busy 0\nlha_executor_queued 0\nlha_grpc_active{method="StreamTask"} 1\n')
    assert not preflight.executor_idle('lha_executor_queued 0\n')


def test_single_report_model_is_pinned():
    report=single_ready();report['configured_vlm_model']='another-model'
    with pytest.raises(ValueError,match='pinned'):
        client.validate(config('single-report'),'https://www.smproject.site',report)


def test_pause_gate_disables_all_readiness_even_when_environment_is_healthy(tmp_path,monkeypatch):
    import io
    from types import SimpleNamespace
    from urllib.error import HTTPError
    preflight=module('pause_preflight',BASE/'preflight.py')
    settings={'AUTH_REQUIRED':'true','JWT_SECRET':'test','DATABASE_URL':'unused',
              'LHA_ENVIRONMENT':'isolated','VLM_MODEL':'qwen3-vl-plus',
              'DEEPSEEK_API_KEY':'test','DASHSCOPE_API_KEY':'test','SILICONFLOW_API_KEY':'test'}
    monkeypatch.setattr(preflight,'dotenv_values',lambda path:settings)
    class Connection:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def execute(self,sql):
            if 'schema_migrations' in sql:return SimpleNamespace(fetchall=lambda:[(4,False)])
            if 'to_regclass' in sql:return SimpleNamespace(fetchone=lambda:('uploaded_files',))
            return SimpleNamespace(fetchone=lambda:(1,))
    monkeypatch.setattr(preflight.psycopg,'connect',lambda *a,**kw:Connection())
    monkeypatch.setattr(preflight.subprocess,'run',lambda *a,**kw:SimpleNamespace(stdout='active\n'))
    def respond(request,**kwargs):
        url=request if isinstance(request,str) else request.full_url
        if '/uploads' in url:raise HTTPError(url,401,'Unauthorized',None,None)
        if url.endswith('/metrics'):data=b'lha_executor_busy 0\nlha_executor_queued 0\n'
        elif url.endswith('/models'):data=json.dumps({'data':[{'id':'qwen3-vl-plus'}]}).encode()
        elif '/targets' in url:data=json.dumps({'data':{'activeTargets':[{'labels':{'job':str(i)},'health':'up'} for i in range(4)]}}).encode()
        elif '/query?' in url:
            values={'lha_dependency_up':1,'lha_host_memory_available_bytes':2000000000,'lha_host_disk_free_bytes':3000000000,'lha_executor_busy':0,'lha_executor_queued':0}
            data=json.dumps({'data':{'result':[{'metric':{'__name__':k},'value':[0,str(v)]} for k,v in values.items()]}}).encode()
        else:data=b''
        response=io.BytesIO(data);response.status=200;return response
    monkeypatch.setattr(preflight,'urlopen',respond)
    (tmp_path/'.run').mkdir();(tmp_path/'.run/lha-go').write_bytes(b'fixture');expected=tmp_path/'.run/expected';expected.write_bytes(b'fixture')
    gates=tmp_path/'gates.json';policy={'sse_owner_isolation_verified':True,'report_owner_isolation_verified':True,'real_report_chain_verified':True}
    gates.write_text(json.dumps(policy))
    normal=preflight.check(tmp_path,'https://test.example.com','http://prom.invalid',gates,'isolated',expected)
    assert normal['ready_for_smoke'] and normal['ready_for_single_report'] and normal['ready_for_load']
    policy['testing_paused']=True;gates.write_text(json.dumps(policy))
    paused=preflight.check(tmp_path,'https://test.example.com','http://prom.invalid',gates,'isolated',expected)
    assert not any(paused[k] for k in ['ready_for_smoke','ready_for_single_report','ready_for_load'])
    assert 'testing_not_paused' in paused['blockers']
