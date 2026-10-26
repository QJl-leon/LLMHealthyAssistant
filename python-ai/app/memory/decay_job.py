import argparse
import json
import logging
logger = logging.getLogger(__name__)

def run(user_id: str | None=None, dry_run: bool=False) -> dict:
    from app.memory.curator import MemoryCurator
    curator = MemoryCurator()
    if dry_run:
        report = {'dry_run': True, 'note': 'dry-run 只展示当前待确认队列，不执行衰减'}
        if user_id:
            pending = curator.decay_check(user_id)
            report['pending'] = [{'id': e.id, 'kind': e.kind, 'content': e.content, 'confidence': e.confidence} for e in pending]
        return report
    return curator.run_decay(user_id=user_id)

def main():
    parser = argparse.ArgumentParser(description='记忆置信度衰减调度')
    parser.add_argument('--user-id', default=None, help='限定单用户（默认全量）')
    parser.add_argument('--dry-run', action='store_true', help='只查不改')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s: %(message)s')
    report = run(user_id=args.user_id, dry_run=args.dry_run)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
if __name__ == '__main__':
    main()
