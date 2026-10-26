import pytest
from app.retrieval.chunk_strategies import Chunk
from app.retrieval.chunker import chunks_to_index_rows
from app.retrieval.index_builder import embedding_dim
DEFAULT_DIM = 1024
SELECTED_MODEL = 'BAAI/bge-m3'

def test_embedding_dim_default_and_override(monkeypatch):
    monkeypatch.delenv('EMBEDDING_DIM', raising=False)
    assert embedding_dim() == DEFAULT_DIM
    monkeypatch.setenv('EMBEDDING_DIM', '512')
    assert embedding_dim() == 512

def test_index_rows_carry_model_and_dim(monkeypatch):
    monkeypatch.setenv('EMBEDDING_MODEL', SELECTED_MODEL)
    rows = chunks_to_index_rows([Chunk(text='文本', doc_id='d1', chunk_index=0)], dim=DEFAULT_DIM)
    assert rows[0]['embedding_model'] == SELECTED_MODEL
    assert rows[0]['embedding_dim'] == DEFAULT_DIM

def test_real_collection_dim_matches_config(monkeypatch):
    monkeypatch.delenv('EMBEDDING_DIM', raising=False)
    try:
        from pymilvus import Collection
        from app.retrieval.index_builder import COLLECTION_TEXT, connect
        connect()
        coll = Collection(COLLECTION_TEXT)
        coll.load()
        rows = coll.query(expr='chunk_role == "child"', output_fields=['embedding_dim', 'embedding_model'], limit=5)
    except Exception as e:
        pytest.skip(f'Milvus 不可用，跳过集合维度断言: {e}')
    assert rows, '集合为空'
    dim = embedding_dim()
    assert all((int(r['embedding_dim']) == dim for r in rows)), '集合行维度与 EMBEDDING_DIM 不一致 —— 换模型后需重建索引'
    assert all((r['embedding_model'] for r in rows)), '缺少 embedding_model 溯源信息'
