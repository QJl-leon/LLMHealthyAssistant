from __future__ import annotations
import logging
import os
from typing import Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from app.context import ctx as call_ctx
logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://lha:lha_dev@localhost:5432/lha')
TASK_TOKEN_BUDGET = int(os.getenv('TASK_TOKEN_BUDGET', '100000'))
USER_DAILY_TOKEN_QUOTA = int(os.getenv('USER_DAILY_TOKEN_QUOTA', '1000000'))
COST_LIMIT_ENABLED = os.getenv('COST_LIMIT_ENABLED', 'true').lower() in ('1', 'true', 'yes')

class BudgetExceededError(Exception):
    pass

class QuotaExceededError(Exception):
    pass

def _conn():
    return psycopg2.connect(DATABASE_URL)

def init_cost_tables() -> None:
    sql = "\n    CREATE TABLE IF NOT EXISTS token_usage (\n        id                BIGSERIAL PRIMARY KEY,\n        task_id           TEXT NOT NULL DEFAULT '',\n        user_id           TEXT NOT NULL DEFAULT '',\n        trace_id          TEXT NOT NULL DEFAULT '',\n        call_type         TEXT NOT NULL,          -- llm / embedding / rerank / vlm / hyde\n        model             TEXT NOT NULL DEFAULT '',\n        prompt_tokens     INT NOT NULL DEFAULT 0,\n        completion_tokens INT NOT NULL DEFAULT 0,\n        total_tokens      INT NOT NULL DEFAULT 0,\n        call_count        INT NOT NULL DEFAULT 1,  -- 批量调用条数（embedding 一批 N 条）\n        latency_ms        INT NOT NULL DEFAULT 0,\n        created_at        TIMESTAMPTZ NOT NULL DEFAULT now()\n    );\n    CREATE INDEX IF NOT EXISTS idx_usage_task  ON token_usage (task_id);\n    CREATE INDEX IF NOT EXISTS idx_usage_user  ON token_usage (user_id, created_at DESC);\n    CREATE INDEX IF NOT EXISTS idx_usage_model ON token_usage (model, created_at DESC);\n    "
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    logger.info('[Cost] token_usage 表就绪')

def record_usage(call_type: str, model: str, *, prompt_tokens: int=0, completion_tokens: int=0, total_tokens: int=0, call_count: int=1, latency_ms: int=0) -> None:
    try:
        init_cost_tables()
    except Exception:
        pass
    total = total_tokens or prompt_tokens + completion_tokens
    from app.observability.runtime import usage
    usage(call_type, model, total, latency_ms, call_count)
    try:
        with _conn() as conn:
            with conn.cursor() as cur:
                cur.execute('INSERT INTO token_usage\n                       (task_id, user_id, trace_id, call_type, model,\n                        prompt_tokens, completion_tokens, total_tokens,\n                        call_count, latency_ms)\n                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)', (call_ctx.get_task_id(), call_ctx.get_user_id(), call_ctx.get_trace_id(), call_type, model, prompt_tokens, completion_tokens, total, call_count, latency_ms))
            conn.commit()
    except Exception as e:
        logger.warning('[Cost] token 落库失败（不阻塞主链路）: %s', e)

def _sum_tokens(where: str, params: tuple) -> int:
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(f'SELECT COALESCE(SUM(total_tokens), 0) FROM token_usage WHERE {where}', params)
            return int(cur.fetchone()[0])

def get_task_tokens(task_id: str) -> int:
    if not task_id:
        return 0
    try:
        return _sum_tokens('task_id = %s', (task_id,))
    except Exception as e:
        logger.warning('[Cost] 任务 token 查询失败: %s', e)
        return 0

def get_user_daily_tokens(user_id: str) -> int:
    if not user_id:
        return 0
    try:
        return _sum_tokens("user_id = %s AND created_at > now() - interval '1 day'", (user_id,))
    except Exception as e:
        logger.warning('[Cost] 用户 token 查询失败: %s', e)
        return 0

def check_limits(*, task_id: str='', user_id: str='', estimated_tokens: int=0) -> None:
    if not COST_LIMIT_ENABLED:
        return
    task_id = task_id or call_ctx.get_task_id()
    user_id = user_id or call_ctx.get_user_id()
    if user_id:
        used_daily = get_user_daily_tokens(user_id)
        if used_daily + estimated_tokens > USER_DAILY_TOKEN_QUOTA:
            raise QuotaExceededError(f'用户日配额超限: {used_daily}+{estimated_tokens} > {USER_DAILY_TOKEN_QUOTA}')
    if task_id:
        used_task = get_task_tokens(task_id)
        if used_task + estimated_tokens > TASK_TOKEN_BUDGET:
            raise BudgetExceededError(f'任务 token 预算超限: {used_task}+{estimated_tokens} > {TASK_TOKEN_BUDGET}')

def get_task_cost(task_id: str) -> dict[str, Any]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT call_type, model,\n                          COUNT(*) AS calls,\n                          SUM(total_tokens) AS tokens,\n                          SUM(prompt_tokens) AS prompt_tokens,\n                          SUM(completion_tokens) AS completion_tokens,\n                          AVG(latency_ms)::int AS avg_latency_ms\n                   FROM token_usage WHERE task_id = %s\n                   GROUP BY call_type, model ORDER BY tokens DESC', (task_id,))
            items = [dict(r) for r in cur.fetchall()]
    total = sum((int(i['tokens']) for i in items))
    return {'task_id': task_id, 'total_tokens': total, 'call_count': sum((int(i['calls']) for i in items)), 'items': items}

def get_user_cost(user_id: str, days: int=7) -> dict[str, Any]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT date_trunc('day', created_at) AS day, call_type,\n                          COUNT(*) AS calls, SUM(total_tokens) AS tokens\n                   FROM token_usage\n                   WHERE user_id = %s AND created_at > now() - make_interval(days => %s)\n                   GROUP BY 1, 2 ORDER BY 1 DESC, tokens DESC", (user_id, days))
            items = [dict(r) for r in cur.fetchall()]
    return {'user_id': user_id, 'days': days, 'items': items, 'total_tokens': sum((int(i['tokens']) for i in items))}

def get_model_summary(days: int=7) -> dict[str, Any]:
    with _conn() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute('SELECT model, call_type, COUNT(*) AS calls,\n                          SUM(total_tokens) AS tokens,\n                          AVG(latency_ms)::int AS avg_latency_ms\n                   FROM token_usage\n                   WHERE created_at > now() - make_interval(days => %s)\n                   GROUP BY model, call_type ORDER BY tokens DESC', (days,))
            items = [dict(r) for r in cur.fetchall()]
    return {'days': days, 'items': items, 'total_tokens': sum((int(i['tokens']) for i in items))}
