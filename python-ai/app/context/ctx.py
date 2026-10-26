from __future__ import annotations
from contextvars import ContextVar
_task_id: ContextVar[str] = ContextVar('ctx_task_id', default='')
_user_id: ContextVar[str] = ContextVar('ctx_user_id', default='')
_trace_id: ContextVar[str] = ContextVar('ctx_trace_id', default='')

def set_context(task_id: str='', user_id: str='', trace_id: str='') -> None:
    if task_id:
        _task_id.set(task_id)
    if user_id:
        _user_id.set(user_id)
    if trace_id:
        _trace_id.set(trace_id)

def get_task_id() -> str:
    return _task_id.get()

def get_user_id() -> str:
    return _user_id.get()

def get_trace_id() -> str:
    return _trace_id.get()

def clear_context() -> None:
    _task_id.set('')
    _user_id.set('')
    _trace_id.set('')
