#!/usr/bin/env python3
"""One new six-task batch: capture provider HTTP outcomes without resetting old failures."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from dotenv import dotenv_values

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent/'client'))
from rerank_diagnostic_evidence import validate_diagnostic
from load_client import validate
from bounded_campaign import readiness

CAMPAIGN='mac_c6diag_20261019'
RUN_ID=CAMPAIGN+'_c6'
POLICY=ROOT.parent/'线上测试部署/results/rerank-diagnostic-campaign-20261019.json'


def reserve_state(state,batch,report):
    if state.get('campaign')!=CAMPAIGN or state.get('authorized') is not True or batch!=1 or state['batches']:
        raise ValueError('Only one newly authorized diagnostic batch may be reserved')
    authorization={'campaign':CAMPAIGN,'batch':1,'reserved_run_id':RUN_ID,'max_batch_tasks':6,'max_concurrency':6,'max_campaign_tasks':6}
    result=dict(report,bounded_concurrency_authorization=authorization)
    cfg=json.loads((ROOT/'deploy/performance/config/concurrency-6-diagnostic.json').read_text())
    validate(cfg,'https://www.smproject.site',result)
    state['batches'].append({'batch':1,'run_id':RUN_ID,'status':'reserved','task_slots_consumed':6,'reserved_unix':time.time()})
    return result


@contextmanager
def ledger():
    with Path(str(POLICY)+'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=json.loads(POLICY.read_text());yield state
        temp=POLICY.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');temp.chmod(0o600);temp.replace(POLICY)


def checked_readiness(state):
    report=readiness();cfg=dotenv_values(ROOT/'.env')
    if cfg.get('LHA_RERANK_DIAGNOSTIC_RUN_ID')!=RUN_ID or cfg.get('RERANKER_PROVIDER')!='jina' or cfg.get('RERANKER_MODEL')!='jina-reranker-v3':
        raise ValueError('Diagnostic run/provider/model configuration mismatch')
    source=ROOT/'python-ai/app/gateway/adapters/reranker.py'
    if hashlib.sha256(source.read_bytes()).hexdigest()!=state['reranker_source_sha256']:
        raise ValueError('Reranker source changed since preparation')
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['reserve','complete','status']);parser.add_argument('--batch',type=int,choices=[1],default=1)
    args=parser.parse_args();os.umask(0o077)
    if args.action=='status':print(POLICY.read_text());return 0
    with ledger() as state:
        if args.action=='reserve':result=reserve_state(state,args.batch,checked_readiness(state))
        else:
            if not state['batches']:raise ValueError('Batch not reserved')
            run=ROOT.parent/'线上测试部署/results'/RUN_ID
            result=validate_diagnostic(run);report=checked_readiness(state)
            result['idle_at_completion']=report['checks']['no_active_tasks']
            entry=state['batches'][0]
            if entry.get('status')=='failed':result['healthy_concurrency_passed']=False;result['errors'].append('Batch previously failed')
            entry.update(status='passed' if result['healthy_concurrency_passed'] else 'failed',
                         diagnostic_evidence_complete=result['diagnostic_evidence_complete'],observed_tokens=result['observed_tokens'],completed_unix=time.time())
            (run/'concurrency-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if args.action=='reserve' or result['healthy_concurrency_passed'] else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except (Exception,KeyboardInterrupt) as exc:
        print('Diagnostic campaign stopped:',type(exc).__name__,'. Inspect campaign and active tasks.',file=sys.stderr)
        raise SystemExit(1)
