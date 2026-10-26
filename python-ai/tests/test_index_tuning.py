"""Verify IVF sweep uses a fixed corpus/truth and cleans only its temporary collection."""
from types import SimpleNamespace
import sys

import pytest

from app.eval import index_tuning as tuning


def test_ivf_sweep_fixed_index_and_cleanup(monkeypatch):
    calls = []
    collections = []
    truth = [{1, 2}]

    class Collection:
        def __init__(self, name, schema):
            self.name = name
            collections.append(self)

        def insert(self, rows):
            calls.append(('insert', len(rows)))

        def flush(self, **kwargs):
            pass

        def create_index(self, field, params, **kwargs):
            calls.append(('index', params))

        def load(self, **kwargs):
            pass

        def release(self, **kwargs):
            pass

        def drop_index(self, **kwargs):
            calls.append(('drop_index',))

    def measure(coll, queries, params, reference=None):
        calls.append(('search', params, reference))
        return {'recall@10': 1.0, 'p95_latency_ms': 2.0}, truth

    milvus = SimpleNamespace(
        Collection=Collection, CollectionSchema=lambda fields: fields,
        FieldSchema=lambda *args, **kwargs: None,
        DataType=SimpleNamespace(INT64=1, FLOAT_VECTOR=2),
        connections=SimpleNamespace(connect=lambda **kw: None,
                                    disconnect=lambda alias: calls.append(('disconnect',))),
        utility=SimpleNamespace(wait_for_index_building_complete=lambda *a, **kw: None,
                                drop_collection=lambda name, **kw: calls.append(('drop', name))),
    )
    monkeypatch.setitem(sys.modules, 'pymilvus', milvus)
    monkeypatch.setattr(tuning, '_load_real_vectors', lambda: [[1.0, 0.0]])
    monkeypatch.setattr(tuning, '_load_real_queries', lambda *args, **kwargs: [[1.0, 0.0]])
    monkeypatch.setattr(tuning, '_derive_corpus', lambda seeds: seeds * 128)
    monkeypatch.setattr(tuning, '_measure_search', measure)
    report = tuning._run_ivf_sq8_sweep([4, 8, 16, 32, 64], 128)
    assert [r['nprobe'] for r in report['results']] == [4, 8, 16, 32, 64]
    assert [c[1]['index_type'] for c in calls if c[0] == 'index'] == ['FLAT', 'IVF_SQ8']
    searches = [c for c in calls if c[0] == 'search']
    assert searches[0][2] is None
    assert all(c[2] is truth for c in searches[1:])
    assert len(collections) == 1
    assert ('drop', collections[0].name) in calls
    assert collections[0].name.startswith('tune_ivf_sq8_')
    assert ('insert', 128) in calls

    def fail_search(*args, **kwargs):
        raise RuntimeError('search failed')

    monkeypatch.setattr(tuning, '_measure_search', fail_search)
    with pytest.raises(RuntimeError, match='search failed'):
        tuning._run_ivf_sq8_sweep([4], 128)
    assert ('drop', collections[-1].name) in calls
    assert calls[-1] == ('disconnect',)


def test_measure_recall_and_nearest_rank_p95(monkeypatch):
    class Collection:
        def search(self, *args, **kwargs):
            return [[SimpleNamespace(id=1), SimpleNamespace(id=3)]]

    # Twenty queries: 19 take 1 ms, one takes 100 ms; nearest-rank P95 is 1 ms.
    ticks = iter(t for i in range(20) for t in (i, i + (0.1 if i == 19 else 0.001)))
    monkeypatch.setattr(tuning.time, 'perf_counter', lambda: next(ticks))
    metrics, ids = tuning._measure_search(Collection(), [[1.0]] * 20, {}, [{1, 2}] * 20)
    assert metrics == {'recall@10': 0.5, 'p95_latency_ms': 1.0}
    assert ids == [{1, 3}] * 20


def test_ivf_dry_run_no_services_and_invalid_nprobe(monkeypatch, capsys):
    monkeypatch.setattr(tuning, '_milvus_ready', lambda: pytest.fail('dry-run contacted Milvus'))
    monkeypatch.setattr(sys, 'argv', ['index_tuning', '--index-type', 'IVF_SQ8', '--dry-run'])
    tuning.main()
    assert 'nprobe=[4, 8, 16, 32, 64]' in capsys.readouterr().out
    monkeypatch.setattr(sys, 'argv', ['index_tuning', '--index-type', 'IVF_SQ8', '--nprobe', '129'])
    with pytest.raises(SystemExit) as exc:
        tuning.main()
    assert exc.value.code == 2


def test_expand_to_100_distinct_queries_preserves_original_30():
    names = [f'指标{i}' for i in range(30)]
    queries = tuning._build_query_texts(names + names, 100)
    assert len(queries) == len(set(queries)) == 100
    assert queries[:30] == [f'{name} 参考区间 运动干预' for name in names]
    assert queries == tuning._build_query_texts(names, 100)
    with pytest.raises(ValueError, match='少于要求'):
        tuning._build_query_texts(names, 151)
