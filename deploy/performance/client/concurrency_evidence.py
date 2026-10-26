"""Validate each report and prove overlapping work from server timestamps."""
from datetime import datetime
import gzip
import json
import statistics
from pathlib import Path

SAMPLE_SHA256='3ca172f041e1019ca8c34315ebeab2683c99b5b70f63933d9d1a9dfcab3fd774'
REQUIRED={'model.ocr','model.vlm','orchestrator.report_draft','save_report'}


def validate_batch(directory, expected_tasks=2):
    if expected_tasks not in (2,3,4,6,8):raise ValueError('Unsupported batch size')
    directory=Path(directory)
    errors=[]
    summary=json.loads((directory/'client/summary.json').read_text())
    rows=[json.loads(line) for line in (directory/'client/tasks.jsonl').read_text().splitlines()]
    config=json.loads((directory/'client/run-config.json').read_text())
    manifest=json.loads((directory/'run.json').read_text())
    if (len(rows)!=expected_tasks or summary.get('submitted_tasks')!=expected_tasks or summary.get('successful_expected_results')!=expected_tasks
            or summary.get('readable_reports')!=expected_tasks or summary.get('unresolved_tasks')!=0 or summary.get('stop_reasons')):
        errors.append(f'Expected exactly {expected_tasks} completed, readable reports and no stop reasons')
    ids=[r.get('task_id') for r in rows];report_ids=[r.get('report_id') for r in rows]
    if len(set(ids))!=expected_tasks or None in ids or len(set(report_ids))!=expected_tasks or None in report_ids:
        errors.append('Task/report IDs must be distinct and present')
    if config.get('measurement_origin')!='remote-client':errors.append('Expected a remote client')
    if set(config.get('sample_files_sha256',{}).values())!={SAMPLE_SHA256}:errors.append('Sample hash mismatch')
    cfg=config.get('config',{})
    if (cfg.get('mode')!='bounded_concurrency' or cfg.get('concurrency')!=expected_tasks or cfg.get('max_tasks')!=expected_tasks
            or cfg.get('max_inflight')!=expected_tasks or cfg.get('required_vlm_model')!='qwen3-vl-plus'):
        errors.append('Client configuration differs from bounded campaign')
    if not manifest.get('export_complete') or manifest.get('metric_export_errors') or manifest.get('log_export_warnings'):
        errors.append('Server archive incomplete')
    before=manifest.get('environment',{});after=manifest.get('end_environment',{})
    for key in ['files_sha256','model_config']:
        if not before.get(key) or before.get(key)!=after.get(key):errors.append('Configuration changed or missing: '+key)
    if before.get('model_config',{}).get('VLM_MODEL')!='qwen3-vl-plus':errors.append('Server model mismatch')
    with gzip.open(directory/'task-events.jsonl.gz','rt') as stream:events=[json.loads(line) for line in stream]
    intervals=[]
    for row in rows:
        task=row.get('task_id');prefix=str(task)+': '
        if (not row.get('success') or row.get('unresolved') or row.get('status')!='published'
                or row.get('saved_status')!='published' or row.get('metrics_count',0)<=0
                or row.get('nonempty_sections',0)<=0 or row.get('model_call_count',0)<=0
                or row.get('total_tokens',0)<=0 or row.get('report_readable_seconds',0)<=0
                or row.get('report_versions')!=1 or row.get('run_id')!=manifest.get('run_id')):
            errors.append(prefix+'Incomplete report, usage, or unexpected report versions')
        stages=[e for e in events if e.get('task_id')==task and e.get('event')=='stage_end' and e.get('run_id')==manifest.get('run_id')]
        missing=REQUIRED-{e.get('stage') for e in stages if e.get('outcome')=='ok'}
        if missing:errors.append(prefix+'Missing successful stages: '+','.join(sorted(missing)))
        for e in stages:
            if e.get('outcome')!='ok':errors.append(prefix+str(e.get('stage'))+':'+str(e.get('outcome')))
        vision=[e for e in stages if e.get('stage')=='orchestrator.vision_observe' and e.get('outcome')=='ok']
        if len(vision)!=1:errors.append(prefix+'Expected one vision-observe interval')
        else:
            event=vision[0];end=datetime.fromisoformat(event['ts'].replace('Z','+00:00')).timestamp()
            start=end-float(event['duration_ms'])/1000
            if start<manifest['start_unix']-1 or end>manifest['end_unix']+1:errors.append(prefix+'Stage outside server window')
            intervals.append({'task_id':task,'start_unix':start,'end_unix':end})
    overlap=0
    if len(intervals)==expected_tasks:
        overlap=max(0,min(i['end_unix'] for i in intervals)-max(i['start_unix'] for i in intervals))
    if overlap<=0:errors.append('No overlapping server vision work proved')
    tokens=sum(r.get('total_tokens',0) for r in rows)
    if tokens!=summary.get('observed_tokens') or tokens>=30000*expected_tasks:errors.append('Usage mismatch or batch soft limit reached')
    times=[r['report_readable_seconds'] for r in rows if r.get('report_readable_seconds')]
    if times and statistics.median(times)>21.55800370799261*1.5:
        errors.append('Report latency exceeds the provisional 1.5x baseline target; pause and investigate')
    return {'run_id':manifest.get('run_id'),'healthy_concurrency_passed':not errors,'errors':errors,
            'tasks':len(rows),'observed_tokens':tokens,'server_vision_overlap_seconds':overlap,
            'server_vision_intervals':intervals,'report_readable_seconds':times,
            'scope':('Two tasks only; not a capacity or P95 conclusion' if expected_tasks==2 else f'{expected_tasks} tasks only; not a capacity or P95 conclusion')}
