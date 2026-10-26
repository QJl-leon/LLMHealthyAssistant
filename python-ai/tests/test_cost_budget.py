from __future__ import annotations
import os
import pytest
from app.context import cost as cost_mod
from app.context import ctx as call_ctx
from app.context.budget import EvidenceBudget, allocate_evidence_budget, build_evidence_text_with_budget
from app.context.cost import BudgetExceededError, QuotaExceededError

@pytest.fixture(autouse=True)
def _clean_ctx():
    call_ctx.clear_context()
    yield
    call_ctx.clear_context()

class TestLimits:

    def test_task_budget_exceeded(self, monkeypatch):
        monkeypatch.setattr(cost_mod, 'get_task_tokens', lambda tid: 99990)
        monkeypatch.setattr(cost_mod, 'get_user_daily_tokens', lambda uid: 0)
        monkeypatch.setattr(cost_mod, 'TASK_TOKEN_BUDGET', 100000)
        monkeypatch.setattr(cost_mod, 'COST_LIMIT_ENABLED', True)
        with pytest.raises(BudgetExceededError, match='任务 token 预算超限'):
            cost_mod.check_limits(task_id='t1', estimated_tokens=100)

    def test_task_budget_within_limit(self, monkeypatch):
        monkeypatch.setattr(cost_mod, 'get_task_tokens', lambda tid: 1000)
        monkeypatch.setattr(cost_mod, 'get_user_daily_tokens', lambda uid: 0)
        monkeypatch.setattr(cost_mod, 'TASK_TOKEN_BUDGET', 100000)
        monkeypatch.setattr(cost_mod, 'COST_LIMIT_ENABLED', True)
        cost_mod.check_limits(task_id='t1', estimated_tokens=5000)

    def test_user_quota_exceeded(self, monkeypatch):
        monkeypatch.setattr(cost_mod, 'get_task_tokens', lambda tid: 0)
        monkeypatch.setattr(cost_mod, 'get_user_daily_tokens', lambda uid: 1000000)
        monkeypatch.setattr(cost_mod, 'USER_DAILY_TOKEN_QUOTA', 1000000)
        monkeypatch.setattr(cost_mod, 'COST_LIMIT_ENABLED', True)
        with pytest.raises(QuotaExceededError, match='用户日配额超限'):
            cost_mod.check_limits(user_id='u1', estimated_tokens=1)

    def test_user_quota_checked_before_task_budget(self, monkeypatch):
        monkeypatch.setattr(cost_mod, 'get_task_tokens', lambda tid: 999999)
        monkeypatch.setattr(cost_mod, 'get_user_daily_tokens', lambda uid: 9999999)
        monkeypatch.setattr(cost_mod, 'COST_LIMIT_ENABLED', True)
        monkeypatch.setattr(cost_mod, 'USER_DAILY_TOKEN_QUOTA', 1000000)
        with pytest.raises(QuotaExceededError):
            cost_mod.check_limits(task_id='t1', user_id='u1', estimated_tokens=1)

    def test_limits_disabled(self, monkeypatch):
        monkeypatch.setattr(cost_mod, 'COST_LIMIT_ENABLED', False)
        monkeypatch.setattr(cost_mod, 'get_task_tokens', lambda tid: 10 ** 9)
        monkeypatch.setattr(cost_mod, 'get_user_daily_tokens', lambda uid: 10 ** 9)
        cost_mod.check_limits(task_id='t1', user_id='u1', estimated_tokens=1)

    def test_contextvars_provide_task_and_user(self, monkeypatch):
        call_ctx.set_context(task_id='ctx-task', user_id='ctx-user')
        seen = {}

        def _fake_task_tokens(tid):
            seen['task'] = tid
            return 0

        def _fake_user_tokens(uid):
            seen['user'] = uid
            return 0
        monkeypatch.setattr(cost_mod, 'get_task_tokens', _fake_task_tokens)
        monkeypatch.setattr(cost_mod, 'get_user_daily_tokens', _fake_user_tokens)
        monkeypatch.setattr(cost_mod, 'COST_LIMIT_ENABLED', True)
        cost_mod.check_limits()
        assert seen['task'] == 'ctx-task' and seen['user'] == 'ctx-user'

class TestDynamicBudget:

    def test_budget_scales_with_window(self):
        small = allocate_evidence_budget(system_prompt_tokens=2000, metrics_tokens=1000, trend_tokens=500, profile_tokens=300, evidence_count=50, model_window=16000)
        large = allocate_evidence_budget(system_prompt_tokens=2000, metrics_tokens=1000, trend_tokens=500, profile_tokens=300, evidence_count=50, model_window=64000)
        assert large.total_tokens > small.total_tokens
        assert large.max_items >= small.max_items

    def test_budget_zero_when_no_room(self):
        b = allocate_evidence_budget(system_prompt_tokens=60000, metrics_tokens=5000, trend_tokens=0, profile_tokens=0, evidence_count=10, model_window=64000, output_reserve=4096)
        assert b.max_items == 0

    def test_per_item_chars_relaxed_when_budget_ample(self):
        b = allocate_evidence_budget(system_prompt_tokens=1000, metrics_tokens=500, trend_tokens=200, profile_tokens=200, evidence_count=5, model_window=64000)
        assert b.per_item_chars > 200, '预算宽裕时单条应放宽'
        assert b.max_items >= 5

    def test_no_hardcoded_20_items(self):
        b = allocate_evidence_budget(system_prompt_tokens=2000, metrics_tokens=1000, trend_tokens=500, profile_tokens=300, evidence_count=100, model_window=128000)
        assert b.max_items > 20, '大窗口下证据条数应突破写死的 20'

    def test_build_text_respects_budget_and_keeps_ids(self):
        evidence = [{'evidence_id': f'ev-{i}', 'quote': '内容' * 500, 'source_name': f'来源{i}', 'source_url': f'https://x/{i}'} for i in range(1, 6)]
        budget = EvidenceBudget(total_tokens=1000, max_items=3, per_item_chars=50, reason='test')
        text = build_evidence_text_with_budget(evidence, budget)
        lines = [l for l in text.splitlines() if l.startswith('- [')]
        assert len(lines) == 3, '条数受预算限制'
        for i, line in enumerate(lines, start=1):
            assert f'编号: ev-{i}' in line, 'evidence_id 必须保留'
            assert f'URL: https://x/{i}' in line, 'source_url 必须保留'
            quote_part = line.split('|')[0]
            assert len(quote_part) <= 60

class TestReportAgentLimitDegradation:

    def _state(self):
        return {'evidence': [{'evidence_id': 'ev-1', 'quote': '每周 150 分钟运动', 'source_name': '指南', 'source_url': 'https://x/1'}], 'validated_claims': [], 'parsed_metrics': [], 'metric_trends': [], 'user_profile': {}, 'errors': []}

    def test_budget_exceeded_falls_back(self, monkeypatch):
        from app.agents import report_agent

        class _FakeLLM:

            def chat(self, **kw):
                raise BudgetExceededError('任务 token 预算超限: 100000 > 100000')
        monkeypatch.setattr('app.gateway.adapters.llm.LLMAdapter', lambda: _FakeLLM())
        out = report_agent._draft_report(self._state())
        sections = out['report_draft']['sections']
        assert not sections['exercise_advice'], '预算超限不得生成建议'
        assert not out['report_draft']['advice_claims'], '预算超限不得有建议 claim'
        assert any((e.get('error_code') == 'BUDGET_EXCEEDED' for e in out['errors']))

    def test_quota_exceeded_raises(self, monkeypatch):
        from app.agents import report_agent

        class _FakeLLM:

            def chat(self, **kw):
                raise QuotaExceededError('用户日配额超限')
        monkeypatch.setattr('app.gateway.adapters.llm.LLMAdapter', lambda: _FakeLLM())
        with pytest.raises(QuotaExceededError):
            report_agent._draft_report(self._state())

def _db_available() -> bool:
    try:
        import psycopg2
        conn = psycopg2.connect(cost_mod.DATABASE_URL, connect_timeout=2)
        conn.close()
        return True
    except Exception:
        return False
_DB_SKIP = pytest.mark.skipif(not _db_available(), reason='数据库不可用，跳过集成用例')

@_DB_SKIP
class TestCostRecordingRealDb:

    @pytest.fixture(autouse=True)
    def _setup_teardown(self):
        import psycopg2
        cost_mod.init_cost_tables()
        yield
        with psycopg2.connect(cost_mod.DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM token_usage WHERE task_id LIKE 'cost-test-%'")
            conn.commit()

    def test_record_and_aggregate(self):
        call_ctx.set_context(task_id='cost-test-t1', user_id='cost-test-u1', trace_id='trace-1')
        cost_mod.record_usage('llm', 'deepseek-chat', prompt_tokens=800, completion_tokens=200, latency_ms=1200)
        cost_mod.record_usage('embedding', 'bge-m3', total_tokens=150, call_count=5, latency_ms=300)
        cost_mod.record_usage('rerank', 'bge-reranker-v2-m3', total_tokens=900, call_count=10, latency_ms=450)
        task = cost_mod.get_task_cost('cost-test-t1')
        assert task['total_tokens'] == 800 + 200 + 150 + 900
        assert task['call_count'] == 3
        types = {i['call_type'] for i in task['items']}
        assert types == {'llm', 'embedding', 'rerank'}
        user = cost_mod.get_user_cost('cost-test-u1', days=1)
        assert user['total_tokens'] == task['total_tokens']
        models = cost_mod.get_model_summary(days=1)
        model_names = {i['model'] for i in models['items']}
        assert 'deepseek-chat' in model_names

    def test_limit_uses_real_db_totals(self):
        call_ctx.set_context(task_id='cost-test-t2', user_id='cost-test-u2')
        cost_mod.record_usage('llm', 'deepseek-chat', total_tokens=99950)
        import app.context.cost as cm
        old_budget = cm.TASK_TOKEN_BUDGET
        old_enabled = cm.COST_LIMIT_ENABLED
        cm.TASK_TOKEN_BUDGET = 100000
        cm.COST_LIMIT_ENABLED = True
        try:
            with pytest.raises(BudgetExceededError):
                cm.check_limits(task_id='cost-test-t2', estimated_tokens=100)
        finally:
            cm.TASK_TOKEN_BUDGET = old_budget
            cm.COST_LIMIT_ENABLED = old_enabled
