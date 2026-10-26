import pytest
from app.retrieval.chunk_strategies import TEXT_STRATEGIES, Chunk, chunk_fixed_length, chunk_fixed_symbol, chunk_semantic_by_similarity, chunk_sliding_window, expand_to_parent, resolve_text_strategy
from app.retrieval.chunker import build_chunks, build_index_chunks, chunks_to_index_rows

def _pad(s: str, n: int) -> str:
    return (s * (n // len(s) + 1))[:n]
_SENTENCES = [_pad('血脂异常人群应进行规律有氧运动并控制体重', 60) + '。', _pad('同时应减少饱和脂肪摄入', 20) + '。', _pad('他汀类药物需遵医嘱服用', 20) + '。', _pad('服药期间应复查肝功能', 20) + '。']

def _text() -> str:
    return ''.join(_SENTENCES)

def _stub_embed():

    def _fn(texts):
        return [[1.0, 0.0] if i == 0 else [0.0, 1.0] for i, _ in enumerate(texts)]
    return _fn

def _identical_embed(texts):
    return [[1.0, 0.0] for _ in texts]

def test_semantic_split_breaks_at_low_similarity():
    chunks = chunk_semantic_by_similarity(_text(), embed_fn=_stub_embed(), chunk_size=100, overlap=0, min_fill=0.1)
    assert len(chunks) == 2
    assert chunks[0] == _SENTENCES[0]
    assert chunks[1] == ''.join(_SENTENCES[1:])

def test_semantic_split_differs_from_window_split():
    text = _text()
    semantic = chunk_semantic_by_similarity(text, embed_fn=_stub_embed(), chunk_size=100, overlap=0, min_fill=0.1)
    window = chunk_sliding_window(text, chunk_size=100, overlap=0)
    assert semantic != window
    assert semantic[0] == _SENTENCES[0]
    assert window[0] == ''.join(_SENTENCES[:2])

def test_semantic_split_falls_back_on_embed_failure():

    def boom(_texts):
        raise RuntimeError('embedding api down')
    text = _text()
    got = chunk_semantic_by_similarity(text, embed_fn=boom, chunk_size=100, overlap=0)
    assert got == chunk_sliding_window(text, chunk_size=100, overlap=0)
    assert ''.join(got).replace(' ', '')

def test_semantic_split_falls_back_on_vector_count_mismatch():
    text = _text()
    got = chunk_semantic_by_similarity(text, embed_fn=lambda texts: [[1.0, 0.0]], chunk_size=100, overlap=0)
    assert got == chunk_sliding_window(text, chunk_size=100, overlap=0)

def test_semantic_split_never_exceeds_chunk_size():
    text = '。'.join(['很长的句子' * 12] * 6) + '。'
    chunks = chunk_semantic_by_similarity(text, embed_fn=_identical_embed, chunk_size=120, overlap=0, min_fill=0.1)
    assert chunks
    assert all((len(c) <= 120 for c in chunks))

def test_semantic_split_without_boundaries_merges():
    text = _text()
    chunks = chunk_semantic_by_similarity(text, embed_fn=_identical_embed, chunk_size=200, overlap=0)
    assert chunks == [text]

def test_fixed_length_cuts_hard_at_size():
    text = '血脂异常人群应进行规律有氧运动' * 10
    chunks = chunk_fixed_length(text, chunk_size=30)
    assert len(chunks) == 5
    assert all((len(c) == 30 for c in chunks[:-1]))
    assert all((len(c) <= 30 for c in chunks))
    assert ''.join(chunks) == text

def test_fixed_length_overlap_covers_boundary():
    text = '0123456789' * 10
    chunks = chunk_fixed_length(text, chunk_size=30, overlap=10)
    assert len(chunks) > 1
    for i in range(len(chunks) - 1):
        assert chunks[i][-10:] == chunks[i + 1][:10]

def test_fixed_symbol_keeps_fields_intact():
    row1 = '体检指标 低密度脂蛋白胆固醇 | 编码 LDL_C | 参考区间 0-3.4。'
    row2 = '体检指标 空腹血糖 | 编码 FPG | 参考区间 3.9-6.1。'
    text = row1 + row2
    chunks = chunk_fixed_symbol(text, chunk_size=40)
    assert chunks == [row1, row2]
    assert ''.join(chunks) == text

def test_resolve_text_strategy_priority_and_fallback(monkeypatch):
    fn, label = resolve_text_strategy('auto', embed_fn=None)
    assert (fn, label) == (chunk_sliding_window, 'semantic_window')
    fn, label = resolve_text_strategy('auto', embed_fn=_identical_embed)
    assert (fn, label) == (chunk_semantic_by_similarity, 'semantic_split')
    monkeypatch.setenv('CHUNK_STRATEGY', 'fixed_length')
    fn, label = resolve_text_strategy('auto', embed_fn=_identical_embed)
    assert (fn, label) == (TEXT_STRATEGIES['fixed_length'], 'fixed_length')
    fn, label = resolve_text_strategy('semantic_window', embed_fn=_identical_embed)
    assert label == 'semantic_window'
    monkeypatch.delenv('CHUNK_STRATEGY')
    fn, label = resolve_text_strategy('semantic_split', embed_fn=None)
    assert (fn, label) == (chunk_sliding_window, 'semantic_window')
    with pytest.raises(ValueError):
        resolve_text_strategy('no_such_strategy')

def test_build_chunks_text_strategy_selectable():
    doc = {'id': 'd1', 'source_id': 's1', 'source_level': 1, 'knowledge_version': 'kv_test', 'content': {'raw_text': '0123456789' * 20}}
    for name in ('fixed_length', 'fixed_symbol', 'semantic_window'):
        chunks = build_chunks([doc], strategy=name, chunk_size=30, overlap=0)
        assert chunks and all((c.strategy == name for c in chunks))

def _doc(doc_id: str, text_len: int, kind: str='guideline') -> dict:
    return {'id': doc_id, 'source_id': f'src_{doc_id}', 'source_level': 1, 'knowledge_version': 'kv_test', 'content': {'kind': kind, 'title': 'T', 'content': '甲' * text_len}}

def test_short_doc_is_single_child_without_parent():
    chunks, parents = build_index_chunks([_doc('d1', 100)], embed_fn=lambda t: [])
    assert parents == {}
    assert len(chunks) == 1
    c = chunks[0]
    assert c.role == 'child' and c.parent_key == ''
    assert c.index_key == 'd1:c0'

def test_long_doc_has_one_parent_and_children():
    long_text = '。'.join(['这是一段较长的指南正文用于触发父子块切分'] * 80)
    doc = {'id': 'd2', 'source_id': 's2', 'source_level': 2, 'knowledge_version': 'kv_test', 'content': {'kind': 'guideline', 'title': 'T', 'content': long_text}}
    chunks, parents = build_index_chunks([doc], embed_fn=_identical_embed)
    ps = [c for c in chunks if c.role == 'parent']
    cs = [c for c in chunks if c.role == 'child']
    assert len(ps) == 1 and len(cs) >= 2
    assert ps[0].index_key == 's2:p0'
    assert all((c.parent_key == 's2:p0' for c in cs))
    assert parents['s2:p0'] == ps[0].text
    assert len({c.index_key for c in chunks}) == len(chunks)

def test_use_parent_child_disabled_degrades_to_single_layer():
    long_text = '。'.join(['这是一段较长的指南正文用于触发父子块切分'] * 80)
    doc = {'id': 'd3', 'source_id': 's3', 'source_level': 1, 'knowledge_version': 'kv_test', 'content': {'kind': 'guideline', 'title': 'T', 'content': long_text}}
    chunks, parents = build_index_chunks([doc], embed_fn=_identical_embed, use_parent_child=False)
    assert parents == {}
    assert all((c.role == 'child' for c in chunks))

def test_index_rows_carry_role_and_parent_key():
    rows = chunks_to_index_rows([Chunk(text='父', doc_id='d4', role='parent', parent_key='d4:p0', strategy='parent', chunk_index=0), Chunk(text='子', doc_id='d4', role='child', parent_key='d4:p0', strategy='semantic_split', chunk_index=0)], dim=4)
    by_id = {r['id']: r for r in rows}
    assert by_id['d4:p0']['chunk_role'] == 'parent'
    assert by_id['d4:c0']['chunk_role'] == 'child'
    assert by_id['d4:c0']['parent_key'] == 'd4:p0'
    assert by_id['d4:p0']['parent_key'] == 'd4:p0'

def test_expand_to_parent_uses_parent_key_field():
    ranked = [{'id': 'd5:c3', 'snippet': '子块文本', 'parent_key': 'd5:p0'}]
    out = expand_to_parent(ranked, {'d5:p0': '父块完整上下文'})
    assert out[0]['snippet'] == '父块完整上下文'
    assert out[0]['child_snippet'] == '子块文本'
    assert out[0]['parent_expanded'] is True

def test_expand_to_parent_derives_key_when_field_missing():
    ranked = [{'id': 'd6:c2', 'snippet': '子块'}]
    out = expand_to_parent(ranked, {'d6:p0': '父块'})
    assert out[0]['snippet'] == '父块'

def test_expand_to_parent_noop_when_parent_missing():
    ranked = [{'id': 'd7:c1', 'snippet': '子块', 'parent_key': 'd7:p0'}]
    out = expand_to_parent(ranked, {})
    assert out[0]['snippet'] == '子块'
    assert 'parent_expanded' not in out[0]
    assert ranked[0].get('parent_expanded') is None
