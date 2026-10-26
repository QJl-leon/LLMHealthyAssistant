#!/usr/bin/env python3
"""Mac coordinator: read-only readiness, window begin, ONE report, drain, export."""
import argparse
import gzip
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys

from dotenv import dotenv_values
import httpx
from load_client import validate, load_samples


def run(args):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,79}', args.run_id):
        raise ValueError('Invalid run ID')
    if args.ssh_target.startswith('-') or not re.fullmatch(r'[A-Za-z0-9_.@:-]+',args.ssh_target):
        raise ValueError('Invalid SSH target')
    root=args.server_root.rstrip('/')
    if not root.startswith('/'):
        raise ValueError('Absolute server root required')
    base=str(Path(root).parent/'线上测试部署')
    python=root+'/python-ai/.venv/bin/python'
    readiness_path=base+'/results/readiness/'+args.run_id+'.json'
    output=args.out/args.run_id
    os.umask(0o077)
    output.mkdir(parents=True,exist_ok=args.finalize)
    credentials=dotenv_values(args.env_file)
    if not credentials.get('RAG_BASE_URL'):
        raise ValueError('Missing RAG_BASE_URL')
    def remote(command):
        completed=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',args.ssh_target,shlex.join(command)],capture_output=True,text=True)
        if completed.returncode:
            raise RuntimeError('Server command failed; inspect server state before retrying')
        return completed.stdout
    def readiness():
        raw=remote([python,root+'/deploy/performance/preflight.py','--base-url',credentials['RAG_BASE_URL'],'--out',readiness_path])
        body=json.loads(raw)
        (output/'server-readiness.json').write_text(json.dumps(body,ensure_ascii=False,indent=2))
        return body
    report=readiness()
    if not args.finalize:
        cfg=json.loads(args.config.read_text())
        if cfg['mode']!='single_report':
            raise ValueError('This coordinator only permits single_report')
        if not report.get('ready_for_single_report'):
            print('Single-report readiness failed:',json.dumps({'configured_vlm_model':report.get('configured_vlm_model'),'configured_vlm_visible':report.get('configured_vlm_visible'),'blockers':report.get('blockers',[])},ensure_ascii=False))
        validate(cfg,credentials['RAG_BASE_URL'],report)
        samples=load_samples(args.config.parent/cfg['samples'])
        # Pinning is also checked in the subprocess before any business request.
        if len(samples)!=1:
            raise ValueError('One fixed sample required')
        with httpx.Client(timeout=5) as http:
            response=http.get(args.prometheus_url.rstrip('/')+'/api/v1/query',params={'query':'up'})
            response.raise_for_status()
            body=response.json()
            if body.get('status')!='success' or not body['data']['result'] or any(float(v['value'][1])!=1 for v in body['data']['result']):
                raise RuntimeError('Open a healthy SSH monitoring tunnel before starting')
        remote([python,root+'/deploy/observability/run_record.py','begin',args.run_id])
        print('Server window started; sending one real report task.',flush=True)
        completed=subprocess.run([sys.executable,str(Path(__file__).with_name('load_client.py')),
                                  '--config',str(args.config),'--env-file',str(args.env_file),
                                  '--readiness',str(output/'server-readiness.json'),
                                  '--prometheus-url',args.prometheus_url,'--origin','remote-client',
                                  '--run-id',args.run_id,'--out',str(output/'client')])
        result=completed.returncode
        report=readiness()
    else:
        summary_path=output/'client/summary.json'
        data=json.loads(summary_path.read_text()) if summary_path.exists() else {}
        result=0 if data.get('successful_expected_results')==1 and not data.get('stop_reasons') else 1
    if not report['checks'].get('no_active_tasks'):
        print('Server still has active/queued work. Window left open; do not start another task.')
        print('After it drains, rerun this command with --finalize to export without creating a task.')
        return 2
    remote([python,root+'/deploy/observability/run_record.py','finish',args.run_id])
    remote_dir=base+'/results/'+args.run_id
    copied=subprocess.run(['scp','-r',args.ssh_target+':'+remote_dir,str(output/'server-archive')])
    if copied.returncode:
        raise RuntimeError('Export exists on server but download failed')
    # Return only this run's results. Never transmit the client's credential file.
    if (output/'client').is_dir():
        sent=subprocess.run(['scp','-r',str(output/'client'),args.ssh_target+':'+remote_dir+'/client'])
        if sent.returncode:
            raise RuntimeError('Local client results exist but upload failed')
    stage_errors=[]
    seen_stages=set()
    events=output/'server-archive/task-events.jsonl.gz'
    if events.exists():
        with gzip.open(events,'rt') as stream:
            for line in stream:
                event=json.loads(line)
                if event.get('event')=='stage_end':seen_stages.add(event.get('stage'))
                if event.get('event')=='stage_end' and event.get('outcome')=='error':
                    stage_errors.append({'stage':event.get('stage'),'error_type':event.get('error_type')})
    else:stage_errors.append({'stage':'missing_server_evidence','error_type':'MissingFile'})
    for missing in sorted({'model.ocr','model.vlm','orchestrator.report_draft','save_report'}-seen_stages):
        stage_errors.append({'stage':missing,'error_type':'MissingRequiredStage'})
    (output/'baseline-validation.json').write_text(json.dumps({'stage_errors':stage_errors,'healthy_baseline_passed':result==0 and not stage_errors},indent=2))
    if stage_errors:
        print('Report may have been saved through fallback; stage errors found. Stop the measurement series.')
        result=1
    print('Window exported and client/server results synchronized:',output)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file',type=Path,default=Path('client.env'))
    parser.add_argument('--config',type=Path,default=Path(__file__).resolve().parents[1]/'config/single-report.json')
    parser.add_argument('--ssh-target',default='ubuntu@43.165.5.253')
    parser.add_argument('--server-root',default='/home/ubuntu/RAG-job/LLMHealthyAssistant')
    parser.add_argument('--prometheus-url',default='http://127.0.0.1:9190')
    parser.add_argument('--run-id',required=True)
    parser.add_argument('--out',type=Path,default=Path('results'))
    parser.add_argument('--finalize',action='store_true',help='Only finalize an existing window; never create another task')
    return run(parser.parse_args())


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except (Exception,KeyboardInterrupt) as exc:
        print('Coordinator stopped:',type(exc).__name__,'. Check server work before starting another run.')
        raise SystemExit(1)
