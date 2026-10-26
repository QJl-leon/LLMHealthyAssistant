import os
from uuid import uuid4
import pytest
from app.factory.health_parser import TableParseContext, _is_continuation_table, _is_full_width_note_row, _row_is_header_row, build_report, compute_report_hash, dedupe_by_name, flag_from_hint, flag_of, merge_channel_metrics, normalize_metric, normalize_metric_name, parse_exam_image, parse_exam_pdf, parse_metric_lines, parse_reference_text, parse_result_value, reflow_ocr_lines
from app.factory.models import HealthMetric, MetricCatalogRow

def _catalog(name_cn='空腹血糖', code='GLU', category='血糖', unit='mmol/L', low=3.9, high=6.1, ref_text='3.9-6.1', direction='both'):
    return MetricCatalogRow(metric_code=code, name_cn=name_cn, category=category, unit=unit, ref_low=low, ref_high=high, ref_text=ref_text, direction=direction, source_id=uuid4())

def _metric(metric_name='空腹血糖', metric_code='GLU', value=5.4, unit='mmol/L', flag='normal', report_id=None):
    return HealthMetric(report_id=report_id or uuid4(), user_id='u1', metric_code=metric_code, metric_name=metric_name, category='血糖', value_num=value, value_text=str(value), unit=unit, ref_low=3.9, ref_high=6.1, ref_text='3.9-6.1', flag=flag, measured_at='2026-01-01')

def test_flag_of_within_range_is_normal():
    assert flag_of(5.4, 3.9, 6.1) == 'normal'

def test_flag_of_below_low_is_low():
    assert flag_of(3.5, 3.9, 6.1) == 'low'

def test_flag_of_above_high_is_high():
    assert flag_of(7.0, 3.9, 6.1) == 'high'

def test_flag_of_upper_bound_only():
    assert flag_of(4.0, None, 5.2) == 'normal'
    assert flag_of(6.0, None, 5.2) == 'high'

def test_flag_of_lower_bound_only():
    assert flag_of(1.5, 1.0, None) == 'normal'
    assert flag_of(0.6, 1.0, None) == 'low'
    assert flag_of(0.5, 1.0, None) == 'critical'

def test_flag_of_qualitative():
    assert flag_of('阴性', None, None) == 'normal'
    assert flag_of('阳性', None, None) == 'high'
    assert flag_of('(-)', None, None) == 'normal'
    assert flag_of('(+)', None, None) == 'high'

def test_flag_of_critical_by_fold():
    assert flag_of(30.0, 1.0, 10.0) == 'critical'
    assert flag_of(15.0, 1.0, 10.0) == 'high'
    assert flag_of(0.4, 1.0, 10.0) == 'critical'

def test_flag_of_critical_key_items():
    assert flag_of(7.2, 3.9, 6.1, metric_key='GLU|空腹血糖', unit='mmol/L') == 'critical'
    assert flag_of(145, 90, 140, metric_key='SBP|收缩压', unit='mmHg') == 'critical'
    assert flag_of(95, 60, 90, metric_key='DBP|舒张压', unit='mmHg') == 'critical'
    assert flag_of(7.2, 3.9, 6.1, metric_key='空腹血糖', unit='mg/dL') == 'high'

def test_flag_of_direction_suppresses_meaningless_side():
    assert flag_of(3.0, 3.9, 6.1, direction='high') == 'normal'
    assert flag_of(9.0, 3.9, 6.1, direction='low') == 'normal'
    assert flag_of(9.0, 3.9, 6.1, direction='both') == 'high'

def test_flag_of_unknown():
    assert flag_of(None, 3.9, 6.1) == 'unknown'
    assert flag_of(5.4, None, None) == 'unknown'
    assert flag_of('未检', None, None) == 'unknown'

def test_flag_from_hint():
    assert flag_from_hint('↑') == 'high'
    assert flag_from_hint('↓') == 'low'
    assert flag_from_hint('正常') == 'unknown'
    assert flag_from_hint('') == 'unknown'

@pytest.mark.parametrize('raw,expected', [('3.9-6.1', (3.9, 6.1, '3.9-6.1')), ('3.9~6.1', (3.9, 6.1, '3.9~6.1')), ('3.9—6.1', (3.9, 6.1, '3.9—6.1')), ('0-40', (0.0, 40.0, '0-40')), ('<5.2', (None, 5.2, '<5.2')), ('≤5.2', (None, 5.2, '≤5.2')), ('>1.0', (1.0, None, '>1.0')), ('≥1.0', (1.0, None, '≥1.0')), ('阴性/阳性', (None, None, '阴性/阳性')), ('', (None, None, ''))])
def test_parse_reference_text(raw, expected):
    assert parse_reference_text(raw) == expected

def test_parse_result_value():
    assert parse_result_value('5.40') == (5.4, '5.40')
    assert parse_result_value('7.2↑') == (7.2, '7.2↑')
    assert parse_result_value('<0.05') == (0.05, '<0.05')
    assert parse_result_value('阴性') == (None, '阴性')
    assert parse_result_value('') == (None, '')

def test_normalize_metric_name():
    assert normalize_metric_name('  空腹血糖 ↑ ') == '空腹血糖'
    assert normalize_metric_name('1. 谷丙转氨酶*') == '谷丙转氨酶'
    assert normalize_metric_name('（2）总胆固醇') == '总胆固醇'
    assert normalize_metric_name('低密度脂蛋白胆固醇(LDL-C)') == '低密度脂蛋白胆固醇(LDL-C)'
    assert normalize_metric_name('') == ''

def test_normalize_metric_catalog_hit():
    m = normalize_metric('空腹血糖', '5.40', 'mmol/L', '3.9-6.1', page=2, lookup=lambda name: _catalog())
    assert m is not None
    assert (m.metric_code, m.metric_name, m.category) == ('GLU', '空腹血糖', '血糖')
    assert m.unit == 'mmol/L'
    assert (m.ref_low, m.ref_high, m.ref_text) == (3.9, 6.1, '3.9-6.1')
    assert m.value_num == 5.4 and m.flag == 'normal' and (m.source_page == 2)

def test_normalize_metric_catalog_miss_uses_report_ref():
    m = normalize_metric('某新指标', '70', 'mg/dL', '0-40', lookup=lambda name: None)
    assert m is not None
    assert m.category == '未分类'
    assert m.metric_code.startswith('X_')
    assert (m.ref_low, m.ref_high, m.ref_text) == (0.0, 40.0, '0-40')
    assert m.flag == 'high'

def test_normalize_metric_empty_name_returns_none():
    assert normalize_metric('', '5.4', 'mmol/L', '3.9-6.1', lookup=lambda n: None) is None

def test_normalize_metric_unit_mismatch_keeps_report_values():
    m = normalize_metric('空腹血糖', '100', 'mg/dL', '70-110', lookup=lambda name: _catalog())
    assert m is not None
    assert m.unit == 'mg/dL'
    assert (m.ref_low, m.ref_high) == (70.0, 110.0)
    assert m.flag == 'normal'

def test_normalize_metric_qualitative():
    m = normalize_metric('乙肝表面抗原', '阳性', '', '阴性/阳性', lookup=lambda n: None)
    assert m is not None
    assert m.value_num is None and m.value_text == '阳性'
    assert m.flag == 'high'

def test_normalize_metric_lookup_failure_falls_back():

    def boom(_name):
        raise RuntimeError('db down')
    m = normalize_metric('空腹血糖', '5.4', 'mmol/L', '3.9-6.1', lookup=boom)
    assert m is not None and m.category == '未分类' and (m.flag == 'normal')
FIXTURE_LINES = ['某某体检中心  体检报告', '项目  结果  单位  参考范围  提示', '空腹血糖  5.40  mmol/L  3.9-6.1', '总胆固醇  6.80  mmol/L  3.1-5.2  ↑', '乙肝表面抗原  阴性  阴性/阳性', '未见异常']

def test_parse_metric_lines_fixture():
    metrics = parse_metric_lines(FIXTURE_LINES, page=1, lookup=lambda n: None)
    got = {m.metric_name: m for m in metrics}
    assert set(got) == {'空腹血糖', '总胆固醇', '乙肝表面抗原'}
    assert got['空腹血糖'].value_num == 5.4 and got['空腹血糖'].flag == 'normal'
    assert got['总胆固醇'].value_num == 6.8 and got['总胆固醇'].flag == 'high'
    assert got['总胆固醇'].unit == 'mmol/L' and got['总胆固醇'].ref_high == 5.2
    assert got['乙肝表面抗原'].value_num is None
    assert got['乙肝表面抗原'].flag == 'normal'
    assert got['乙肝表面抗原'].ref_text == '阴性/阳性'
    assert all((m.source_page == 1 for m in metrics))

def test_parse_metric_lines_skips_titles():
    assert parse_metric_lines(['体检报告', '一般检查', ''], lookup=lambda n: None) == []

def test_reflow_ocr_lines_groups_by_y():

    def poly(x, y):
        return [{'X': x, 'Y': y}, {'X': x + 60, 'Y': y}, {'X': x + 60, 'Y': y + 14}, {'X': x, 'Y': y + 14}]
    detections = [{'DetectedText': '空腹血糖', 'Polygon': poly(10, 10)}, {'DetectedText': '5.4', 'Polygon': poly(200, 11)}, {'DetectedText': 'mmol/L', 'Polygon': poly(260, 10)}, {'DetectedText': '3.9-6.1', 'Polygon': poly(340, 10)}, {'DetectedText': '总胆固醇', 'Polygon': poly(10, 40)}, {'DetectedText': '6.8', 'Polygon': poly(200, 41)}, {'DetectedText': 'mmol/L', 'Polygon': poly(260, 40)}, {'DetectedText': '3.1-5.2', 'Polygon': poly(340, 40)}]
    lines = reflow_ocr_lines(detections)
    assert len(lines) == 2
    assert '空腹血糖' in lines[0] and '5.4' in lines[0] and ('3.9-6.1' in lines[0])
    metrics = parse_metric_lines(lines, lookup=lambda n: None)
    assert {m.metric_name for m in metrics} == {'空腹血糖', '总胆固醇'}

def test_reflow_ocr_lines_without_polygon_returns_empty():
    assert reflow_ocr_lines([{'DetectedText': '空腹血糖'}]) == []
    assert reflow_ocr_lines(None) == []

def test_build_report_backfills_metrics():
    metrics = [_metric(value=5.4), _metric(metric_name='总胆固醇', metric_code='TC', value=6.8)]
    report, out = build_report(metrics, 'u1', '2026-01-01', '某某体检中心')
    assert report.user_id == 'u1' and report.report_date == '2026-01-01'
    assert report.institution == '某某体检中心' and report.report_type == 'physical_exam'
    assert len(report.content_hash) == 32
    assert all((m.report_id == report.id and m.user_id == 'u1' for m in out))
    assert all((m.measured_at == '2026-01-01' for m in out))

def test_report_hash_stable_and_date_sensitive():
    metrics = [_metric(value=5.4)]
    h1 = compute_report_hash('u1', '2026-01-01', metrics)
    assert h1 == compute_report_hash('u1', '2026-01-01', [_metric(value=5.4)])
    assert h1 != compute_report_hash('u1', '2026-06-01', [_metric(value=5.4)])
    assert h1 != compute_report_hash('u2', '2026-01-01', [_metric(value=5.4)])

def test_merge_channel_metrics_same_value_merges():
    ocr = [_metric(value=5.4)]
    vlm = [_metric(value=5.4)]
    merged, rejected = merge_channel_metrics(ocr, vlm)
    assert len(merged) == 1 and (not rejected)

def test_merge_channel_metrics_conflict_picks_vlm():
    ocr = [_metric(metric_name='身高', metric_code='', value=5.12, unit='cm')]
    vlm = [_metric(metric_name='身高', metric_code='', value=178, unit='cm')]
    merged, rejected = merge_channel_metrics(ocr, vlm)
    assert len(merged) == 1 and merged[0].value_num == 178
    assert len(rejected) == 1
    assert rejected[0]['value_text'] == '5.12' and rejected[0]['channel'] == 'ocr'
    assert '采信 VLM' in rejected[0]['reason']

def test_merge_channel_metrics_single_channel_only():
    ocr = [_metric(value=5.4)]
    vlm = [_metric(metric_name='总胆固醇', metric_code='TC', value=6.8)]
    merged, rejected = merge_channel_metrics(ocr, vlm)
    assert len(merged) == 2 and (not rejected)

def test_merge_ocr_only_commonsense_violation_rejected():
    ocr = [_metric(metric_name='身高', metric_code='', value=5.12, unit='cm')]
    merged, rejected = merge_channel_metrics(ocr, [])
    assert not merged
    assert len(rejected) == 1
    assert rejected[0]['channel'] == 'ocr' and '常识范围' in rejected[0]['reason']

def test_merge_vlm_value_commonsense_violation_rejected():
    vlm = [_metric(metric_name='身高', metric_code='', value=999, unit='cm')]
    merged, rejected = merge_channel_metrics([], vlm)
    assert not merged
    assert len(rejected) == 1
    assert rejected[0]['channel'] == 'vlm' and 'VLM 值常识越界' in rejected[0]['reason']

def test_merge_vlm_only_fallback_kept():
    vlm = [_metric(metric_name='身高', metric_code='', value=178, unit='cm')]
    merged, rejected = merge_channel_metrics([], vlm)
    assert len(merged) == 1 and merged[0].value_num == 178 and (not rejected)

def test_commonsense_unit_mismatch_not_blocked():
    ocr = [_metric(metric_name='空腹血糖', metric_code='GLU', value=98, unit='mg/dL')]
    merged, rejected = merge_channel_metrics(ocr, [])
    assert len(merged) == 1 and (not rejected)

def test_dedupe_by_name_keeps_first():
    metrics = [_metric(value=5.4), _metric(value=9.9), _metric(metric_name='总胆固醇', value=6.8)]
    out = dedupe_by_name(metrics)
    assert len(out) == 2 and out[0].value_num == 5.4

class _StubOCR:

    def __init__(self, text):
        self.text = text

    def extract_text(self, image_url):
        return {'engine': 'stub', 'text': self.text}

class _StubVLM:

    def __init__(self, payload):
        self.payload = payload

    def analyze_image(self, image_url, prompt):
        return {'choices': [{'message': {'content': self.payload}}]}

def test_parse_exam_image_dual_channel():
    ocr_text = '空腹血糖  5.4  mmol/L  3.9-6.1\n总胆固醇  6.8  mmol/L  3.1-5.2'
    vlm_payload = '{"metrics": [{"name": "空腹血糖", "result": "5.4", "unit": "mmol/L", "ref": "3.9-6.1"}, {"name": "尿酸", "result": "480", "unit": "umol/L", "ref": "208-428"}], "report_date": "2026-01-10", "institution": "某某体检中心"}'
    report, metrics = parse_exam_image('not-exists.png', 'u1', ocr_adapter=_StubOCR(ocr_text), vlm_adapter=_StubVLM(vlm_payload), lookup=lambda n: None)
    assert report.report_date == '2026-01-10'
    assert report.institution == '某某体检中心'
    by_name = {m.metric_name: m for m in metrics}
    assert set(by_name) == {'空腹血糖', '总胆固醇', '尿酸'}
    assert by_name['空腹血糖'].value_num == 5.4
    assert by_name['尿酸'].ref_high == 428.0 and by_name['尿酸'].flag == 'high'
    assert all((m.report_id == report.id and m.user_id == 'u1' for m in metrics))
_FIXTURE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'fixtures')
PDF_LINED = os.path.join(_FIXTURE_DIR, 'exam_report_multipage.pdf')
PDF_BORDERLESS = os.path.join(_FIXTURE_DIR, 'exam_report_borderless.pdf')

def _parse_to_map(pdf_path: str) -> dict:
    assert os.path.exists(pdf_path), f'夹具缺失，请先运行 make_exam_pdf.py：{pdf_path}'
    _, metrics = parse_exam_pdf(pdf_path, 'u1', lookup=lambda n: None)
    return {m.metric_name: m for m in metrics}

@pytest.fixture(scope='module')
def lined():
    return _parse_to_map(PDF_LINED)

@pytest.fixture(scope='module')
def borderless():
    return _parse_to_map(PDF_BORDERLESS)

def test_merged_rowspan_category_forward_filled(lined):
    assert lined['红细胞计数'].category == '血常规'
    assert lined['血红蛋白'].category == '血常规'
    assert lined['天冬氨酸氨基转移酶'].category == '肝功能'

def test_colspan_note_row_is_not_metric(lined):
    assert not any(('备注' in name for name in lined))

def test_cross_page_continuation_without_header(lined):
    assert {'尿白细胞', '尿胆原', '尿酸碱度'} <= set(lined)
    assert lined['尿白细胞'].source_page == 3

def test_cross_page_name_carry_over(lined):
    assert '糖化血红蛋白' in lined
    m = lined['糖化血红蛋白']
    assert (m.value_num, m.unit) == (6.2, '%')
    assert m.source_page == 2
    assert m.flag == 'high'

def test_repeated_header_row_is_skipped(lined):
    assert '项目类别' not in lined
    assert '胸部正位片' in lined

def test_no_empty_or_bleeding_names(lined):
    assert all((name.strip() for name in lined))
    assert not [name for name in lined if ' ' in name]

def test_section_title_stops_name_carry(lined):
    assert lined['尿蛋白'].metric_name == '尿蛋白'
    assert lined['尿蛋白'].category == '尿常规'

def test_borderless_table_structure_reconstructed(borderless):
    assert {'白细胞计数', '红细胞计数', '丙氨酸氨基转移酶', '天冬氨酸氨基转移酶'} <= set(borderless)
    assert borderless['红细胞计数'].category == '血常规'
    assert borderless['天冬氨酸氨基转移酶'].category == '肝功能'

def test_borderless_note_name_carry_and_section(borderless):
    assert not any(('备注' in name for name in borderless))
    assert '糖化血红蛋白' in borderless
    assert borderless['糖化血红蛋白'].value_num == 6.2
    assert borderless['尿蛋白'].category == '尿常规'

def test_row_is_header_row():
    assert _row_is_header_row(['项目类别', '检查项目', '结果', '单位', '参考区间', '提示'])
    assert not _row_is_header_row(['', '尿白细胞', '阴性', '', '阴性', ''])

def test_is_full_width_note_row():
    assert _is_full_width_note_row(['备注：本报告仅对本次送检样本负责，如有疑问请咨询检验科。', None, None])
    assert _is_full_width_note_row(['注：本页无数据'])
    assert not _is_full_width_note_row(['', '尿蛋白', '阴性', '', '阴性', ''])

def test_is_continuation_table_guards():
    ctx = TableParseContext(header_col_map={'name': 1, 'value': 2}, header_ncols=6)
    assert _is_continuation_table([['', '尿白细胞', '阴性', '', '阴性', '']], ctx)
    ctx.pending_name = '糖化血红蛋白'
    assert _is_continuation_table([['', '', '6.2', '%', '4.0-6.0', '↑']], ctx)
    ctx.pending_name = ''
    assert not _is_continuation_table([['', '', '6.2', '%', '4.0-6.0', '↑']], ctx)
    assert not _is_continuation_table([['', '尿白细胞', '阴性']], ctx)
    assert not _is_continuation_table([['', '尿白细胞', '阴性', '', '阴性', '']], TableParseContext())

def _db_available() -> bool:
    try:
        import psycopg2
        from app.factory.repository import DATABASE_URL
        conn = psycopg2.connect(DATABASE_URL, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False
_DB_SKIP = pytest.mark.skipif(not _db_available(), reason='数据库不可用，跳过只读集成用例')
_GHOST_USER = '__pytest_not_exist_user__'

@_DB_SKIP
def test_abnormal_metrics_of_ghost_user_is_empty():
    from app.health.trends import abnormal_metrics_of
    assert abnormal_metrics_of(_GHOST_USER) == []

@_DB_SKIP
def test_build_trends_ghost_user_is_empty():
    from app.health.trends import build_trends
    assert build_trends(_GHOST_USER) == []

@_DB_SKIP
def test_trend_summary_ghost_user_no_record():
    from app.health.trends import trend_summary
    text = trend_summary(_GHOST_USER)
    assert '暂无' in text
