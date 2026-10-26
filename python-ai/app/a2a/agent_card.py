from __future__ import annotations
import logging
import os
import threading
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4
logger = logging.getLogger(__name__)

def get_agent_card() -> dict:
    base = os.getenv('A2A_PUBLIC_BASE', 'http://localhost:9002').rstrip('/')
    return {'name': '个人健康顾问助手', 'description': '基于健康指南库与病历案例库（双库 RAG），对体检报告指标做逐项证据解读，并给出运动与生活方式建议。每条结论绑定引用来源，证据不足时拒答并引导补充体检材料。', 'version': '0.4.0', 'provider': {'name': 'LLMHealthyAssistant', 'url': 'https://github.com/niceoffer/llm-healthy-assistant'}, 'capabilities': {'streaming': False, 'push_notifications': False, 'state_transition_history': True}, 'skills': [{'id': 'health_consult', 'name': '健康咨询', 'description': '对体检报告图片或健康诉求文本做完整分析，产出带引用的指标解读、运动与生活方式建议。可通过 query（健康诉求）文本委托，或传 images 走视觉识别。', 'tags': ['health-rag', 'fitness-advice', 'multi-agent', 'medical-guidelines'], 'examples': ['帮我看看血脂高该怎么运动', 'LDL-C 偏高，想改善血脂，日常饮食和运动怎么安排？', '这份体检报告里的血糖指标是否异常，需要复查吗？'], 'inputModes': ['text', 'image', 'application/json'], 'outputModes': ['application/json']}], 'url': base, 'endpoints': {'agent_card': f'{base}/a2a/agent-card', 'submit_task': f'{base}/a2a/tasks', 'task_status': f'{base}/a2a/tasks/{{task_id}}', 'task_result': f'{base}/a2a/tasks/{{task_id}}/result', 'mcp': f'{base}/mcp'}, 'authentication': {'type': 'bearer', 'scopes': ['a2a:health_consult'], 'optional_dev': True, 'header': 'Authorization: Bearer <A2A_API_TOKEN>'}}
_task_store: dict[str, dict] = {}
_lock = threading.Lock()

def submit_task(*, images: list[dict] | None=None, query: str='', user_id: str='a2a-user') -> str:
    task_id = str(uuid4())
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        _task_store[task_id] = {'task_id': task_id, 'status': 'pending', 'images': images or [], 'query': query, 'user_id': user_id, 'created_at': now, 'updated_at': now, 'result': None, 'error': None}
    logger.info('[A2A] 任务提交 task_id=%s images=%d query=%r', task_id, len(images or []), query[:60])

    def _worker() -> None:
        with _lock:
            t = _task_store.get(task_id)
            if not t:
                return
            t['status'] = 'processing'
            t['updated_at'] = datetime.now(timezone.utc).isoformat()
        try:
            from app.a2a.runner import run_health_consult
            result = run_health_consult(images=images, query=query, user_id=user_id)
            status = result.get('status') or 'completed'
            with _lock:
                t = _task_store.get(task_id)
                if not t:
                    return
                t['status'] = status
                t['result'] = result
                t['updated_at'] = datetime.now(timezone.utc).isoformat()
                if status == 'failed':
                    t['error'] = result.get('error')
        except Exception as e:
            logger.error('[A2A] 任务执行异常 task_id=%s: %s', task_id, e, exc_info=True)
            with _lock:
                t = _task_store.get(task_id)
                if not t:
                    return
                t['status'] = 'failed'
                t['error'] = str(e)
                t['updated_at'] = datetime.now(timezone.utc).isoformat()
    threading.Thread(target=_worker, name=f'a2a-{task_id[:8]}', daemon=True).start()
    return task_id

def get_task_status(task_id: str) -> dict[str, Any]:
    with _lock:
        task = _task_store.get(task_id)
    if task is None:
        return {'task_id': task_id, 'status': 'not_found', 'error': 'Task not found'}
    return {'task_id': task['task_id'], 'status': task['status'], 'created_at': task.get('created_at'), 'updated_at': task.get('updated_at'), 'error': task.get('error'), 'has_result': task.get('result') is not None}

def get_task_result(task_id: str) -> dict[str, Any]:
    with _lock:
        task = _task_store.get(task_id)
    if task is None:
        return {'task_id': task_id, 'status': 'not_found'}
    status = task['status']
    if status in ('pending', 'processing'):
        return {'task_id': task_id, 'status': status, 'report': None, 'message': '任务处理中，请稍后轮询'}
    result = task.get('result') or {}
    return {'task_id': task_id, 'status': status, 'report': result, 'error': task.get('error')}
