import pytest
from app.eval import hyde_bench
from app.gateway.adapters.llm import LLMAdapter
from app.retrieval import hyde, channels


def test_counter_can_be_reused_and_restores_adapter(monkeypatch):
    def chat(self, messages, **kwargs):
        return {'usage': {'total_tokens': 7, 'prompt_tokens': 5, 'completion_tokens': 2}}
    monkeypatch.setattr(LLMAdapter, 'chat', chat)
    for _ in range(2):
        with hyde_bench._llm_counter() as counted:
            LLMAdapter.chat(None, [])
            assert counted['tokens'] == 7 and counted['calls'] == 1
        assert LLMAdapter.chat is chat


def test_counter_restores_after_failure(monkeypatch):
    def fail(self, messages, **kwargs):
        raise RuntimeError('model unavailable')
    monkeypatch.setattr(LLMAdapter, 'chat', fail)
    with pytest.raises(RuntimeError):
        with hyde_bench._llm_counter() as counted:
            LLMAdapter.chat(None, [])
    assert LLMAdapter.chat is fail
    assert counted['attempts'] == counted['failed_calls'] == 1
    assert counted['tokens'] == 0


def detail(text='血脂', did='a'):
    return {'candidates': [{'doc_id': did, 'text': text}], 'generated_documents': [], 'effective_documents': 0, 'fallback_to_raw': False, 'generation_ms': 1, 'embedding_ms': 1, 'retrieval_ms': 1, 'latency_ms': 3, 'usage': {'tokens': 0}}


def test_incomplete_query_excluded_from_all_three_arms(monkeypatch):
    monkeypatch.setattr(hyde_bench, 'CASES', [{'query': '失败查询', 'topic': '血脂'}, {'query': '完整查询', 'topic': '血脂'}])
    def run(query, mode, counters):
        if query == '失败查询' and mode == 'hyde':
            raise RuntimeError('embedding failed')
        return detail()
    monkeypatch.setattr(hyde_bench, '_run_mode', run)
    per, excluded, attempts, aggregated = hyde_bench._evaluate({'tokens': 0})
    assert len(per) == len(excluded) == 1
    assert per[0]['query'] == '完整查询'
    assert all(aggregated[mode]['mrr'] == 1 for mode in ('raw','hyde','multi_hyde'))


def test_hyde_generates_embedding_but_search_retains_original_query(monkeypatch):
    seen = {}
    monkeypatch.setattr(hyde, 'build_hyde_query', lambda q: '血脂运动的假设文档')
    def embed(texts):
        seen['embed'] = texts
        return [[1.0, 0.0]]
    def search(query, **kwargs):
        seen['query'] = query
        seen['options'] = kwargs
        return channels.ChannelResult('dense', ['a'], [1.0], ['血脂运动'], [{}])
    monkeypatch.setattr(hyde_bench, '_embed', embed)
    monkeypatch.setattr(channels, 'search_dense', search)
    result = hyde_bench._run_mode('血脂高怎么运动', 'hyde', {'tokens': 0})
    assert seen['embed'] == ['血脂运动的假设文档']
    assert seen['query'] == '血脂高怎么运动'
    assert result['fallback_to_raw'] is False
    assert seen['options']['embedding'] == [1.0, 0.0]


def test_real_hyde_generation_failure_returns_original_query(monkeypatch):
    class Cache:
        enabled = False
    def fail(query):
        raise RuntimeError('LLM unavailable')
    monkeypatch.setattr(hyde, '_generate_uncached', fail)
    assert hyde.build_hyde_query('血脂怎么运动', cache=Cache()) == '血脂怎么运动'
    assert hyde.build_hyde_queries('血脂怎么运动', n=3, cache=Cache()) == ['血脂怎么运动']


def test_multi_vector_is_normalized_average():
    vector = hyde_bench._avg_vector([[1, 0], [0, 1]])
    assert vector == pytest.approx([2 ** -0.5, 2 ** -0.5])
