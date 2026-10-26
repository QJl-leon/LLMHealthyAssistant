#!/usr/bin/env python3
"""Authorized production campaign: one three-task batch, then one four-task batch."""
import argparse
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(Path(__file__).parent/'client'))
from concurrency_evidence import validate_batch
from load_client import validate
from bounded_campaign import readiness

CAMPAIGN='mac_c34_20261019'
POLICY=ROOT.parent/'线上测试部署/results/concurrency-c34-campaign-20261019.json'


def reserve_state(state,batch,report):
    if state.get('campaign')!=CAMPAIGN or state.get('authorized') is not True:
        raise ValueError('Campaign not authorized')
    entries=state['batches']
    if batch not in (1,2) or len(entries)!=batch-1:raise ValueError('Batch already reserved or out of order')
    if any(e.get('status')!='passed' for e in entries):raise ValueError('Previous batch did not pass')
    count=batch+2
    if sum(e.get('observed_tokens',0) for e in entries)+30000*count>210000:raise ValueError('Campaign soft budget exhausted')
    run_id=f'{CAMPAIGN}_c{count}'
    authorization={'campaign':CAMPAIGN,'batch':batch,'reserved_run_id':run_id,'max_batch_tasks':count,
                   'max_concurrency':count,'max_campaign_tasks':7}
    report=dict(report,bounded_concurrency_authorization=authorization)
    cfg=json.loads((ROOT/f'deploy/performance/config/concurrency-{count}.json').read_text())
    validate(cfg,'https://www.smproject.site',report)
    entries.append({'batch':batch,'concurrency':count,'run_id':run_id,'status':'reserved',
                    'reserved_unix':time.time(),'task_slots_consumed':count})
    return report


@contextmanager
def ledger():
    with Path(str(POLICY)+'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=json.loads(POLICY.read_text());yield state
        temp=POLICY.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n')
        temp.chmod(0o600);temp.replace(POLICY)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['reserve','complete','status']);parser.add_argument('--batch',type=int,choices=[1,2])
    args=parser.parse_args();os.umask(0o077)
    if args.action=='status':print(POLICY.read_text());return 0
    if args.batch is None:raise ValueError('Batch required')
    with ledger() as state:
        if args.action=='reserve':result=reserve_state(state,args.batch,readiness())
        else:
            if len(state['batches'])<args.batch:raise ValueError('Batch not reserved')
            entry=state['batches'][args.batch-1]
            run=ROOT.parent/'线上测试部署/results'/entry['run_id']
            result=validate_batch(run,expected_tasks=args.batch+2)
            if args.batch==2:
                previous=json.loads((ROOT.parent/'线上测试部署/results'/state['batches'][0]['run_id']/'run.json').read_text())
                current=json.loads((run/'run.json').read_text())
                for key in ['files_sha256','model_config']:
                    if previous['environment'].get(key)!=current['environment'].get(key):
                        result['errors'].append('Configuration changed between steps: '+key)
                        result['healthy_concurrency_passed']=False
            checked=readiness();result['idle_at_completion']=checked['checks']['no_active_tasks']
            if entry.get('status')=='failed':
                result['healthy_concurrency_passed']=False;result['errors'].append('Batch previously failed')
            entry.update(status='passed' if result['healthy_concurrency_passed'] else 'failed',
                         observed_tokens=result['observed_tokens'],completed_unix=time.time())
            (run/'concurrency-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if args.action=='reserve' or result['healthy_concurrency_passed'] else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except (Exception,KeyboardInterrupt) as exc:
        print('Step campaign stopped:',type(exc).__name__,'. Inspect campaign and active tasks.',file=sys.stderr)
        raise SystemExit(1)
