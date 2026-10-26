import numpy as np
import pytest
from app.eval import bm25_bench, real_eval


def test_like_query_keeps_ids_and_groups_tenant_filter():
    class Collection:
        def query(self, **kwargs):
            assert 'id' in kwargs['output_fields']
            assert kwargs['expr'].startswith('tenant_id == "dev-tenant" and chunk_role == "child" and (')
            assert kwargs['expr'].endswith(')')
            return [{'id': 'chunk-1', 'doc_id': 'source-1', 'text': '血脂异常'}]
    results = bm25_bench._like_search(Collection(), '血脂异常')
    assert results[0]['doc_id'] == 'chunk-1'
    assert bm25_bench._metrics(['chunk-1'], {'chunk-1'})['recall@10'] == 1


def test_main_eval_reports_dense_separately(monkeypatch):
    corpus = [
        {'id': 'a', 'bank': 'guideline', 'name': '血脂指南', 'text': '血脂运动', 'topic': '血脂'},
        {'id': 'b', 'bank': 'guideline', 'name': '血糖指南', 'text': '血糖运动', 'topic': '血糖'},
    ]
    monkeypatch.setattr(real_eval, 'load_health_corpus', lambda: corpus)
    monkeypatch.setenv('SILICONFLOW_API_KEY', 'test-only')
    def embed(texts):
        if len(texts) == 2:
            return [[1, 0], [0, 1]]
        return [[1, 0] if '血脂' in texts[0] else [0, 1]]
    monkeypatch.setattr(real_eval, '_dense_vectors', embed)
    report = real_eval.run_real_eval()
    assert report['aggregated']['dense']['hit@1'] == 1
    assert report['aggregated']['dense']['recall@10'] == 1
    assert all('dense' in row for row in report['per_query'])
