from __future__ import annotations
import logging
import os
from typing import Any
logger = logging.getLogger(__name__)
_pool: Any = None
_saver: Any = None

def get_checkpointer():
    global _pool, _saver
    if _saver is not None:
        return _saver
    backend = (os.getenv('CHECKPOINT_BACKEND') or 'postgres').strip().lower()
    if backend in ('memory', 'mem', 'memorysaver'):
        _saver = _memory_saver()
        return _saver
    try:
        _saver = _postgres_saver()
        return _saver
    except Exception as e:
        logger.warning('⚠️ PostgresSaver 不可用，回落 MemorySaver: %s', e)
        _saver = _memory_saver()
        return _saver

def _memory_saver():
    from langgraph.checkpoint.memory import MemorySaver
    logger.info('✅ Checkpointer: MemorySaver（进程内 HITL，重启不可恢复）')
    return MemorySaver()

def _postgres_saver():
    global _pool
    from psycopg.rows import dict_row
    from psycopg_pool import ConnectionPool
    from langgraph.checkpoint.postgres import PostgresSaver
    db_url = os.getenv('DATABASE_URL', 'postgresql://lha:lha_dev@localhost:5432/lha?sslmode=disable')
    _pool = ConnectionPool(conninfo=db_url, min_size=1, max_size=8, kwargs={'autocommit': True, 'prepare_threshold': 0, 'row_factory': dict_row}, open=True)
    saver = PostgresSaver(_pool)
    saver.setup()
    logger.info('✅ Checkpointer: PostgresSaver（DATABASE_URL 持久化 HITL）')
    return saver

def close_checkpointer() -> None:
    global _pool, _saver
    if _pool is not None:
        try:
            _pool.close()
        except Exception as e:
            logger.warning('关闭 checkpointer pool 失败: %s', e)
    _pool = None
    _saver = None
