import pytest
from app.eval import rerank_bench
from app.retrieval import channels


def result(channel):
    return channels.ChannelResult(channel, [channel], [1.0], ['血脂运动'], [{}])


def test_rrf_named_mode_runs_both_channels_without_early_rerank(monkeypatch):
    calls = []
    monkeypatch.setattr(channels, 'search_bm25', lambda *a, **k: calls.append('bm25') or result('bm25'))
    monkeypatch.setattr(channels, 'search_dense', lambda *a, **k: calls.append('dense') or result('dense'))
    def fuse(results, query, **kwargs):
        assert kwargs['rerank_enabled'] is False
        assert kwargs['expand_parents'] is False
        assert kwargs['channel_weights'] == {}
        assert kwargs['rrf_k'] == 60
        return [{'doc_id': 'fused', 'snippet': '血脂运动'}]
    monkeypatch.setattr(channels, 'fuse_and_rerank', fuse)
    assert rerank_bench._retrieve_candidates('血脂', mode='rrf_fusion')[0]['doc_id'] == 'fused'
    assert calls == ['bm25', 'dense']


def test_bm25_control_does_not_call_dense(monkeypatch):
    monkeypatch.setattr(channels, 'search_bm25', lambda *a, **k: result('bm25'))
    def forbidden(*a, **k):
        raise AssertionError('BM25 control must not call Dense')
    monkeypatch.setattr(channels, 'search_dense', forbidden)
    assert rerank_bench._retrieve_candidates('血脂', mode='bm25_only')[0]['doc_id'] == 'bm25'


def test_mrr_uses_same_top10_horizon_for_both_arms():
    ranked = [str(i) for i in range(11)]
    assert rerank_bench._metrics(ranked, {'10'})['mrr'] == 0
    assert rerank_bench._metrics(ranked, {'9'})['mrr'] == 0.1


def test_rerank_duplicate_indices_are_rejected(monkeypatch):
    from app.gateway.adapters.reranker import RerankerAdapter
    monkeypatch.setattr(RerankerAdapter, 'rerank', lambda *a, **k: [{'index': 0}, {'index': 0}])
    with pytest.raises(RuntimeError, match='重复'):
        rerank_bench._rough_rerank('血脂', [{'doc_id': 'a', 'text': 'a'}, {'doc_id': 'b', 'text': 'b'}])
