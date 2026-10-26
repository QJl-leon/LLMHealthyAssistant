import pytest
from app.gateway.adapters.clip import CLIPAdapter, clip_dim
from app.retrieval.query_planner import QueryPlanner
CALIBRATED_DIM = 4096

def test_clip_dim_default_and_override(monkeypatch):
    monkeypatch.delenv('CLIP_DIM', raising=False)
    assert clip_dim() == CALIBRATED_DIM
    monkeypatch.setenv('CLIP_DIM', '512')
    assert clip_dim() == 512

def test_clip_adapter_uses_vl_model_by_default(monkeypatch):
    monkeypatch.delenv('CLIP_MODEL', raising=False)
    assert CLIPAdapter().model == 'Qwen/Qwen3-VL-Embedding-8B'

def test_clip_adapter_raises_without_api_key(monkeypatch):
    monkeypatch.setenv('SILICONFLOW_API_KEY', '')
    with pytest.raises(RuntimeError, match='SILICONFLOW_API_KEY'):
        CLIPAdapter().embed_image(b'\x89PNG\r\n\x1a\nfake')

def test_clip_adapter_has_no_local_onnx_path():
    assert not hasattr(CLIPAdapter(), '_embed_local')

def _channels_of(query: str) -> set[str]:
    plan = QueryPlanner().plan([], query=query)
    return {c for p in plan.plans for c in p.channels}

def test_planner_adds_image_channel_for_image_intent():
    assert 'image' in _channels_of('找一份和我这份版式相同的历史体检报告')

def test_planner_omits_image_channel_for_text_query():
    assert 'image' not in _channels_of('血脂偏高平时应该注意什么')

def _image_collection_dim() -> int:
    try:
        from pymilvus import Collection
        from pymilvus import utility
        from app.retrieval.index_builder import COLLECTION_IMAGE, connect
        connect()
        if not utility.has_collection(COLLECTION_IMAGE):
            pytest.skip('evidence_image 集合不存在（未构建图像索引）')
        coll = Collection(COLLECTION_IMAGE)
        for f in coll.schema.fields:
            if f.name == 'embedding':
                return int(f.params.get('dim', 0))
    except Exception as e:
        pytest.skip(f'Milvus 不可用，跳过图像集合断言: {e}')
    pytest.skip('未找到 embedding 字段')

def test_real_image_collection_dim_matches_clip_dim(monkeypatch):
    monkeypatch.delenv('CLIP_DIM', raising=False)
    dim = _image_collection_dim()
    assert dim == clip_dim(), f'evidence_image 维度（{dim}）与 clip_dim()（{clip_dim()}）不一致，需重建图像索引'
