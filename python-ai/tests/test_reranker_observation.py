import json
from types import SimpleNamespace

import httpx
import pytest

from app.gateway.adapters import reranker
from app.context import cost
import app.cache


@pytest.fixture
def observed(monkeypatch):
    events=[];usage=[]
    monkeypatch.setenv('JINA_API_KEY','must-not-log-api-key')
    monkeypatch.setattr(reranker,'emit',lambda event,**fields:events.append({'event':event,**fields}))
    monkeypatch.setattr(cost,'record_usage',lambda *a,**kw:usage.append(kw))
    adapter=reranker.RerankerAdapter(provider='jina');adapter.client.close()
    yield adapter,events,usage
    adapter.client.close()


@pytest.mark.parametrize('status',[200,400,401,403,422,429,500,503])
def test_status_and_numeric_retry_after_without_secrets_or_retries(observed,status):
    adapter,events,usage=observed;requests=[]
    def respond(request):
        requests.append(request)
        return httpx.Response(status,headers={'Retry-After':'12','X-Request-Id':'private-id'},json={'results':[{'index':0}],'error':'private-response-body'})
    adapter.client=httpx.Client(base_url=adapter.base_url,transport=httpx.MockTransport(respond))
    if status>=400:
        with pytest.raises(httpx.HTTPStatusError):adapter._rerank_uncached('private-query',['private-document'],1)
        assert not usage
    else:assert adapter._rerank_uncached('private-query',['private-document'],1)==[{'index':0}]
    record=[e for e in events if e['event']=='rerank_http'][0]
    assert len(requests)==1 and record['http_status']==status and record['attempt']==1
    assert record['outcome']==('error' if status>=400 else 'ok') and record['retry_after_seconds']==12
    assert record['duration_ms']>=0 and record['provider']=='jina'
    text=json.dumps(events)
    for secret in ['must-not-log-api-key','private-query','private-document','private-response-body','private-id','Authorization']:
        assert secret not in text


@pytest.mark.parametrize('exception',[httpx.ReadTimeout,httpx.ConnectError])
def test_network_error_has_no_fabricated_status_and_is_not_retried(observed,exception):
    adapter,events,usage=observed;attempts=[]
    def fail(request):attempts.append(1);raise exception('private-exception-message',request=request)
    adapter.client=httpx.Client(base_url=adapter.base_url,transport=httpx.MockTransport(fail))
    with pytest.raises(exception):adapter._rerank_uncached('private-query',['private-document'],1)
    assert len(attempts)==1 and not usage
    assert events[0]['http_status'] is None and events[0]['error_type']==exception.__name__
    assert 'private' not in json.dumps(events)


def test_invalid_json_is_not_misreported_as_http_failure(observed):
    adapter,events,usage=observed
    adapter.client=httpx.Client(base_url=adapter.base_url,transport=httpx.MockTransport(lambda r:httpx.Response(200,text='private-invalid-json')))
    with pytest.raises(ValueError):adapter._rerank_uncached('q',['d'],1)
    assert events[0]['http_status']==200 and events[0]['outcome']=='error' and not usage
    assert 'private-invalid-json' not in json.dumps(events)


@pytest.mark.parametrize('raw', ['private-header','NaN','Infinity','-1','1000000','Thu, 01 Jan 2030 00:00:00 GMT'])
def test_untrusted_retry_header_is_not_logged(raw):assert reranker.retry_after_seconds(raw) is None


@pytest.mark.parametrize('enabled,hit,expected',[(True,[{'index':0}],'hit'),(True,None,'miss'),(False,None,'disabled')])
def test_cache_hit_and_miss_visible_without_logging_keys_or_contents(observed,monkeypatch,enabled,hit,expected):
    adapter,events,usage=observed;calls=[];sets=[]
    cache=SimpleNamespace(enabled=enabled,get=lambda key:hit,set=lambda *args,**kwargs:sets.append(args))
    monkeypatch.setattr(app.cache,'get_cache',lambda:cache)
    monkeypatch.setattr(adapter,'_rerank_uncached',lambda *args:calls.append(1) or [{'index':0}])
    assert adapter.rerank('private-query',['private-document'],1)==[{'index':0}]
    assert events[0]['cache_status']==expected and events[0]['document_count']==1
    assert len(calls)==(0 if expected=='hit' else 1)
    assert 'private' not in json.dumps(events)


@pytest.mark.parametrize('configured,current,bypass',[('diagnostic-run','diagnostic-run',True),('diagnostic-run','normal-run',False),('','',False)])
def test_cache_bypass_is_scoped_and_does_not_modify_shared_cache(observed,monkeypatch,configured,current,bypass):
    adapter,events,usage=observed;gets=[];sets=[];http=[]
    monkeypatch.setenv('LHA_RERANK_DIAGNOSTIC_RUN_ID',configured)
    cache=SimpleNamespace(enabled=True,get=lambda key:gets.append(key) or [{'index':0}],set=lambda *a,**kw:sets.append(a))
    monkeypatch.setattr(app.cache,'get_cache',lambda:cache)
    monkeypatch.setattr(adapter,'_rerank_uncached',lambda *args:http.append(1) or [{'index':1}])
    token=reranker.CORRELATION.set({'run_id':current})
    try:result=adapter.rerank('private-query',['private-document'],1)
    finally:reranker.CORRELATION.reset(token)
    assert events[0]['cache_status']==('bypass' if bypass else 'hit')
    assert len(http)==int(bypass) and len(gets)==int(not bypass) and not sets
    assert result==[{'index':1 if bypass else 0}]
