from app.agents.report_agent import _DEGRADED_MARK, _build_retry_block, degrade_failed_sections
from app.evidence.conflicts import conflict_is_addressed, detect_evidence_conflicts, validate_conflicts_addressed

def test_retry_block_empty_on_first_round():
    assert _build_retry_block({'errors': [], 'report_draft': {}}) == ''
    assert _build_retry_block({'errors': [{'message': 'x'}], 'report_draft': {}}) == ''

def test_retry_block_carries_specific_errors():
    state = {'report_draft': {'sections': {'observation': '...'}}, 'errors': [{'error_code': 'CITATION_MISMATCH', 'message': '报告正文引用编号无效: facts:[7]', 'claim_id': ''}, {'error_code': 'CITATION_MISMATCH', 'message': '指标数值与体检数据不一致: 6.2', 'claim_id': 'c1'}]}
    block = _build_retry_block(state)
    assert 'facts:[7]' in block
    assert '指标数值与体检数据不一致' in block
    assert 'c1' in block
    assert '定向修正' in block

def test_retry_block_tolerates_malformed_errors():
    state = {'report_draft': {'sections': {}}, 'errors': ['not-a-dict', {}, {'message': ''}]}
    assert _build_retry_block(state) == ''

def _sections() -> dict:
    return {'observation': '本次体检共 3 项异常', 'facts': '低密度脂蛋白 3.8 mmol/L', 'metric_reading': '血脂偏高', 'exercise_advice': [{'text': '每周有氧运动 [7]', 'evidence_ids': ['e1']}], 'lifestyle_advice': [{'text': '低脂饮食 [1]', 'evidence_ids': ['e2']}]}

def test_degrade_only_failed_sections():
    errors = [{'message': '报告正文引用编号无效: exercise_advice:[7]'}]
    kept, degraded = degrade_failed_sections(_sections(), errors)
    assert degraded == ['exercise_advice']
    assert kept['exercise_advice'] == []
    assert kept['observation'] == '本次体检共 3 项异常'
    assert kept['lifestyle_advice']

def test_degrade_marks_text_section_with_explicit_note():
    errors = [{'message': '报告正文引用编号无效: metric_reading:[9]'}]
    kept, degraded = degrade_failed_sections(_sections(), errors)
    assert degraded == ['metric_reading']
    assert kept['metric_reading'] == _DEGRADED_MARK

def test_degrade_refuses_when_nothing_survives():
    original = {'observation': '', 'facts': '', 'metric_reading': '', 'exercise_advice': [], 'lifestyle_advice': []}
    errors = [{'message': '报告正文引用编号无效: facts:[9]'}, {'message': '报告正文引用编号无效: metric_reading:[9]'}]
    kept, degraded = degrade_failed_sections(original, errors)
    assert degraded == []
    assert kept == original

def test_degrade_noop_without_errors():
    s = _sections()
    kept, degraded = degrade_failed_sections(s, [])
    assert degraded == [] and kept == s

def _evidence():
    return [{'evidence_id': 'e1', 'quote': '高血压患者推荐进行中等强度有氧运动，有助于控制血压'}, {'evidence_id': 'e2', 'quote': '血压控制不佳时应避免剧烈运动，存在风险'}, {'evidence_id': 'e3', 'quote': '饮食上建议减少钠盐摄入'}]

def test_detect_conflict_on_opposite_polarity():
    conflicts = detect_evidence_conflicts(_evidence())
    topics = {c['topic'] for c in conflicts}
    assert '血压' in topics
    c = next((c for c in conflicts if c['topic'] == '血压'))
    assert set(c['evidence_ids']) == {'e1', 'e2'}
    assert 'recommend' in c['polarities'] and 'avoid' in c['polarities']

def test_no_conflict_when_same_polarity():
    ev = [{'evidence_id': 'e1', 'quote': '推荐有氧运动，有助于血压控制'}, {'evidence_id': 'e2', 'quote': '建议规律运动，可以改善血压'}]
    assert detect_evidence_conflicts(ev) == []

def test_conflict_addressed_by_conflicts_section():
    c = {'topic': '血压', 'evidence_ids': ['e1', 'e2']}
    assert conflict_is_addressed(c, {'conflicts': '关于血压存在不同建议'}) is True
    assert conflict_is_addressed(c, {'conflicts': ''}) is False

def test_conflict_addressed_by_neutral_marker():
    c = {'topic': '血压', 'evidence_ids': ['e1']}
    sections = {'metric_reading': '血压方面存在不同说法，需个体化评估'}
    assert conflict_is_addressed(c, sections) is True

def test_conflict_gate_reports_unaddressed():
    conflicts = detect_evidence_conflicts(_evidence())
    errors = validate_conflicts_addressed(conflicts, {'conflicts': ''})
    assert errors, '未处理冲突必须产生校验失败'
    assert all((e['error_code'] == 'CITATION_MISMATCH' for e in errors))
    joined = ' '.join((e['message'] for e in errors))
    assert '血压' in joined and '运动' in joined
    ok = validate_conflicts_addressed(conflicts, {'conflicts': '关于血压与运动存在不同建议'})
    assert ok == []
