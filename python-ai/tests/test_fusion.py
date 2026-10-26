import pytest
from app.retrieval.channels import ChannelResult, _channel_weights, fuse_and_rerank, should_rerank
from app.retrieval.rrf import rrf_fuse

def _cr(channel: str, ids: list[str], snippets: list[str] | None=None) -> ChannelResult:
    return ChannelResult(channel=channel, doc_ids=list(ids), scores=[1.0] * len(ids), snippets=snippets or [f'文本-{i}' for i in ids], metadata=[{} for _ in ids])

def test_rrf_equal_weight_matches_plain_rrf():
    results = [_cr('dense', ['a', 'b']), _cr('bm25', ['b', 'c'])]
    plain = rrf_fuse(results, k=60)
    weighted = rrf_fuse(results, k=60, weights={'dense': 1.0, 'bm25': 1.0})
    assert [x['doc_id'] for x in plain] == [x['doc_id'] for x in weighted]
    assert plain[0]['doc_id'] == 'b'

def test_rrf_channel_weight_lifts_its_top_item():
    results = [_cr('dense', ['x']), _cr('bm25', ['y'])]
    equal = rrf_fuse(results, k=60)
    boost = rrf_fuse(results, k=60, weights={'bm25': 2.0})
    assert equal[0]['doc_id'] == 'x'
    assert boost[0]['doc_id'] == 'y'
    assert boost[0]['rrf_score'] == pytest.approx(2.0 / 61, abs=1e-06)

def test_rrf_unlisted_channel_defaults_to_one():
    results = [_cr('dense', ['x']), _cr('image', ['z'])]
    out = rrf_fuse(results, k=60, weights={'dense': 5.0})
    assert out[0]['doc_id'] == 'x'
    assert out[1]['rrf_score'] == pytest.approx(1.0 / 61, abs=1e-06)

def test_rrf_fuse_empty_results():
    assert rrf_fuse([], k=60) == []

def _items(snippets: list[str]) -> list[dict]:
    return [{'doc_id': f'd{i}', 'snippet': s} for i, s in enumerate(snippets)]

def test_should_rerank_switch_off():
    do, why = should_rerank('血脂怎么运动', _items(['a', 'b']), enabled=False)
    assert do is False and '开关' in why

def test_should_rerank_needs_at_least_two_candidates():
    do, why = should_rerank('血脂怎么运动', _items(['a']), enabled=True)
    assert do is False and '候选不足' in why

def test_should_rerank_skips_short_exact_query_hit_at_top():
    q = '低密度脂蛋白胆固醇'
    do, why = should_rerank(q, _items([f'{q} 参考区间 0-3.4', '其他文本']), enabled=True)
    assert do is False and '粗排已准' in why

def test_should_rerank_runs_for_semantic_query():
    do, why = should_rerank('我血脂有点高平时应该注意些什么呢', _items(['a', 'b']), enabled=True)
    assert do is True and '语义' in why

def test_should_rerank_runs_when_short_query_not_hit():
    do, _ = should_rerank('骨密度', _items(['他汀类药物注意事项', '骨密度 -1.2 SD']), enabled=True)
    assert do is True

def test_channel_weights_env_parsing(monkeypatch):
    monkeypatch.delenv('RRF_CHANNEL_WEIGHTS', raising=False)
    assert _channel_weights() == {}
    monkeypatch.setenv('RRF_CHANNEL_WEIGHTS', '{"dense": 1.5, "bm25": 0.8}')
    assert _channel_weights() == {'dense': 1.5, 'bm25': 0.8}
    monkeypatch.setenv('RRF_CHANNEL_WEIGHTS', '不是 JSON')
    assert _channel_weights() == {}
    monkeypatch.setenv('RRF_CHANNEL_WEIGHTS', '[1,2]')
    assert _channel_weights() == {}

class _ExplodingReranker:

    def rerank(self, *a, **kw):
        raise AssertionError('精排关闭时不应调用 reranker')

def test_fuse_skips_reranker_when_disabled():
    results = [_cr('dense', ['a', 'b'], ['文本A', '文本B'])]
    out = fuse_and_rerank(results, '随便什么查询', reranker=_ExplodingReranker(), top_k=2, expand_parents=False, rerank_enabled=False)
    assert [x['doc_id'] for x in out] == ['a', 'b']

def test_fuse_skips_reranker_for_short_exact_query():
    q = '空腹血糖'
    results = [_cr('dense', ['a', 'b'], [f'{q} 5.4 mmol/L', '别的'])]
    out = fuse_and_rerank(results, q, reranker=_ExplodingReranker(), top_k=2, expand_parents=False, rerank_enabled=True)
    assert out[0]['doc_id'] == 'a'

def test_fuse_empty_results_returns_empty():
    assert fuse_and_rerank([], 'q', expand_parents=False) == []
