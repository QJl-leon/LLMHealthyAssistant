import pytest
from app.retrieval.hyde import HYDE_DEFAULT_ON, prepare_dense_query, should_use_hyde, strip_numbers
from app.retrieval.synonyms import SYNONYM_MAP, canonical_terms, coverage_of_metric_names, expand_terms

def test_expand_terms_appends_without_replacing():
    q = '坏胆固醇高了怎么办'
    out = expand_terms(q)
    assert out.startswith(q)
    assert '低密度脂蛋白胆固醇' in out.split(q)[1]

def test_expand_terms_handles_ascii_abbreviation_case_insensitively():
    assert '低密度脂蛋白胆固醇' in expand_terms('LDL 偏高')
    assert '血清肌酐' in expand_terms('Crea 正常吗')

def test_expand_terms_maps_upper_word_to_multiple_metrics():
    got = expand_terms('血脂高')
    for name in ('总胆固醇', '甘油三酯', '低密度脂蛋白胆固醇'):
        assert name in got
    got2 = expand_terms('转氨酶有点高')
    assert '丙氨酸氨基转移酶' in got2 and '天门冬氨酸氨基转移酶' in got2

def test_expand_terms_no_false_positive():
    assert expand_terms('最近总是口渴') == '最近总是口渴'
    assert expand_terms('') == ''

def test_expand_terms_does_not_duplicate_existing_term():
    q = '低密度脂蛋白胆固醇偏高'
    out = expand_terms(q)
    assert out.count('低密度脂蛋白胆固醇') == 1

def test_expand_terms_respects_max_terms():
    out = expand_terms('血脂高', max_terms=2)
    added = out.split('血脂高', 1)[1].split()
    assert len(added) == 2

def test_canonical_terms_reports_hits_only():
    assert set(canonical_terms('转氨酶高')) >= {'丙氨酸氨基转移酶', '天门冬氨酸氨基转移酶'}
    assert canonical_terms('最近总是口渴') == []

def test_synonym_map_covers_all_metric_catalog_names():
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
        from app.factory.repository import DATABASE_URL
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute('SELECT name_cn FROM metric_catalog')
        names = [r['name_cn'] for r in cur.fetchall()]
        cur.close()
        conn.close()
    except Exception as e:
        pytest.skip(f'数据库不可用，跳过覆盖率守卫: {e}')
    assert names, 'metric_catalog 为空，守卫无效'
    cov = coverage_of_metric_names(names)
    assert cov['missing'] == [], f"同义表未覆盖这些指标名: {cov['missing']}"

def test_strip_numbers_removes_concrete_values():
    got = strip_numbers('有氧运动每周 150 分钟，心率控制在 120，参考区间 3.5-9.5')
    assert '150' not in got and '120' not in got
    assert '3.5' not in got and '9.5' not in got
    assert '某值' in got

def test_should_use_hyde_boundaries():
    assert should_use_hyde('血脂高的人该怎么锻炼') is True
    assert should_use_hyde('低密度脂蛋白 3.8 怎么办') is False
    assert should_use_hyde('') is False
    assert should_use_hyde('很长很长的问题' * 5) is False

def test_prepare_dense_query_disabled_returns_original():
    q = '血脂高的人该怎么锻炼'
    assert prepare_dense_query(q, enabled=False) == (q, None)

def test_prepare_dense_query_skips_exact_query_even_when_enabled():
    q = '低密度脂蛋白 3.8'
    assert prepare_dense_query(q, enabled=True) == (q, None)

def test_hyde_default_off_is_a_documented_decision():
    assert HYDE_DEFAULT_ON is False
