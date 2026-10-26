from __future__ import annotations
import contextvars
import functools
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import grpc
from prometheus_client import Counter, Gauge, Histogram, start_http_server
from app.context import ctx as call_ctx

CORRELATION = contextvars.ContextVar('observation_correlation', default={})
WAIT = threading.local()
BUCKETS = (.001, .005, .01, .05, .1, .25, .5, 1, 2, 5, 10, 30, 60, 120, 300, 600)
STAGES = Histogram('lha_stage_seconds', 'Inclusive node/adapter duration; nested stages overlap', ['stage', 'outcome'], buckets=BUCKETS)
ACTIVE = Gauge('lha_grpc_active', 'Executing RPC handlers including streams', ['method'])
RPC = Histogram('lha_grpc_seconds', 'RPC handler lifetime', ['method', 'outcome'], buckets=BUCKETS)
QUEUED = Gauge('lha_executor_queued', 'Submitted work not yet started')
BUSY = Gauge('lha_executor_busy', 'Occupied gRPC worker threads')
WORKERS = Gauge('lha_executor_workers', 'Configured gRPC workers')
QUEUE = Histogram('lha_executor_queue_seconds', 'Actual executor submit-to-start wait', buckets=BUCKETS)
RPC_QUEUE = Histogram('lha_grpc_queue_seconds', 'Executor wait correlated to handler method', ['method'], buckets=BUCKETS)
TOKENS = Counter('lha_model_tokens', 'Reported token usage, or existing estimates for embedding/rerank', ['call_type', 'model'])
USAGE = Counter('lha_model_usage_records', 'Usage records (not batch item count)', ['call_type', 'model'])
ATTEMPTS = Counter('lha_model_attempts', 'Adapter invocations, including retries and failures', ['adapter', 'outcome'])
EVENTS = Counter('lha_stream_events', 'Yielded gRPC events', ['method', 'event'])
LOG = logging.getLogger('lha.observations')
LOG.propagate = False
LOG.setLevel(logging.INFO)


def configure_log():
    if LOG.handlers:
        return
    path = Path(os.getenv('LHA_OBSERVATION_LOG', '/home/ubuntu/RAG-job/线上测试部署/logs/task-events.jsonl'))
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(path, maxBytes=20 * 1024 * 1024, backupCount=10, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(message)s'))
    LOG.addHandler(handler)


def emit(event, **fields):
    # No prompts, image URLs, report contents, credentials, or exception messages.
    context = dict(CORRELATION.get())
    context.update(task_id=call_ctx.get_task_id() or context.get('task_id', ''),
                   trace_id=call_ctx.get_trace_id() or context.get('trace_id', ''))
    LOG.info(json.dumps({'ts': datetime.now(timezone.utc).isoformat(), 'event': event, **context, **fields}, ensure_ascii=False))


def timed(stage):
    def decorate(fn):
        @functools.wraps(fn)
        def wrapped(*args, **kwargs):
            state = args[0] if args and isinstance(args[0], dict) else {}
            context = {**CORRELATION.get(), **{k: state[k] for k in ('task_id', 'trace_id') if state.get(k)}}
            token = CORRELATION.set(context)
            start = time.monotonic()
            outcome, error_type = 'ok', ''
            result = None
            execution_id = uuid.uuid4().hex
            emit('stage_start', stage=stage, execution_id=execution_id)
            try:
                result = fn(*args, **kwargs)
                if result is None and stage == 'save_report':
                    outcome = 'failed_return'
                elif isinstance(result, dict) and result.get('error'):
                    outcome = 'failed_return'
                return result
            except BaseException as exc:
                error_type = type(exc).__name__
                outcome = 'interrupted' if error_type in ('GraphInterrupt', 'NodeInterrupt') else 'error'
                raise
            finally:
                duration = time.monotonic() - start
                STAGES.labels(stage, outcome).observe(duration)
                if stage.startswith('model.'):
                    ATTEMPTS.labels(stage[6:], outcome).inc()
                emit('stage_end', stage=stage, execution_id=execution_id, outcome=outcome, error_type=error_type, duration_ms=round(duration * 1000, 3),
                     business_status=result.get('status', '') if isinstance(result, dict) else '',
                     retry_count=result.get('retry_count', 0) if isinstance(result, dict) else 0,
                     citation_retry_count=result.get('citation_retry_count', 0) if isinstance(result, dict) else 0,
                     error_codes=[e.get('error_code', '') for e in result.get('errors', []) if isinstance(e, dict)] if isinstance(result, dict) else [],
                     report_id=result.get('id', '') if stage == 'save_report' and isinstance(result, dict) else '')
                CORRELATION.reset(token)
        return wrapped
    return decorate


def usage(call_type, model, total_tokens, latency_ms, call_count):
    TOKENS.labels(call_type, model).inc(max(0, total_tokens))
    USAGE.labels(call_type, model).inc()
    emit('model_usage', call_type=call_type, model=model, total_tokens=total_tokens,
         latency_ms=latency_ms, batch_items=call_count)


class ObservedExecutor(ThreadPoolExecutor):
    def __init__(self, max_workers=10):
        super().__init__(max_workers=max_workers, thread_name_prefix='lha-grpc')
        WORKERS.set(max_workers)

    def submit(self, fn, /, *args, **kwargs):
        submitted = time.monotonic()
        QUEUED.inc()
        lock = threading.Lock()
        released = False
        def release_queue():
            nonlocal released
            with lock:
                if not released:
                    QUEUED.dec()
                    released = True
        def work():
            release_queue()
            wait = time.monotonic() - submitted
            WAIT.seconds = wait
            QUEUE.observe(wait)
            BUSY.inc()
            try:
                # A fresh Context prevents data leaking between reused worker threads.
                return contextvars.Context().run(fn, *args, **kwargs)
            finally:
                BUSY.dec()
                WAIT.seconds = 0
        try:
            future = super().submit(work)
        except BaseException:
            release_queue()
            raise
        future.add_done_callback(lambda f: release_queue() if f.cancelled() else None)
        return future


class ObservationInterceptor(grpc.ServerInterceptor):
    def intercept_service(self, continuation, details):
        handler = continuation(details)
        if handler is None or handler.request_streaming:
            return handler
        method = details.method.rsplit('/', 1)[-1]
        metadata = dict(details.invocation_metadata or ())
        def begin(request):
            call_ctx.clear_context()
            task = getattr(request, 'task_id', '')
            trace = getattr(request, 'trace_id', '') or metadata.get('x-trace-id', '') or task
            run = metadata.get('x-run-id', '')[:100]
            token = CORRELATION.set({'task_id': task, 'trace_id': trace, 'run_id': run,
                                     'rpc_id': uuid.uuid4().hex, 'client_task_id': getattr(request, 'client_task_id', '')[:160]})
            call_ctx.set_context(task_id=task, trace_id=trace)
            wait = getattr(WAIT, 'seconds', 0)
            RPC_QUEUE.labels(method).observe(wait)
            ACTIVE.labels(method).inc()
            emit('rpc_start', method=method, queue_ms=round(wait * 1000, 3))
            return token, time.monotonic()
        def finish(token, started, context, error=''):
            outcome = error or (context.code().name if context.code() else 'OK')
            RPC.labels(method, outcome).observe(time.monotonic() - started)
            ACTIVE.labels(method).dec()
            emit('rpc_end', method=method, outcome=outcome, duration_ms=round((time.monotonic()-started)*1000, 3), client_active=context.is_active())
            call_ctx.clear_context()
            CORRELATION.reset(token)
        def unary(request, context):
            token, started = begin(request)
            error = ''
            try:
                return handler.unary_unary(request, context)
            except BaseException as exc:
                error = type(exc).__name__
                raise
            finally:
                finish(token, started, context, error)
        def stream(request, context):
            token, started = begin(request)
            error = ''
            try:
                for item in handler.unary_stream(request, context):
                    event = item.WhichOneof('payload') if 'payload' in item.DESCRIPTOR.oneofs_by_name else 'message'
                    EVENTS.labels(method, event or 'empty').inc()
                    if event in ('result', 'error'):
                        emit('stream_terminal', method=method, kind=event, seq=getattr(item, 'seq', 0),
                             status=getattr(getattr(item, 'result', None), 'status', ''),
                             error_code=getattr(getattr(item, 'error', None), 'error_code', ''))
                    yield item
            except BaseException as exc:
                error = type(exc).__name__
                raise
            finally:
                finish(token, started, context, error)
        factory = grpc.unary_stream_rpc_method_handler if handler.response_streaming else grpc.unary_unary_rpc_method_handler
        return factory(stream if handler.response_streaming else unary,
                       request_deserializer=handler.request_deserializer, response_serializer=handler.response_serializer)


def start():
    configure_log()
    start_http_server(int(os.getenv('LHA_PYTHON_METRICS_PORT', '9108')), addr='127.0.0.1')
