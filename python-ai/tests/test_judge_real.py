from __future__ import annotations
import json
import pytest
from app.eval import judge as judge_mod

class TestLLMJudgeParsing:

    def test_openai_response_parsed(self, monkeypatch):

        class _FakeLLM:

            def chat(self, messages, **kw):
                return {'choices': [{'message': {'content': '{"faithfulness": 0.9, "answer_relevancy": 0.8, "reason": "ok"}'}}]}
        monkeypatch.setattr('app.gateway.adapters.llm.LLMAdapter', lambda: _FakeLLM())
        out = judge_mod._llm_judge('问题', '报告正文', 5)
        assert out['faithfulness'] == 0.9
        assert out['answer_relevancy'] == 0.8
        assert 'error' not in out

    def test_markdown_code_block_tolerated(self, monkeypatch):

        class _FakeLLM:

            def chat(self, messages, **kw):
                return {'choices': [{'message': {'content': '```json\n{"faithfulness": 0.7, "answer_relevancy": 1.0, "reason": "x"}\n```'}}]}
        monkeypatch.setattr('app.gateway.adapters.llm.LLMAdapter', lambda: _FakeLLM())
        out = judge_mod._llm_judge('q', 'r', 1)
        assert out['faithfulness'] == 0.7

    def test_failure_returns_error(self, monkeypatch):

        class _FakeLLM:

            def chat(self, messages, **kw):
                raise RuntimeError('api down')
        monkeypatch.setattr('app.gateway.adapters.llm.LLMAdapter', lambda: _FakeLLM())
        out = judge_mod._llm_judge('q', 'r', 1)
        assert 'error' in out
_REVIEW_MD = '# judge 人工抽检对照卡（结论级）\n\n| # | 结论 | 引用证据原文 | judge 判定 | 预填建议 | 人工判定 |\n|---|---|---|---|---|---|\n| 1.1 | LDL-C 4.2 偏高 | · 参考区间 <3.4 | 有依据 | 有依据 | 有依据 |\n| 1.2 | 建议每周 150 分钟有氧 | · 每周累计 150 分钟 | 有依据 | 有依据 | 部分依据 |\n| 2.1 | 血糖 6.8 属空腹血糖受损 | · ≥6.1 且 <7.0 为受损 | 有依据 | 有依据 | 无依据 |\n| 2.2 | 某某结论 | · 某某证据 | 无依据 | 无依据 |  |\n'

class TestHumanCompare:

    def test_parse_and_claim_level_agreement(self, tmp_path):
        f = tmp_path / 'review.md'
        f.write_text(_REVIEW_MD, encoding='utf-8')
        result = judge_mod.human_compare(str(f))
        assert result['rated_claims'] == 3, '第 4 条未人工判定不计入'
        assert result['full_agree'] == 1
        assert result['half_agree'] == 1
        assert result['disagree'] == 1
        assert result['agreement_rate'] == pytest.approx(0.5)
        assert result['judge_trustworthy'] is False

    def test_full_agreement_trustworthy(self, tmp_path):
        f = tmp_path / 'review.md'
        f.write_text(_REVIEW_MD.replace('部分依据 |\n| 2.1', '有依据 |\n| 2.1').replace('无依据 |\n| 2.2', '有依据 |\n| 2.2'), encoding='utf-8')
        result = judge_mod.human_compare(str(f))
        assert result['agreement_rate'] == pytest.approx(1.0)
        assert result['judge_trustworthy'] is True

    def test_empty_human_scores(self, tmp_path):
        f = tmp_path / 'review.md'
        f.write_text('| 1.1 | 结论 | 证据 | 有依据 | 有依据 |  |\n', encoding='utf-8')
        result = judge_mod.human_compare(str(f))
        assert result['rated'] == 0
        assert 'error' in result

class TestClaimJudgeVerdict:

    def _ev_map(self):
        return {'e1': '体检指标 低密度脂蛋白胆固醇 参考区间 <3.4 mmol/L', 'e2': '推荐以中等强度有氧运动为主，每周累计 150 分钟以上'}

    def test_supported_claim(self):
        verdict, _ = judge_mod._claim_judge_verdict({'text': '低密度脂蛋白胆固醇 参考区间 <3.4', 'evidence_ids': ['e1']}, self._ev_map())
        assert verdict == '有依据'

    def test_nonexistent_evidence(self):
        verdict, suggest = judge_mod._claim_judge_verdict({'text': '某结论', 'evidence_ids': ['not-exist']}, self._ev_map())
        assert verdict == '无依据'
        assert '不存在' in suggest

    def test_no_evidence_ids(self):
        verdict, _ = judge_mod._claim_judge_verdict({'text': '某结论', 'evidence_ids': []}, self._ev_map())
        assert verdict == '无依据'

class TestLoadRealJudgeGen:

    def test_missing_report_returns_none(self, monkeypatch):
        import app.eval.run as run_mod
        monkeypatch.setattr(run_mod.glob, 'glob', lambda p: [])
        assert run_mod._load_real_judge_gen() is None

    def test_demo_report_rejected(self, monkeypatch, tmp_path):
        import app.eval.run as run_mod
        report = tmp_path / 'judge_real_20260920.json'
        report.write_text(json.dumps({'demo': True, 'aggregate': {}}))
        monkeypatch.setattr(run_mod.glob, 'glob', lambda p: [str(report)])
        assert run_mod._load_real_judge_gen() is None

    def test_real_report_accepted(self, monkeypatch, tmp_path):
        import app.eval.run as run_mod
        report = tmp_path / 'judge_real_20260920.json'
        report.write_text(json.dumps({'demo': False, 'cases': 10, 'succeeded': 10, 'llm_judged': 10, 'timestamp': __import__('datetime').datetime.now().isoformat(), 'aggregate': {'faithfulness': 1.0, 'citation_accuracy': 1.0, 'answer_relevancy': 1.0, 'llm_judge_faithfulness': 0.93, 'llm_judge_answer_relevancy': 0.88}}))
        monkeypatch.setattr(run_mod.glob, 'glob', lambda p: [str(report)])
        gen = run_mod._load_real_judge_gen()
        assert gen is not None
        assert gen['sample'] == 'real_pipeline'
        assert gen['judge_mode'] == 'llm'
        assert gen['faithfulness'] == 0.93
        assert gen['answer_relevancy'] == 0.88

class TestMetricRelatedBoundary:

    def test_hgb_not_related_to_hba1c(self):
        from app.agents.report_agent import _metric_related_to_quote
        assert _metric_related_to_quote('血红蛋白', 'HGB', '体检指标 糖化血红蛋白 | 编码 HBA1C | 参考区间 4%~6%') is False

    def test_hgb_related_to_own_record(self):
        from app.agents.report_agent import _metric_related_to_quote
        assert _metric_related_to_quote('血红蛋白', 'HGB', '血红蛋白 145g/L（正常）参考区间 130-175') is True

    def test_metric_code_exact_match(self):
        from app.agents.report_agent import _metric_related_to_quote
        assert _metric_related_to_quote('血红蛋白', 'HGB', '体检指标 血红蛋白 | 编码 HGB | 参考区间 130-175') is True
        assert _metric_related_to_quote('血红蛋白', 'HBA1C', '体检指标 血红蛋白 | 编码 HGB') is True

    def test_fasting_glucose_not_broken(self):
        from app.agents.report_agent import _metric_related_to_quote
        assert _metric_related_to_quote('空腹血糖', 'GLU', '空腹血糖 6.8mmol/L（偏高）参考区间 3.9-6.1') is True
