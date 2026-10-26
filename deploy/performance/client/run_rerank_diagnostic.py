#!/usr/bin/env python3
"""Mac coordinator: authorized production six-task rerank diagnostic, six reports maximum; never advances to eight."""
import argparse
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys

from dotenv import dotenv_values
import httpx
from load_client import validate,load_samples
from concurrency_evidence import SAMPLE_SHA256
import hashlib

SERVER='ubuntu@43.165.5.253'
ROOT='/home/ubuntu/RAG-job/LLMHealthyAssistant'
BASE='/home/ubuntu/RAG-job/线上测试部署'
CAMPAIGN='mac_c6diag_20261019'


def remote(command,check=True):
    result=subprocess.run(['ssh','-o','BatchMode=yes','-o','ConnectTimeout=10',SERVER,shlex.join(command)],capture_output=True,text=True)
    if check and result.returncode:raise RuntimeError('Server command failed; inspect campaign status before proceeding')
    return result


def run(args):
    os.umask(0o077)
    count=6
    run_id=f'{CAMPAIGN}_c{count}'
    output=args.out/run_id
    credentials=dotenv_values(args.env_file)
    if credentials.get('RAG_BASE_URL','').rstrip('/')!='https://www.smproject.site':raise ValueError('Fixed production target required')
    cfgpath=Path(__file__).resolve().parents[1]/'config/concurrency-6-diagnostic.json'
    cfg=json.loads(cfgpath.read_text())
    samples=load_samples(cfgpath.parent/cfg['samples'])
    if (len(samples)!=1 or len(samples[0]['images'])!=1 or samples[0].get('new_images')
            or samples[0]['expected']!='published'
            or hashlib.sha256(Path(samples[0]['images'][0]['path']).read_bytes()).hexdigest()!=SAMPLE_SHA256):
        raise ValueError('Fixed synthetic report sample required')
    if output.exists() and not args.finalize:raise FileExistsError('Preserve the existing run directory')
    python=ROOT+'/python-ai/.venv/bin/python'
    campaign=ROOT+'/deploy/performance/rerank_diagnostic_campaign.py'
    if not args.finalize:
        with httpx.Client(timeout=5) as http:
            # Probe the Mac-to-target DNS/TLS path before consuming server task slots.
            target=http.get(credentials['RAG_BASE_URL'].rstrip('/')+'/')
            target.raise_for_status()
            response=http.get(args.prometheus_url.rstrip('/')+'/api/v1/query',params={'query':'up'})
            response.raise_for_status();data=response.json()
            if data.get('status')!='success' or not data['data']['result'] or any(float(v['value'][1])!=1 for v in data['data']['result']):
                raise ValueError('Healthy SSH monitoring tunnel required')
        output.mkdir(parents=True,exist_ok=False)
        reservation=json.loads(remote([python,campaign,'reserve','--batch',str(args.batch)]).stdout)
        validate(cfg,credentials['RAG_BASE_URL'],reservation)
        (output/'server-readiness.json').write_text(json.dumps(reservation,indent=2))
        remote([python,ROOT+'/deploy/observability/run_record.py','begin',run_id])
        print('Reserved step; sending at most',count,'report tasks:',run_id,flush=True)
        subprocess.run([sys.executable,str(Path(__file__).with_name('load_client.py')),
                        '--config',str(cfgpath),'--env-file',str(args.env_file),
                        '--readiness',str(output/'server-readiness.json'),
                        '--prometheus-url',args.prometheus_url,'--origin','remote-client',
                        '--run-id',run_id,'--out',str(output/'client')])
    if args.finalize:output.mkdir(parents=True,exist_ok=True)
    idle=json.loads(remote([python,ROOT+'/deploy/performance/preflight.py','--out',BASE+'/results/readiness/'+run_id+'.json']).stdout)
    (output/'end-readiness.json').write_text(json.dumps(idle,indent=2))
    if not idle['checks'].get('no_active_tasks'):
        print('Active work remains. Stop here; after drain, use the same --batch with --finalize. No new task is sent by finalize.')
        return 2
    remote([python,ROOT+'/deploy/observability/run_record.py','finish',run_id])
    directory=BASE+'/results/'+run_id
    if (output/'client').is_dir():
        remote(['mkdir','-p',directory+'/client'])
        subprocess.run(['scp','-r',str(output/'client')+'/.',SERVER+':'+directory+'/client/'],check=True)
    checked=remote([python,campaign,'complete','--batch',str(args.batch)],check=False)
    archive=output/'server-archive';archive.mkdir(exist_ok=True)
    subprocess.run(['scp','-r',SERVER+':'+directory+'/.',str(archive)],check=True)
    if checked.stdout.strip():
        evidence=json.loads(checked.stdout)
        (output/'concurrency-validation.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2)+'\n')
        print(json.dumps(evidence,ensure_ascii=False,indent=2))
    if checked.returncode:
        print('Batch did not pass. Do not start the next batch; inspect the synchronized archive.')
        return 2
    print('Batch passed; client and server archives synchronized:',output)
    return 0


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch',type=int,choices=[1],help='Only the new six-task diagnostic batch is allowed')
    parser.add_argument('--env-file',type=Path,default=Path('client.env'))
    parser.add_argument('--out',type=Path,default=Path('results'))
    parser.add_argument('--prometheus-url',default='http://127.0.0.1:9190')
    parser.add_argument('--finalize',action='store_true',help='Export/validate an already reserved batch; creates no task')
    args=parser.parse_args()
    if sys.platform!='darwin' and not args.finalize:raise ValueError('This production campaign must originate on the Mac client')
    if args.finalize and args.batch is None:raise ValueError('Finalize requires the original --batch')
    if args.batch is not None:return run(args)
    for batch in [1]:
        args.batch=batch
        result=run(args)
        if result:return result
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except (Exception,KeyboardInterrupt) as exc:
        print('Coordinator stopped:',type(exc).__name__,'. Check server campaign and active tasks before proceeding.')
        raise SystemExit(1)
