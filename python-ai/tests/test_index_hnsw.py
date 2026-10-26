import pytest
from app.retrieval.index_builder import COLLECTION_TEXT, hnsw_index_params, search_ef
CALIBRATED_M = 32
CALIBRATED_EF_CONSTRUCTION = 200
CALIBRATED_SEARCH_EF = 128

def test_hnsw_default_params_are_calibrated(monkeypatch):
    monkeypatch.delenv('INDEX_M', raising=False)
    monkeypatch.delenv('INDEX_EF_CONSTRUCTION', raising=False)
    monkeypatch.delenv('INDEX_SEARCH_EF', raising=False)
    assert hnsw_index_params() == {'M': CALIBRATED_M, 'efConstruction': CALIBRATED_EF_CONSTRUCTION}
    assert search_ef() == CALIBRATED_SEARCH_EF

def test_hnsw_params_env_override(monkeypatch):
    monkeypatch.setenv('INDEX_M', '16')
    monkeypatch.setenv('INDEX_EF_CONSTRUCTION', '100')
    monkeypatch.setenv('INDEX_SEARCH_EF', '64')
    assert hnsw_index_params() == {'M': 16, 'efConstruction': 100}
    assert search_ef() == 64

def test_search_ef_not_below_calibrated_floor(monkeypatch):
    monkeypatch.delenv('INDEX_SEARCH_EF', raising=False)
    assert search_ef() >= CALIBRATED_SEARCH_EF

def _dense_index_info() -> dict:
    try:
        from pymilvus import Collection
        from app.retrieval.index_builder import connect
        connect()
        coll = Collection(COLLECTION_TEXT)
        coll.load()
        for idx in coll.indexes:
            if idx.field_name == 'embedding':
                return dict(idx.params or {})
    except Exception as e:
        pytest.skip(f'Milvus 不可用或集合缺失，跳过真实索引断言: {e}')
    pytest.skip('未找到 embedding 索引')

def test_real_dense_index_is_hnsw_with_calibrated_params():
    info = _dense_index_info()
    assert str(info.get('index_type', '')).upper() == 'HNSW', f"Dense 索引必须是 HNSW（实际: {info.get('index_type')}）"
    assert str(info.get('metric_type', '')).upper() == 'COSINE'
    params = info.get('params') or {}
    assert int(params.get('M', 0)) == CALIBRATED_M, f"M 与 sweep 定参不一致（实际 {params.get('M')}，期望 {CALIBRATED_M}）"
    assert int(params.get('efConstruction', 0)) == CALIBRATED_EF_CONSTRUCTION
