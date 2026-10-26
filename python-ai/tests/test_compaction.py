from __future__ import annotations
import pytest
from app.context.compaction import compact_discussion, compact_evidence, compact_observations, compact_state, estimate_tokens, extract_numbers, should_compact

def _ev(i: int, quote: str='', **kw) -> dict:
    return {'evidence_id': f'ev-{i}', 'quote': quote or f'证据{i}：中等强度有氧运动每周 150 分钟，参考区间 3.4-4.5 mmol/L', 'source_name': f'指南{i}', 'source_url': f'https://example.org/g/{i}', 'source_type': 'guideline' if i % 2 else 'case', **kw}

class TestTrigger:

    def test_below_threshold_not_triggered(self):
        assert should_compact('短文本', trigger_tokens=1000) is False

    def test_above_threshold_triggered(self):
        long_text = '证据内容 ' * 500
        assert should_compact(long_text, trigger_tokens=100) is True

    def test_estimate_tokens_chinese(self):
        assert estimate_tokens('健' * 150) == pytest.approx(101, abs=2)

    def test_compact_state_respects_threshold(self):
        state = {'evidence': [_ev(1)], 'image_observations': [], 'validated_claims': [], 'errors': []}
        out, report = compact_state(state, trigger_tokens=10 ** 9)
        assert report['triggered'] is False
        assert out['evidence'] == state['evidence']

class TestEvidenceLayer:

    def test_cited_mode_keeps_only_cited_plus_summary(self):
        evidence = [_ev(i) for i in range(1, 11)]
        out, stats = compact_evidence(evidence, cited_ids={'ev-2', 'ev-5'})
        kept_ids = [e['evidence_id'] for e in out if e.get('evidence_id')]
        assert kept_ids == ['ev-2', 'ev-5'], '必须只保留被引用证据（原顺序）'
        summary = [e for e in out if e.get('compacted')]
        assert len(summary) == 1
        assert '8 条' in summary[0]['quote']
        assert stats['dropped'] == 8

    def test_topn_mode_keeps_first_n(self):
        evidence = [_ev(i) for i in range(1, 21)]
        out, stats = compact_evidence(evidence, cited_ids=None, keep_top=5)
        kept_ids = [e['evidence_id'] for e in out if e.get('evidence_id')]
        assert kept_ids == [f'ev-{i}' for i in range(1, 6)]
        assert stats['dropped'] == 15

    def test_cited_ids_never_dropped(self):
        evidence = [_ev(i) for i in range(1, 51)]
        cited = {'ev-7', 'ev-23', 'ev-49'}
        out, _ = compact_evidence(evidence, cited_ids=cited)
        kept_ids = {e['evidence_id'] for e in out}
        assert cited.issubset(kept_ids)

    def test_no_new_numbers_introduced(self):
        evidence = [_ev(i) for i in range(1, 8)]
        before_nums = set()
        for e in evidence:
            before_nums |= extract_numbers(e['quote'])
        out, _ = compact_evidence(evidence, cited_ids={'ev-1', 'ev-2'})
        after_nums = set()
        for e in out:
            after_nums |= extract_numbers(e.get('quote', ''))
        business_before = {n for n in before_nums if '.' in n}
        business_after = {n for n in after_nums if '.' in n}
        assert business_after.issubset(business_before)

    def test_source_url_preserved_for_kept(self):
        evidence = [_ev(1), _ev(2)]
        out, _ = compact_evidence(evidence, cited_ids={'ev-1'})
        kept = next((e for e in out if e.get('evidence_id') == 'ev-1'))
        assert kept['source_url'] == 'https://example.org/g/1'

    def test_empty_evidence(self):
        out, stats = compact_evidence([], cited_ids=set())
        assert out == [] and stats['before'] == 0

class TestObservationLayer:

    def test_same_name_same_value_merged(self):
        obs = [{'type': 'metric', 'metric_name': '血压', 'value': '120/80'}, {'type': 'metric', 'metric_name': '血压', 'value': '120/80'}, {'type': 'metric', 'metric_name': '血糖', 'value': '5.6'}]
        out, stats = compact_observations(obs)
        assert stats['merged'] == 1
        bp = [o for o in out if o.get('metric_name') == '血压']
        assert len(bp) == 1 and bp[0]['merged_count'] == 2

    def test_same_name_diff_value_kept_with_conflict(self):
        obs = [{'type': 'metric', 'metric_name': '血压', 'value': '120/80'}, {'type': 'metric', 'metric_name': '血压', 'value': '135/90'}]
        out, stats = compact_observations(obs)
        bp = [o for o in out if o.get('metric_name') == '血压']
        assert len(bp) == 2, '同名异值不得丢弃'
        assert all((o.get('conflict') for o in bp))
        assert stats['conflicts'] == 1

    def test_non_metric_passthrough(self):
        obs = [{'type': 'vlm_analysis', 'report_date': '2026-09-01'}]
        out, _ = compact_observations(obs)
        assert out == obs

class TestDiscussionLayer:

    def test_claims_slimmed_to_conclusion_and_ids(self):
        claims = [{'claim_id': 'c1', 'metric_code': 'LDL_C', 'type': 'fact', 'text': '低密度脂蛋白胆固醇 4.2 偏高', 'evidence_ids': ['ev-1'], 'reasoning_trace': '长长的推理过程……' * 100, 'debug': {'prompt': '...'}}]
        slim, _, stats = compact_discussion(claims, [])
        assert stats['claims_after'] == 1
        assert slim[0]['claim_id'] == 'c1'
        assert slim[0]['evidence_ids'] == ['ev-1']
        assert 'reasoning_trace' not in slim[0]
        assert 'debug' not in slim[0]
        assert '4.2' in slim[0]['text'], '结论中的数字原样保留'

    def test_errors_truncated_with_summary(self):
        errors = [{'error_code': 'E', 'message': f'err{i}', 'claim_id': ''} for i in range(25)]
        _, slim_errors, stats = compact_discussion([], errors, keep_errors=10)
        assert stats['errors_before'] == 25
        assert len(slim_errors) == 11
        assert slim_errors[0]['error_code'] == 'COMPACTION_SUMMARY'

class TestIntegration:

    def _big_state(self) -> dict:
        evidence = [_ev(i, quote=f'证据{i}：' + '中等强度有氧运动每周 150 分钟。' * 30) for i in range(1, 21)]
        return {'evidence': evidence, 'image_observations': [], 'validated_claims': [], 'errors': []}

    def test_compact_state_end_to_end(self):
        state = self._big_state()
        out, report = compact_state(state, trigger_tokens=100)
        assert report['triggered'] is True
        assert report['evidence']['dropped'] > 0
        assert len(state['evidence']) == 20

    def test_validator_existence_passes_after_compaction(self):
        from app.evidence.validator import validate_existence
        state = self._big_state()
        out, _ = compact_state(state, cited_ids={'ev-3', 'ev-8'}, trigger_tokens=100)
        registered = {str(e.get('evidence_id')) for e in out['evidence'] if e.get('evidence_id')}
        result = validate_existence('claim-1', ['ev-3', 'ev-8'], registered_ids=registered)
        assert not result.failures, f'压缩后引用必须仍可解析: {result.failures}'

    def test_draft_report_continues_after_compaction(self, monkeypatch):
        from app.agents import report_agent
        fake_json = '{"observation":"o","facts":"f [1]","inferences":"","conflicts":"","unknowns":"","related_to_you":"","metric_reading":"","metric_trend":"","exercise_advice":[{"text":"每周 150 分钟有氧 [1]","evidence_ids":["1"]}],"lifestyle_advice":[],"followup_advice":[]}'

        class _FakeLLM:

            def chat(self, **kwargs):
                return {'choices': [{'message': {'content': fake_json}}]}
        monkeypatch.setattr('app.gateway.adapters.llm.LLMAdapter', lambda: _FakeLLM())
        state = self._big_state()
        state.update({'parsed_metrics': [], 'metric_trends': [], 'user_profile': {}, 'validated_claims': [], 'errors': []})
        monkeypatch.setenv('COMPACTION_TRIGGER_TOKENS', '100')
        import importlib
        import app.context.compaction as comp
        importlib.reload(comp)
        try:
            out = report_agent._draft_report(dict(state))
        finally:
            monkeypatch.delenv('COMPACTION_TRIGGER_TOKENS', None)
            importlib.reload(comp)
        assert out.get('report_draft'), '压缩后报告生成不得中断'
        assert out['report_draft']['sections']['facts'] == 'f [1]'
        assert out.get('compaction_events'), '压缩事件必须写入 state 供 trace'
