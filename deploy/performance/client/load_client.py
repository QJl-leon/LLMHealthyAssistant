#!/usr/bin/env python3
"""Remote HTTPS/SSE load client. No server/model credentials are needed."""
import argparse
import asyncio
from collections import Counter, deque
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import platform
from pathlib import Path
import random
import re
import struct
import time
from urllib.parse import urlparse
import zlib

from dotenv import dotenv_values
import httpx
import psutil

PRODUCTION_HOSTS = {'www.smproject.site', 'smproject.site'}


def tiny_png():
    def chunk(kind, data):
        return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data) & 0xffffffff)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', 1, 1, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(b'\0\x80\x80\x80')) + chunk(b'IEND', b''))


def validate(config, base, readiness=None):
    parsed = urlparse(base)
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/'):
        raise ValueError('Base URL must be an origin without credentials/query/path')
    if parsed.scheme != 'https' and parsed.hostname not in ('127.0.0.1', 'localhost'):
        raise ValueError('Remote target requires HTTPS')
    mode = config['mode']
    if mode not in ('smoke', 'single_report', 'bounded_concurrency', 'closed', 'arrival'):
        raise ValueError('Unknown load mode')
    for key in ['duration_seconds', 'max_tasks', 'task_timeout_seconds', 'max_inflight', 'max_total_tokens']:
        if not isinstance(config.get(key), (int, float)) or not math.isfinite(config[key]) or config[key] <= 0:
            raise ValueError('Positive finite setting required: ' + key)
    for key in ['max_tasks', 'max_inflight']:
        if not isinstance(config[key], int):
            raise ValueError('Integer required: ' + key)
    if config['max_tasks'] > 10000 or config['max_inflight'] > 32 or config['duration_seconds'] > 28800:
        raise ValueError('Task/inflight/duration limit exceeded')
    if mode in ('smoke', 'single_report', 'bounded_concurrency', 'closed'):
        concurrency = config.get('concurrency', 1)
        if not isinstance(concurrency, int) or not 1 <= concurrency <= config['max_inflight']:
            raise ValueError('Invalid concurrency')
    if mode == 'arrival' and (not math.isfinite(config.get('arrival_per_minute', 0)) or config.get('arrival_per_minute', 0) <= 0):
        raise ValueError('Positive arrival rate required')
    if mode == 'smoke':
        if config['max_tasks'] != 1 or config['max_inflight'] != 1 or config.get('concurrency') != 1:
            raise ValueError('Smoke only permits one task')
        return
    if mode == 'single_report':
        if (config['max_tasks'] != 1 or config['max_inflight'] != 1 or config.get('concurrency') != 1
                or config['task_timeout_seconds'] > 300 or config['duration_seconds'] > 600
                or config['max_total_tokens'] > 30000
                or config.get('duplicate_create') or config.get('disconnect_after_events')
                or config.get('slow_read_ms') or config.get('sse_reconnects',0)):
            raise ValueError('Single report requires one bounded task and no fault/reconnect scenarios')
        if (not readiness or not readiness.get('ready_for_single_report')
                or readiness.get('base_url','').rstrip('/') != base.rstrip('/')
                or not 0 <= time.time()-readiness.get('checked_unix',0) <= 600):
            raise ValueError('Fresh matching single-report readiness is required')
        if config.get('required_vlm_model') and readiness.get('configured_vlm_model')!=config['required_vlm_model']:
            raise ValueError('Configured VLM differs from the pinned baseline model')
        return
    if mode == 'bounded_concurrency':
        batch_tasks=config.get('concurrency')
        if (config.get('environment')!='production' or parsed.hostname not in PRODUCTION_HOSTS
                or batch_tasks not in (2,3,4,6,8) or config['max_tasks']!=batch_tasks or config['max_inflight']!=batch_tasks
                or config['task_timeout_seconds']>300 or config['duration_seconds']>600
                or config['max_total_tokens']>30000*batch_tasks or config.get('duplicate_create')
                or config.get('disconnect_after_events') or config.get('slow_read_ms')
                or config.get('sse_reconnects',0) or config.get('required_vlm_model')!='qwen3-vl-plus'):
            raise ValueError('Bounded concurrency permits one fixed batch of 2, 3, 4, 6, or 8 tasks, no faults, and pinned model')
        if (not readiness or not readiness.get('ready_for_single_report')
                or not readiness.get('checks',{}).get('real_report_chain_verified')
                or readiness.get('base_url','').rstrip('/')!=base.rstrip('/')
                or not 0 <= time.time()-readiness.get('checked_unix',0) <= 600
                or readiness.get('configured_vlm_model')!='qwen3-vl-plus'
                or not readiness.get('bounded_concurrency_authorization',{}).get('reserved_run_id')):
            raise ValueError('Fresh server campaign reservation and readiness are required')
        authorization=readiness['bounded_concurrency_authorization']
        if batch_tasks>2 and (authorization.get('campaign') not in ({3:('mac_c34_20261019',),4:('mac_c34_20261019',),6:('mac_c68_20261019','mac_c6diag_20261019'),8:('mac_c68_20261019',)}.get(batch_tasks,()))
                             or authorization.get('max_batch_tasks')!=batch_tasks
                             or authorization.get('max_concurrency')!=batch_tasks):
            raise ValueError('Step campaign reservation must match task count and concurrency')
        return
    if config.get('environment') != 'isolated' or parsed.hostname in PRODUCTION_HOSTS:
        raise ValueError('Load requires an isolated target; production is smoke-only')
    if not readiness or not readiness.get('ready_for_load') or readiness.get('base_url', '').rstrip('/') != base.rstrip('/'):
        raise ValueError('A matching successful server readiness report is required')
    if not 0 <= time.time() - readiness['checked_unix'] <= 3600:
        raise ValueError('Readiness report is stale; refresh within one hour')


async def sse_events(lines):
    data, event_id, event_name = [], '', ''
    async for line in lines:
        if line == '':
            if data:
                yield {'id': event_id, 'event': event_name, 'data': json.loads('\n'.join(data))}
            data, event_id, event_name = [], '', ''
        elif line.startswith('data:'):
            data.append(line[5:].lstrip(' '))
        elif line.startswith('id:'):
            event_id = line[3:].strip()
        elif line.startswith('event:'):
            event_name = line[6:].strip()
    if data:
        yield {'id': event_id, 'event': event_name, 'data': json.loads('\n'.join(data))}


def percentile(values, q):
    if not values:
        return None
    values = sorted(values)
    return values[max(0, math.ceil(len(values) * q) - 1)]


class LoadClient:
    def __init__(self, config, credentials, out, run_id, thresholds, samples=None, transport=None):
        self.config, self.credentials, self.out, self.run_id = config, credentials, out, run_id
        self.thresholds = thresholds
        self.base = credentials['RAG_BASE_URL'].rstrip('/')
        self.token = ''
        self.stop = asyncio.Event()
        self.metrics_ready = asyncio.Event()
        self.stop_reasons = []
        self.rows = []
        self.tokens = 0
        self.failures = deque(maxlen=thresholds['error_window_size'])
        self.consecutive = 0
        self.samples = samples or [{'name': 'synthetic_quality_gate', 'expected': 'awaiting_images',
                                    'images': [{'path': 'synthetic:1x1', 'position': 'lab_sheet'}]}]
        self.http = httpx.AsyncClient(base_url=self.base, transport=transport, follow_redirects=False,
                                      timeout=httpx.Timeout(30, read=60),
                                      limits=httpx.Limits(max_connections=config['max_inflight'] * 4 + 4))
        self.log = (out / 'client-events.jsonl').open('x')
        self.result_log = (out / 'tasks.jsonl').open('x')
        self.process = psutil.Process()
        self.started_monotonic = time.monotonic()

    def event(self, name, **fields):
        self.log.write(json.dumps({'ts': datetime.now(timezone.utc).isoformat(), 'event': name,
                                   'run_id': self.run_id, **fields}, ensure_ascii=False) + '\n')
        self.log.flush()

    def halt(self, reason):
        if reason not in self.stop_reasons:
            self.stop_reasons.append(reason)
            self.event('stop_new_tasks', reason=reason)
        self.stop.set()

    def headers(self, trace):
        headers = {'X-Run-Id': self.run_id, 'X-Trace-Id': trace}
        if self.token:
            headers['Authorization'] = 'Bearer ' + self.token
        return headers

    async def request(self, method, path, trace, **kwargs):
        response = await self.http.request(method, path, headers=self.headers(trace), **kwargs)
        response.raise_for_status()
        body = response.json()
        if body.get('code') != 0:
            raise RuntimeError('Business request rejected')
        return body.get('data') or {}

    async def login(self):
        data = await self.request('POST', '/api/v1/auth/login', self.run_id + '-login', json={
            'email': self.credentials['RAG_TEST_EMAIL'], 'password': self.credentials['RAG_TEST_PASSWORD'],
            'tenant_id': self.credentials['RAG_TEST_TENANT_ID']})
        self.token = data['access_token']

    async def upload(self, images, trace):
        uploaded = []
        for image in images:
            data = tiny_png() if image['path'] == 'synthetic:1x1' else Path(image['path']).read_bytes()
            name = 'quality-gate.png' if image['path'] == 'synthetic:1x1' else Path(image['path']).name
            item = await self.request('POST', '/api/v1/uploads', trace,
                                      files={'file': (name, data, 'application/octet-stream')},
                                      data={'position': image.get('position', 'lab_sheet')})
            uploaded.append({'key': item['image_key'], 'position': image.get('position', 'lab_sheet')})
        return uploaded

    async def stream_result(self, task, trace, row, start, fault, last_id=''):
        reconnects = 0
        while True:
            headers = self.headers(trace)
            if last_id:
                headers['Last-Event-ID'] = last_id
            try:
                async with self.http.stream('GET', f'/api/v1/tasks/{task}/events', headers=headers) as stream:
                    stream.raise_for_status()
                    if 'text/event-stream' not in stream.headers.get('content-type', ''):
                        raise RuntimeError('Expected SSE')
                    seen = 0
                    async for event in sse_events(stream.aiter_lines()):
                        if self.config.get('slow_read_ms', 0):
                            await asyncio.sleep(self.config['slow_read_ms'] / 1000)
                        seen += 1
                        if event['id']:
                            last_id = event['id']
                        obj = event['data']
                        row.setdefault('first_business_event_seconds', time.monotonic() - start)
                        delta = obj.get('reportDelta', obj.get('report_delta', {}))
                        if delta.get('content'):
                            row.setdefault('first_content_seconds', time.monotonic() - start)
                        self.event('sse_event', task_id=task, trace_id=trace, seq=last_id,
                                   payload_types=[k for k in obj if k not in ('taskId', 'task_id', 'traceId', 'trace_id', 'seq')],
                                   at_seconds=time.monotonic() - start)
                        if event['event'] == 'error' or 'error' in obj:
                            raise RuntimeError('SSE error event')
                        if obj.get('result'):
                            return obj['result']
                        if self.config.get('disconnect_after_events', 0) and not fault[0] and seen >= self.config['disconnect_after_events']:
                            fault[0] = True
                            self.event('client_disconnect', task_id=task, seq=last_id)
                            break
                    else:
                        self.event('sse_eof_without_result', task_id=task)
            except (httpx.TransportError, httpx.TimeoutException) as exc:
                self.event('sse_transport_error', task_id=task, error=type(exc).__name__)
            if reconnects >= self.config.get('sse_reconnects', 0):
                raise RuntimeError('SSE ended without terminal result')
            reconnects += 1
            row['sse_reconnects'] = row.get('sse_reconnects', 0) + 1
            await asyncio.sleep(0.5)

    async def report_readable(self, task, trace):
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            versions = await self.request('GET', f'/api/v1/reports/task/{task}/versions', trace)
            items = versions.get('items', [])
            for item in sorted(items, key=lambda r: r.get('version', 0), reverse=True):
                report = await self.request('GET', '/api/v1/reports/' + item['id'], trace)
                if report.get('task_id') == task and report.get('status') in ('published', 'refused'):
                    return report['id'], len(items), {'saved_status':report['status'], 'metrics_count':len(report.get('metrics') or []), 'nonempty_sections':sum(bool(str(v).strip()) for v in (report.get('sections') or {}).values())}
            await asyncio.sleep(0.5)
        raise RuntimeError('Terminal result has no readable saved report')

    async def one(self, number):
        sample = random.choices(self.samples, weights=[s.get('weight', 1) for s in self.samples])[0]
        trace = f'{self.run_id}-{number}'
        row = {'run_id': self.run_id, 'trace_id': trace, 'client_task_id': trace,
               'sample': sample['name'], 'expected': sample.get('expected', 'published'),
               'started_unix': time.time(), 'success': False, 'unresolved': False}
        start = time.monotonic()
        row['started_run_seconds'] = start-self.started_monotonic
        try:
            async with asyncio.timeout(self.config['task_timeout_seconds']):
                images = await self.upload(sample['images'], trace)
                row['upload_seconds'] = time.monotonic() - start
                payload = {'client_task_id': trace, 'images': images, 'institution': 'DEIDENTIFIED_PERFORMANCE_TEST'}
                row['create_attempted'] = True
                create_started = time.monotonic()
                if self.config.get('duplicate_create'):
                    created = await asyncio.gather(*[self.request('POST', '/api/v1/tasks', trace, json=payload) for _ in range(2)])
                    if created[0]['task_id'] != created[1]['task_id']:
                        raise RuntimeError('Concurrent idempotency violation')
                    first = created[0]
                    row['duplicate_create_reused_task'] = True
                else:
                    first = await self.request('POST', '/api/v1/tasks', trace, json=payload)
                row['create_api_seconds'] = time.monotonic() - create_started
                task = row['task_id'] = first['task_id']
                row['created_seconds'] = time.monotonic() - start
                added, confirmations, fault = False, 0, [False]
                for _ in range(self.config.get('max_transitions', 4)):
                    result = await self.stream_result(task, trace, row, start, fault)
                    status = result.get('status', '')
                    row['status'] = status
                    self.event('task_state', task_id=task, status=status)
                    if status == 'awaiting_images' and sample.get('new_images') and not added:
                        new_images = await self.upload(sample['new_images'], trace)
                        await self.request('POST', f'/api/v1/tasks/{task}/resume', trace,
                                           json={'action': 'add_images', 'new_images': new_images})
                        added = True
                    elif status == 'awaiting_publish_confirm' and self.config.get('auto_confirm_publish') and confirmations < self.config.get('max_publish_confirmations', 1):
                        await self.request('POST', f'/api/v1/tasks/{task}/resume', trace, json={'action': 'confirm_publish'})
                        confirmations += 1
                    else:
                        break
                row['terminal_event_seconds'] = time.monotonic() - start
                if row['status'] in ('published', 'refused'):
                    row['report_id'], row['report_versions'], saved = await self.report_readable(task, trace)
                    row.update(saved)
                    if saved['saved_status'] != row['status']:
                        raise RuntimeError('SSE and saved report status differ')
                    if self.config['mode'] in ('single_report','bounded_concurrency') and (saved['metrics_count']==0 or saved['nonempty_sections']==0):
                        raise RuntimeError('Saved report is incomplete')
                    row['report_readable_seconds'] = time.monotonic() - start
                    row['create_to_report_seconds'] = row['report_readable_seconds'] - row['created_seconds']
                elif row['status'].startswith('awaiting'):
                    row['waiting_for_input'] = True
                else:
                    row['unresolved'] = True
                row['success'] = row['status'] == row['expected'] and not row['unresolved']
                if row.get('waiting_for_input') and not row['success']:
                    self.halt('unexpected_human_input_required')
                try:
                    cost = await self.request('GET', f'/api/v1/tasks/{task}/cost', trace)
                    row['total_tokens'] = cost.get('total_tokens', 0)
                    row['model_call_count'] = cost.get('call_count', 0)
                    self.tokens += row['total_tokens']
                    if self.config['mode'] in ('single_report','bounded_concurrency') and (row['model_call_count']<=0 or row['total_tokens']<=0):
                        row['success']=False
                        self.halt('real_model_usage_not_observed')
                    if self.config['mode'] == 'smoke' and row['model_call_count'] != 0:
                        row['success'] = False
                        self.halt('smoke_unexpected_model_call')
                except Exception as exc:
                    row['cost_error'] = type(exc).__name__
                    self.halt('cost_visibility_lost')
        except Exception as exc:
            row['error_type'] = type(exc).__name__
            if isinstance(exc, httpx.HTTPStatusError):
                row['http_status'] = exc.response.status_code
            # Failed/unknown creation and incomplete streams may keep running server-side.
            row['unresolved'] = row.get('create_attempted', False) and row.get('status') not in ('published', 'refused', 'awaiting_images', 'awaiting_memory_confirm', 'awaiting_publish_confirm')
            if row['unresolved']:
                self.halt('unresolved_task_requires_server_check')
        row['elapsed_seconds'] = time.monotonic() - start
        self.rows.append(row)
        self.result_log.write(json.dumps(row, ensure_ascii=False) + '\n')
        self.result_log.flush()
        failed = not row['success']
        self.consecutive = self.consecutive + 1 if failed else 0
        self.failures.append(failed)
        if failed and self.config['mode']=='bounded_concurrency':
            self.halt('bounded_task_failed')
        if self.consecutive >= self.thresholds['consecutive_failures']:
            self.halt('consecutive_failures')
        if len(self.failures) >= self.thresholds['error_window_size'] and sum(self.failures) / len(self.failures) > self.thresholds['error_rate_max']:
            self.halt('rolling_failure_rate')
        if self.tokens >= self.config['max_total_tokens']:
            self.halt('observed_token_budget')
        return row

    async def monitor(self):
        base = self.credentials.get('RAG_PROMETHEUS_URL', '')
        held = {}
        queue_history = deque()
        restarts = {}
        self.process.cpu_percent()
        async with httpx.AsyncClient(timeout=10) as http:
            while not self.stop.is_set():
                now = time.monotonic()
                try:
                    self.event('client_resource', cpu_percent=self.process.cpu_percent(), rss_bytes=self.process.memory_info().rss,
                               threads=self.process.num_threads(), connections=len(self.process.net_connections(kind='tcp')))
                except (psutil.AccessDenied, NotImplementedError):
                    self.event('client_resource', rss_bytes=self.process.memory_info().rss, connections_unavailable=True)
                try:
                    response = await http.get(base.rstrip('/') + '/api/v1/query', params={'query': '{__name__=~"lha_host_memory_available_bytes|lha_host_disk_free_bytes|lha_host_cpu_percent|lha_executor_queued|lha_container_state|lha_dependency_up|up"}'})
                    response.raise_for_status()
                    body = response.json()
                    if body.get('status') != 'success' or not body['data']['result']:
                        raise RuntimeError('No metrics')
                    values = body['data']['result']
                    held.pop('metrics_unavailable', None)
                    metrics = {}
                    for item in values:
                        metrics.setdefault(item['metric']['__name__'], []).append(float(item['value'][1]))
                    for required in ['lha_host_memory_available_bytes', 'lha_host_disk_free_bytes', 'lha_host_cpu_percent', 'lha_executor_queued', 'lha_container_state', 'lha_dependency_up', 'up']:
                        if required not in metrics:
                            raise RuntimeError('Missing guard metric')
                    queue = max(metrics['lha_executor_queued'])
                    queue_history.append((now, queue))
                    while len(queue_history) > 1 and queue_history[1][0] <= now - self.thresholds['queue_growth_seconds']:
                        queue_history.popleft()
                    if (len(queue_history) > 1 and now - queue_history[0][0] >= self.thresholds['queue_growth_seconds']
                            and all(b[1] >= a[1] for a,b in zip(queue_history, list(queue_history)[1:]))
                            and queue > queue_history[0][1]):
                        self.halt('queue_continuously_growing')
                    for item in values:
                        labels = item['metric']
                        if labels['__name__'] == 'lha_container_state':
                            value = float(item['value'][1])
                            if labels.get('measure') == 'oom_killed' and value:
                                self.halt('container_oom')
                            if labels.get('measure') == 'restart_count':
                                name = labels.get('container', '')
                                previous = restarts.setdefault(name, value)
                                if value > previous:
                                    self.halt('container_restarted')
                    checks = {
                        'low_memory': (min(metrics['lha_host_memory_available_bytes']) < self.thresholds['memory_available_min_bytes'], self.thresholds['memory_hold_seconds']),
                        'low_disk': (min(metrics['lha_host_disk_free_bytes']) < self.thresholds['disk_free_min_bytes'], 0),
                        'queue_high': (max(metrics['lha_executor_queued']) > self.thresholds['queue_max'], self.thresholds['queue_hold_seconds']),
                        'cpu_with_queue': (max(metrics.get('lha_host_cpu_percent', [0])) > self.thresholds['cpu_max_percent'] and queue > 0, self.thresholds['cpu_hold_seconds']),
                        'dependency_down': (any(v != 1 for k in ['up', 'lha_dependency_up'] for v in metrics[k]), 0),
                    }
                    self.event('server_guard_sample', metrics=metrics)
                    for name, (active, seconds) in checks.items():
                        if active:
                            held.setdefault(name, now)
                            if now - held[name] >= seconds:
                                self.halt(name)
                        else:
                            held.pop(name, None)
                    self.metrics_ready.set()
                except Exception as exc:
                    held.setdefault('metrics_unavailable', now)
                    self.event('guard_error', error_type=type(exc).__name__)
                    if now - held['metrics_unavailable'] >= self.thresholds['metrics_unavailable_seconds']:
                        self.halt('metrics_unavailable')
                try:
                    await asyncio.wait_for(self.stop.wait(), timeout=self.thresholds['poll_seconds'])
                except asyncio.TimeoutError:
                    pass

    async def run(self):
        await self.login()
        start = time.monotonic()
        self.event('run_start', mode=self.config['mode'], sample_names=[s['name'] for s in self.samples])
        guard = asyncio.create_task(self.monitor()) if self.config['mode'] != 'smoke' else None
        pending, planned = set(), 0
        try:
            if guard:
                try:
                    await asyncio.wait_for(self.metrics_ready.wait(), timeout=self.thresholds['metrics_unavailable_seconds'] + 1)
                except asyncio.TimeoutError:
                    self.halt('initial_metrics_unavailable')
            while planned < self.config['max_tasks'] and not self.stop.is_set() and time.monotonic() - start < self.config['duration_seconds']:
                limit = self.config['max_inflight'] if self.config['mode'] == 'arrival' else self.config.get('concurrency', 1)
                if self.config['mode'] == 'arrival':
                    due = start + planned * 60 / self.config['arrival_per_minute']
                    delay = due - time.monotonic()
                    if delay > 0:
                        try:
                            await asyncio.wait_for(self.stop.wait(), timeout=delay)
                            break
                        except asyncio.TimeoutError:
                            pass
                    if time.monotonic() - start >= self.config['duration_seconds']:
                        break
                pending = {job for job in pending if not job.done()}
                if len(pending) >= limit:
                    if self.config['mode'] == 'arrival':
                        self.event('arrival_not_dispatched', sequence=planned, inflight=len(pending), reason='inflight_limit', lateness_seconds=max(0, time.monotonic() - due))
                        planned += 1
                        continue
                    await asyncio.wait(pending, return_when=asyncio.FIRST_COMPLETED, timeout=0.25)
                    continue
                self.event('task_dispatched', sequence=planned, lateness_seconds=max(0, time.monotonic() - due) if self.config['mode'] == 'arrival' else 0)
                pending.add(asyncio.create_task(self.one(planned)))
                planned += 1
                await asyncio.sleep(0)
            # Do not cancel running jobs when stopping new arrivals. Each has a deadline.
            if pending:
                await asyncio.gather(*pending)
        finally:
            self.stop.set()
            if guard:
                await guard
            await self.http.aclose()
            self.result_log.close()
            self.log.close()
        report_times = [r['report_readable_seconds'] for r in self.rows if 'report_readable_seconds' in r]
        summary = {'run_id': self.run_id, 'planned_arrivals': planned, 'submitted_tasks': len(self.rows),
                   'statuses': dict(Counter(r.get('status', r.get('error_type', 'unknown')) for r in self.rows)),
                   'successful_expected_results': sum(r['success'] for r in self.rows),
                   'readable_reports': len(report_times), 'unresolved_tasks': sum(r['unresolved'] for r in self.rows),
                   'report_seconds_p50': percentile(report_times, 0.5), 'report_seconds_p95': percentile(report_times, 0.95),
                   'latency_statistics_note': 'Exploratory observations; fewer than 100 reports do not establish a stable P95' if len(report_times)<100 else 'Report sample size >=100',
                   'elapsed_seconds': time.monotonic() - start, 'observed_tokens': self.tokens,
                   'stop_reasons': self.stop_reasons, 'network_measurement': 'remote only if run on a separate client machine',
                   'budget_note': 'Tokens are observed after completion; inflight usage can exceed this soft limit. Configure provider billing caps separately.'}
        (self.out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2))
        return summary


def load_samples(path):
    data = json.loads(path.read_text())
    if not isinstance(data, list) or not data:
        raise ValueError('Nonempty samples array required')
    for sample in data:
        if sample.get('expected') not in ('published', 'refused', 'awaiting_images') or not sample.get('images'):
            raise ValueError('Each sample needs images and an expected result')
        if not math.isfinite(sample.get('weight', 1)) or sample.get('weight', 1) <= 0:
            raise ValueError('Positive sample weight required')
        for image in sample['images'] + sample.get('new_images', []):
            file = (path.parent / image['path']).resolve()
            if not file.is_file() or file.stat().st_size > 10 * 1024 * 1024:
                raise ValueError('Sample file missing or too large')
            image['path'] = str(file)
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--thresholds', type=Path, default=Path(__file__).resolve().parents[1] / 'config/thresholds.json')
    parser.add_argument('--readiness', type=Path)
    parser.add_argument('--origin', choices=['unspecified','server-local','remote-client'], default='unspecified')
    parser.add_argument('--prometheus-url', help='Client-local Prometheus URL, normally an SSH tunnel')
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', args.run_id):
        parser.error('Invalid run ID')
    os.umask(0o077)
    config = json.loads(args.config.read_text())
    credentials = dict(dotenv_values(args.env_file))
    if args.prometheus_url:
        credentials['RAG_PROMETHEUS_URL']=args.prometheus_url
    for key in ['RAG_BASE_URL', 'RAG_TEST_EMAIL', 'RAG_TEST_PASSWORD', 'RAG_TEST_TENANT_ID']:
        if not credentials.get(key):
            parser.error('Missing client credential setting: ' + key)
    readiness = json.loads(args.readiness.read_text()) if args.readiness else None
    validate(config, credentials['RAG_BASE_URL'], readiness)
    if config['mode']=='bounded_concurrency' and readiness['bounded_concurrency_authorization']['reserved_run_id']!=args.run_id:
        raise ValueError('Campaign reservation does not match this run ID')
    samples = load_samples(args.config.parent / config['samples']) if config['mode'] != 'smoke' else None
    if config['mode'] in ('single_report','bounded_concurrency'):
        if len(samples)!=1 or len(samples[0]['images'])!=1 or samples[0].get('new_images') or samples[0]['expected']!='published':
            raise ValueError('Single-report baseline requires one fixed report sample')
        if hashlib.sha256(Path(samples[0]['images'][0]['path']).read_bytes()).hexdigest()!=config.get('sample_sha256'):
            raise ValueError('Baseline sample hash does not match configuration')
    if config['mode'] != 'smoke' and not credentials.get('RAG_PROMETHEUS_URL'):
        parser.error('RAG_PROMETHEUS_URL requires a working SSH tunnel')
    thresholds = json.loads(args.thresholds.read_text())
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out / 'run-config.json').write_text(json.dumps({'run_id': args.run_id, 'base_url': credentials['RAG_BASE_URL'], 'measurement_origin':args.origin, 'client_platform':platform.system(), 'config': config,
                                                        'thresholds': thresholds, 'sample_files_sha256': {
                                                            Path(i['path']).name: hashlib.sha256(Path(i['path']).read_bytes()).hexdigest()
                                                            for s in samples or [] for i in s['images'] + s.get('new_images', [])}}, indent=2))
    runner = LoadClient(config, credentials, args.out, args.run_id, thresholds, samples)
    summary = asyncio.run(runner.run())
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary['successful_expected_results'] == summary['submitted_tasks'] and summary['submitted_tasks'] > 0 and not summary['stop_reasons'] else 1


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (KeyboardInterrupt, Exception) as exc:
        # Never print HTTP request objects, credentials, model content or raw bodies.
        print('Client stopped:', type(exc).__name__, 'Inspect local result files and server tasks before retrying.')
        raise SystemExit(1)
