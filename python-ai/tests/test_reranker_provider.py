import httpx
import pytest

from app.gateway.adapters.reranker import RerankerAdapter


def test_jina_uses_separate_credentials_and_standard_rerank_payload(monkeypatch):
    monkeypatch.setenv('RERANKER_PROVIDER', 'jina')
    monkeypatch.setenv('JINA_API_KEY', 'test-jina-key')
    monkeypatch.setenv('SILICONFLOW_API_KEY', 'different-key')
    monkeypatch.delenv('RERANKER_MODEL', raising=False)
    monkeypatch.delenv('RERANKER_BASE_URL', raising=False)
    adapter = RerankerAdapter()

    def handle(request):
        import json
        assert str(request.url) == 'https://api.jina.ai/v1/rerank'
        assert request.headers['Authorization'] == 'Bearer test-jina-key'
        assert json.loads(request.content) == {'model': 'jina-reranker-v3', 'query': '血脂', 'documents': ['运动建议'], 'top_n': 1}
        return httpx.Response(200, json={'results': [{'index': 0, 'relevance_score': .9}]})

    adapter.client.close()
    with httpx.Client(base_url=adapter.base_url, transport=httpx.MockTransport(handle)) as client:
        adapter.client = client
        assert adapter._rerank_uncached('血脂', ['运动建议'], top_k=1) == [{'index': 0, 'relevance_score': .9}]


def test_missing_jina_key_does_not_use_siliconflow_key(monkeypatch):
    monkeypatch.setenv('RERANKER_PROVIDER', 'jina')
    monkeypatch.delenv('JINA_API_KEY', raising=False)
    monkeypatch.setenv('SILICONFLOW_API_KEY', 'different-key')
    adapter = RerankerAdapter()
    try:
        with pytest.raises(RuntimeError, match='JINA_API_KEY'):
            adapter._rerank_uncached('query', ['text'])
    finally:
        adapter.client.close()


def test_siliconflow_remains_default(monkeypatch):
    for key in ('RERANKER_PROVIDER', 'RERANKER_MODEL', 'RERANKER_BASE_URL'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('SILICONFLOW_API_KEY', 'test-key')
    adapter = RerankerAdapter()
    try:
        assert adapter.model == 'BAAI/bge-reranker-v2-m3'
        assert adapter.base_url == 'https://api.siliconflow.cn/v1'
        assert adapter.api_key == 'test-key'
    finally:
        adapter.client.close()


def test_qwen_selection_does_not_inherit_active_jina_config(monkeypatch):
    monkeypatch.setenv('RERANKER_PROVIDER', 'jina')
    monkeypatch.setenv('RERANKER_MODEL', 'jina-reranker-v3')
    monkeypatch.setenv('RERANKER_BASE_URL', 'https://api.jina.ai/v1')
    monkeypatch.setenv('JINA_API_KEY', 'test-jina-key')
    monkeypatch.setenv('QWEN_RERANK_API_KEY', 'test-qwen-key')
    for key in ('QWEN_RERANK_MODEL', 'QWEN_RERANK_BASE_URL', 'QWEN_RERANK_PATH'):
        monkeypatch.delenv(key, raising=False)
    adapter = RerankerAdapter(provider='qwen')

    def handle(request):
        import json
        assert str(request.url) == 'https://maas.qianwenaiapi.com/compatible-api/v1/reranks'
        assert request.headers['Authorization'] == 'Bearer test-qwen-key'
        assert json.loads(request.content) == {'model': 'qwen3-rerank', 'query': '血脂', 'documents': ['运动建议'], 'top_n': 1}
        return httpx.Response(200, json={'results': [{'index': 0, 'relevance_score': .8}]})

    adapter.client.close()
    with httpx.Client(base_url=adapter.base_url, transport=httpx.MockTransport(handle)) as client:
        adapter.client = client
        assert adapter._rerank_uncached('血脂', ['运动建议'], 1)[0]['index'] == 0


def test_missing_qwen_key_does_not_use_other_credentials(monkeypatch):
    monkeypatch.delenv('QWEN_RERANK_API_KEY', raising=False)
    monkeypatch.setenv('SILICONFLOW_API_KEY', 'different-key')
    monkeypatch.setenv('JINA_API_KEY', 'different-key')
    adapter = RerankerAdapter(provider='qwen')
    try:
        with pytest.raises(RuntimeError, match='QWEN_RERANK_API_KEY'):
            adapter._rerank_uncached('query', ['text'])
    finally:
        adapter.client.close()


def test_explicit_jina_selection_does_not_inherit_qwen_model(monkeypatch):
    monkeypatch.setenv('RERANKER_MODEL', 'qwen3-rerank')
    monkeypatch.setenv('RERANKER_BASE_URL', 'https://api.siliconflow.cn/v1')
    for key in ('JINA_RERANK_MODEL', 'JINA_RERANK_BASE_URL'):
        monkeypatch.delenv(key, raising=False)
    adapter = RerankerAdapter(provider='jina')
    try:
        assert adapter.model == 'jina-reranker-v3'
        assert adapter.base_url == 'https://api.jina.ai/v1'
    finally:
        adapter.client.close()
