import json
from datetime import datetime
import pytest
from app.eval import run, judge, retrieval_bench


def test_missing_recall10_is_not_replaced_by_recall5():
    checks, missing = run._layer_gate_checks({'aggregated': {'recall@5': 1, 'mrr': 1}}, {'sample': 'demo'})
    assert not any(c['metric'] == 'recall@10' for c in checks)
    assert any('recall@10' in s for s in missing)


def test_missing_generation_prevents_gate(monkeypatch):
    monkeypatch.setattr(run, '_run_slices', lambda: {'pass_rate': 1, 'skipped': 0, 'total': 9})
    monkeypatch.setattr(run.retrieval_bench, 'run_retrieval_bench', lambda mode: {'aggregated': {'recall@10': 1, 'mrr': 1}})
    monkeypatch.setattr(run, '_load_real_judge_gen', lambda: None)
    monkeypatch.setattr(run.judge_mod, 'evaluate_report', lambda **kw: {'judge_mode': 'rule'})
    r = run.run_all(True)
    assert not r['gate']['passed']
    assert not r['gate']['coverage_complete']


def test_old_or_partially_judged_report_rejected(monkeypatch, tmp_path):
    monkeypatch.delenv('EVAL_JUDGE_REPORT', raising=False)
    p = tmp_path / 'judge.json'
    monkeypatch.setattr(run.glob, 'glob', lambda pattern: [str(p)])
    r = {'demo': False, 'cases': 10, 'succeeded': 10, 'llm_judged': 10, 'timestamp': '2020-01-01', 'aggregate': {'faithfulness': 1}}
    p.write_text(json.dumps(r))
    assert run._load_real_judge_gen() is None
    r.update(timestamp=datetime.now().isoformat(), llm_judged=9)
    p.write_text(json.dumps(r))
    assert run._load_real_judge_gen() is None


def test_llm_judge_receives_evidence_and_rejects_invalid_score(monkeypatch):
    captured = []
    class LLM:
        def chat(self, messages, **kwargs):
            captured.extend(messages)
            return {'choices': [{'message': {'content': '{"faithfulness": 1.5, "answer_relevancy": 1}'}}]}
    monkeypatch.setattr('app.gateway.adapters.llm.LLMAdapter', LLM)
    r = judge._llm_judge('q', 'report', 1, evidence=[{'evidence_id': 'e1', 'quote': '真实证据'}], claims=[{'text': '待核结论', 'evidence_ids': ['e1']}])
    assert '真实证据' in captured[-1]['content'] and '待核结论' in captured[-1]['content']
    assert 'error' in r


def test_retrieval_computes_distinct_recall_depths(monkeypatch):
    monkeypatch.setattr(retrieval_bench, 'RETRIEVAL_EVAL_SET', [{'query': 'x', 'topics': ['目标'], 'banks': [], 'expected_channels': ['bm25']}])
    corpus = [(str(i), '目标' if i in (0, 7) else '其他') for i in range(10)]
    monkeypatch.setattr(retrieval_bench, '_load_db_corpus', lambda: corpus)
    monkeypatch.setattr(retrieval_bench, '_search_self', lambda q, c: [str(i) for i in range(10)])
    r = retrieval_bench.run_retrieval_bench('real')
    assert r['aggregated']['recall@5'] == .5
    assert r['aggregated']['recall@10'] == 1


def test_pipeline_validation_error_blocks_gate(monkeypatch):
    monkeypatch.setattr(run, '_run_slices', lambda: {'pass_rate': 1, 'skipped': 0, 'total': 9})
    monkeypatch.setattr(run.retrieval_bench, 'run_retrieval_bench', lambda mode: {'aggregated': {'recall@10': 1, 'mrr': 1}})
    monkeypatch.setattr(run, '_load_real_judge_gen', lambda: {'sample': 'real_pipeline', 'judge_mode': 'llm', 'faithfulness': 1, 'citation_accuracy': 1, 'answer_relevancy': 1, 'check_error_count': 1})
    r = run.run_all(True)
    assert r['gate']['coverage_complete']
    assert not r['gate']['pipeline_validation_passed']
    assert not r['gate']['passed']


def test_explicit_version_not_replaced_by_missing_published_version(monkeypatch):
    from app.agents.retrieval_agent import _parallel_retrieve
    calls = []
    monkeypatch.setattr('app.factory.repository.get_current_version', lambda: calls.append('read'))
    state = _parallel_retrieve({'knowledge_version': 'kv_exp6_sample', 'user_id': '', 'query_plan': {'plans': []}, 'errors': []})
    assert state['knowledge_version'] == 'kv_exp6_sample'
    assert not calls


def test_rrf_environment_is_used_and_explicit_argument_wins(monkeypatch):
    from app.retrieval.channels import ChannelResult, fuse_and_rerank
    monkeypatch.setenv('RRF_K', '10')
    results = [ChannelResult(channel='bm25', doc_ids=['a'], scores=[1], snippets=['text'], metadata=[{}])]
    selected = fuse_and_rerank(results, 'q', expand_parents=False, rerank_enabled=False)
    explicit = fuse_and_rerank(results, 'q', rrf_k=60, expand_parents=False, rerank_enabled=False)
    assert selected[0]['rrf_score'] == pytest.approx(1 / 11, abs=1e-6)
    assert explicit[0]['rrf_score'] == pytest.approx(1 / 61, abs=1e-6)


def test_legacy_glucose_code_resolves_to_actual_catalog(monkeypatch):
    from types import SimpleNamespace
    scenario = {'code': 'GLU', 'name': '空腹血糖', 'value': 6.8, 'flag': 'high', 'unit': 'mmol/L', 'category': '血糖', 'ref': 'old'}
    row = SimpleNamespace(metric_code='GLU_FAST', name_cn='空腹血糖', unit='mmol/L', ref_text='3.9~6.1', category='血糖')
    monkeypatch.setattr(judge, '_REAL_SCENARIOS', [scenario])
    monkeypatch.setattr('app.factory.repository.get_metric_by_code', lambda code: None)
    monkeypatch.setattr('app.factory.repository.list_metric_catalog', lambda: [row])
    seeded = []
    monkeypatch.setattr(judge, '_seed_bench_metrics', lambda user, cases: seeded.extend(cases))
    monkeypatch.setattr(judge, '_run_real_pipeline', lambda sc, **kwargs: {'question': 'q', 'report_draft': {}, 'claims': [], 'evidence': [], 'check_errors': [], 'knowledge_version': 'kv', 'metric_trends': []})
    monkeypatch.setattr(judge, 'evaluate_report', lambda **kwargs: {'faithfulness': 1, 'citation_accuracy': 1, 'answer_relevancy': 1, 'llm_judge': {'faithfulness': 1, 'answer_relevancy': 1}})
    result = judge.run_real(1)
    assert seeded[0]['code'] == 'GLU_FAST' and seeded[0]['ref'] == '3.9~6.1'
    assert scenario['code'] == 'GLU'  # original fixture is preserved
    assert result['llm_judged'] == 1
