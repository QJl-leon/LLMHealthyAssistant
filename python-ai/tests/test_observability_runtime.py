import contextvars
import json
import logging
import threading
import time
from concurrent.futures import CancelledError

import grpc
import pytest
from app.context import ctx
from app.observability import runtime as obs


def test_stage_failure_and_context_restore(monkeypatch):
    records=[]
    monkeypatch.setattr(obs,'emit',lambda event,**fields: records.append((event,fields)))
    @obs.timed('unit.failure')
    def fail(state):
        assert obs.CORRELATION.get()['task_id']=='task-one'
        raise TimeoutError('secret prompt must never be logged')
    with pytest.raises(TimeoutError): fail({'task_id':'task-one'})
    assert obs.CORRELATION.get()=={}
    end=records[-1][1]
    assert end['outcome']=='error' and end['error_type']=='TimeoutError'
    assert end['duration_ms']>=0
    assert 'secret' not in json.dumps(records)
    assert records[0][1]['execution_id']==end['execution_id']


def test_executor_queue_and_cancel_do_not_leak():
    entered,release=threading.Event(),threading.Event()
    before=obs.QUEUED._value.get()
    with obs.ObservedExecutor(max_workers=1) as executor:
        def block():
            ctx.set_context(task_id='must-not-leak')
            entered.set();assert release.wait(3)
        first=executor.submit(block);assert entered.wait(3)
        second=executor.submit(lambda:(ctx.get_task_id(),obs.WAIT.seconds))
        cancelled=executor.submit(lambda:None)
        assert cancelled.cancel()
        time.sleep(.03);release.set();first.result(timeout=3)
        task,wait=second.result(timeout=3)
        assert task=='' and wait>=.02
    assert obs.QUEUED._value.get()==before


def test_real_grpc_interceptor_stream_and_queue(monkeypatch):
    records=[]
    monkeypatch.setattr(obs,'emit',lambda event,**fields: records.append((event,dict(obs.CORRELATION.get()),fields)))
    from app.server.research.v1 import research_pb2 as pb
    from app.server.research.v1 import research_pb2_grpc as rpc
    entered,release=threading.Event(),threading.Event()
    class Fake(rpc.ResearchServiceServicer):
        def StreamTask(self,request,context):
            entered.set();assert release.wait(3)
            yield pb.TaskEvent(task_id=request.task_id,seq=1,result=pb.TaskResult(status='published'))
        def GetTaskCost(self,request,context):
            return pb.GetTaskCostResponse(task_id=request.task_id)
    executor=obs.ObservedExecutor(max_workers=1)
    server=grpc.server(executor,interceptors=[obs.ObservationInterceptor()])
    rpc.add_ResearchServiceServicer_to_server(Fake(),server)
    port=server.add_insecure_port('127.0.0.1:0');server.start()
    channel=grpc.insecure_channel(f'127.0.0.1:{port}')
    stub=rpc.ResearchServiceStub(channel)
    try:
        stream=stub.StreamTask(pb.StreamTaskRequest(task_id='test-stream'),metadata=(('x-run-id','run-unit'),))
        assert entered.wait(3)
        pending=stub.GetTaskCost.future(pb.GetTaskCostRequest(task_id='cost'),timeout=3)
        time.sleep(.05);release.set()
        assert next(stream).result.status=='published'
        list(stream)
        assert pending.result().task_id=='cost'
    finally:
        release.set();channel.close();server.stop(0).wait();executor.shutdown()
    start=[r for r in records if r[0]=='rpc_start' and r[2]['method']=='GetTaskCost'][0]
    assert start[2]['queue_ms']>=30
    terminal=[r for r in records if r[0]=='stream_terminal'][0]
    assert terminal[1]['run_id']=='run-unit' and terminal[2]['status']=='published'
    assert obs.ACTIVE.labels('StreamTask')._value.get()==0


def test_vlm_timeout_and_usage_are_observed_without_network(monkeypatch):
    import httpx
    from app.gateway.adapters.vlm import VLMAdapter
    from app.context import cost
    records=[]; usages=[]
    monkeypatch.setattr(obs,'emit',lambda event,**fields:records.append((event,fields)))
    monkeypatch.setattr(cost,'record_usage',lambda *a,**kw:usages.append(kw))
    adapter=VLMAdapter()
    adapter.client.close()
    adapter.client=httpx.Client(base_url='https://unit.invalid',transport=httpx.MockTransport(lambda req:httpx.Response(200,json={'usage':{'total_tokens':12}})))
    adapter.analyze_image('not-a-real-image','must-not-be-logged')
    assert usages[0]['total_tokens']==12 and usages[0]['latency_ms']>=0
    adapter.client.close()
    def timeout(req):raise httpx.ReadTimeout('secret-url-or-prompt',request=req)
    adapter.client=httpx.Client(base_url='https://unit.invalid',transport=httpx.MockTransport(timeout))
    with pytest.raises(httpx.ReadTimeout):adapter.analyze_image('x','y')
    adapter.client.close()
    assert records[-1][1]['error_type']=='ReadTimeout'
    assert records[-1][1]['stage']=='model.vlm'
    assert 'secret-url-or-prompt' not in json.dumps(records)
