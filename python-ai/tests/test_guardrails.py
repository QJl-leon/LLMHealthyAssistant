import pytest
from app.evidence.validator import refuse_if_no_evidence, validate_advice_has_evidence, validate_claims_against_evidence, validate_existence, validate_metric_name
from app.memory.curator import MemoryCurator
from app.retrieval.chunk_strategies import chunk_sliding_window, naturalize_metric_row
from app.retrieval.chunker import build_chunks

def test_fake_evidence_rejected():
    claims = [{'claim_id': 'c1', 'type': 'fact', 'text': '低密度脂蛋白 3.4mmol/L 偏高', 'evidence_ids': ['fake_ev_001']}]
    evidence = [{'evidence_id': 'real_ev_001', 'quote': '低密度脂蛋白 3.4mmol/L'}]
    errors = validate_claims_against_evidence(claims, evidence)
    assert len(errors) == 1
    assert errors[0]['error_code'] == 'CITATION_MISMATCH'

def test_valid_evidence_passes():
    claims = [{'claim_id': 'c1', 'type': 'fact', 'text': '低密度脂蛋白 3.4mmol/L 偏高', 'evidence_ids': ['real_ev_001']}]
    evidence = [{'evidence_id': 'real_ev_001', 'quote': '低密度脂蛋白 3.4mmol/L'}]
    assert validate_claims_against_evidence(claims, evidence) == []

def test_refuse_when_no_evidence():
    refuse, reason = refuse_if_no_evidence([{'claim_id': 'c1', 'type': 'fact'}], [])
    assert refuse
    assert reason

def test_refuse_when_fact_without_evidence():
    claims = [{'claim_id': 'c1', 'type': 'fact', 'text': '该用户血脂正常', 'evidence_ids': []}]
    evidence = [{'evidence_id': 'e1', 'quote': '低密度脂蛋白 3.4mmol/L'}]
    refuse, _ = refuse_if_no_evidence(claims, evidence)
    assert refuse

def test_validate_metric_name_rejects_unknown():
    known = {'总胆固醇', '低密度脂蛋白胆固醇', '空腹血糖'}

    def lookup(name):
        if name in known:
            return (True, [])
        return (False, [n for n in known if name in n or n in name][:3])
    unknown = validate_metric_name('c1', '不存在的体检项目XYZ', name_lookup=lookup)
    assert not unknown.passed
    assert '不存在' in unknown.failures[0]
    assert validate_metric_name('c2', '空腹血糖', name_lookup=lookup).passed

def test_validate_metric_name_directory_unavailable():
    result = validate_metric_name('c1', '空腹血糖', name_lookup=lambda name: (None, []))
    assert not result.passed
    assert '不可用' in result.failures[0]

def test_advice_without_evidence_rejected():
    evidence = [{'evidence_id': 'e1', 'quote': '每周中等强度有氧运动 150 分钟'}]
    bad = [{'claim_id': 'a1', 'type': 'advice', 'text': '每周运动 150 分钟', 'evidence_ids': []}]
    assert not validate_advice_has_evidence(bad, evidence).passed
    fake = [{'claim_id': 'a2', 'type': 'advice', 'text': '每周运动 150 分钟', 'evidence_ids': ['fake_ev']}]
    assert not validate_advice_has_evidence(fake, evidence).passed
    good = [{'claim_id': 'a3', 'type': 'advice', 'text': '每周运动 150 分钟', 'evidence_ids': ['e1']}]
    assert validate_advice_has_evidence(good, evidence).passed

def test_memory_rejects_knowledge_source():
    curator = MemoryCurator()
    for bad_source in ('document', 'webpage', 'report'):
        with pytest.raises(ValueError):
            curator.propose_candidate('u1', 'allergy', '用户对所有防腐剂过敏', source=bad_source)

def test_memory_low_confidence_candidate_skipped():
    curator = MemoryCurator()
    entry = curator.propose_candidate('u1', 'goal', '关注血脂管理', source='inferred', confidence=0.1)
    assert entry is None

def test_naturalize_metric_row_keeps_fields():
    text = naturalize_metric_row({'name_cn': '低密度脂蛋白胆固醇', 'metric_code': 'LDL_C', 'category': '血脂', 'unit': 'mmol/L', 'ref_text': '0-3.4', 'advice_hint': '结合运动与饮食干预'})
    assert '低密度脂蛋白胆固醇' in text and 'LDL_C' in text
    assert '血脂' in text and 'mmol/L' in text and ('0-3.4' in text)
    assert '结合运动与饮食干预' in text

def test_chunk_semantic_overlap():
    short = '短文本'
    assert chunk_sliding_window(short) == [short]
    long_text = '体检指标参考区间数值表格内容' * 60
    chunks = chunk_sliding_window(long_text, chunk_size=30, overlap=10)
    assert len(chunks) > 1
    assert all((len(c) <= 30 for c in chunks))
    overlaps = sum((1 for i in range(len(chunks) - 1) if chunks[i][-10:] in chunks[i + 1]))
    assert overlaps >= len(chunks) - 2

def test_build_chunks_evidence_row_single_chunk():
    docs = [{'id': 'd1', 'source_id': 's1', 'source_level': 1, 'knowledge_version': 'kv_test', 'content': {'source_type': 'metric_catalog', 'name_cn': '低密度脂蛋白胆固醇', 'metric_code': 'LDL_C', 'category': '血脂', 'unit': 'mmol/L', 'ref_text': '0-3.4', 'page': 2}}]
    chunks = build_chunks(docs, strategy='evidence_row')
    assert len(chunks) == 1
    assert chunks[0].strategy == 'evidence_row'
    assert chunks[0].source_type == 'metric_catalog'
    assert chunks[0].page == 2
    assert '低密度脂蛋白胆固醇' in chunks[0].text and '0-3.4' in chunks[0].text

def test_build_chunks_auto_routes_evidence_row():
    docs = [{'id': 'd1', 'source_id': 's1', 'content': {'source_type': 'metric_catalog', 'name_cn': '总胆固醇', 'metric_code': 'TC', 'unit': 'mmol/L', 'ref_text': '3.1-5.2'}}, {'id': 'd2', 'source_id': 's1', 'content': {'raw_text': '每周规律有氧运动有助于改善血脂谱。' * 200}}]
    chunks = build_chunks(docs, strategy='auto', chunk_size=100, overlap=20)
    strategies = {c.strategy for c in chunks}
    assert 'evidence_row' in strategies
    assert 'semantic_window' in strategies
