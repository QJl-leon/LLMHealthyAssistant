#!/usr/bin/env python3
"""Server ledger: two one-shot batches; a failed/reserved batch blocks the next."""
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
from preflight import check

CAMPAIGN='mac_c2_20261019'
POLICY=ROOT.parent/'线上测试部署/results/concurrency-campaign-20261019.json'


def reserve_state(state,batch,report):
    if state.get('campaign')!=CAMPAIGN or state.get('authorized') is not True:
        raise ValueError('Campaign not authorized')
    entries=state['batches']
    if batch not in (1,2) or len(entries)!=batch-1:
        raise ValueError('Batch already reserved or out of order; no automatic retries')
    if any(e.get('status')!='passed' for e in entries):raise ValueError('Previous batch has not passed')
    if sum(e.get('observed_tokens',0) for e in entries)+60000>120000:raise ValueError('Campaign budget exhausted')
    run_id=f'{CAMPAIGN}_batch_{batch:02d}'
    authorization={'campaign':CAMPAIGN,'batch':batch,'reserved_run_id':run_id,'max_campaign_tasks':4}
    report=dict(report,bounded_concurrency_authorization=authorization)
    config=json.loads((ROOT/'deploy/performance/config/concurrency-two.json').read_text())
    validate(config,'https://www.smproject.site',report)
    entries.append({'batch':batch,'run_id':run_id,'status':'reserved','reserved_unix':time.time(),'task_slots_consumed':2})
    return report


@contextmanager
def ledger():
    with Path(str(POLICY)+'.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        state=json.loads(POLICY.read_text())
        yield state
        temp=POLICY.with_suffix('.tmp')
        temp.write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n');temp.chmod(0o600);temp.replace(POLICY)


def readiness():
    result=check(ROOT,'https://www.smproject.site','http://127.0.0.1:9190',ROOT/'deploy/performance/config/gates.json','production',ROOT/'.run/lha-go.file-ownership-new')
    if not result['checks'].get('no_active_tasks'):raise ValueError('Server has active work')
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['reserve','complete','status'])
    parser.add_argument('--batch',type=int,choices=[1,2])
    args=parser.parse_args();os.umask(0o077)
    if args.action=='status':
        print(POLICY.read_text());return 0
    if args.batch is None:raise ValueError('Batch required')
    with ledger() as state:
        if args.action=='reserve':
            result=reserve_state(state,args.batch,readiness())
        else:
            if len(state['batches'])<args.batch:raise ValueError('Batch not reserved')
            entry=state['batches'][args.batch-1]
            run=ROOT.parent/'线上测试部署/results'/entry['run_id']
            result=validate_batch(run)
            if args.batch==2:
                previous=json.loads((ROOT.parent/'线上测试部署/results'/state['batches'][0]['run_id']/'run.json').read_text())
                current_manifest=json.loads((run/'run.json').read_text())
                for key in ['files_sha256','model_config']:
                    if previous['environment'].get(key)!=current_manifest['environment'].get(key):
                        result['healthy_concurrency_passed']=False
                        result['errors'].append('Configuration changed between batches: '+key)
            current=readiness()
            result['idle_at_completion']=current['checks']['no_active_tasks']
            # A failed batch stays failed. Finalization only exports; it cannot retry tasks.
            if entry.get('status')=='failed':result['healthy_concurrency_passed']=False;result['errors'].append('Batch previously failed')
            entry.update(status='passed' if result['healthy_concurrency_passed'] else 'failed',observed_tokens=result['observed_tokens'],completed_unix=time.time())
            (run/'concurrency-validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if args.action=='reserve' or result['healthy_concurrency_passed'] else 2


if __name__=='__main__':
    try:raise SystemExit(main())
    except (Exception,KeyboardInterrupt) as exc:
        print('Campaign stopped:',type(exc).__name__,'. Check ledger and active tasks before continuing.',file=sys.stderr)
        raise SystemExit(1)
