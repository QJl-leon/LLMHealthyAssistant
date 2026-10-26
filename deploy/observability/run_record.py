#!/usr/bin/env python3
"""Capture server test windows. Defaults preserve the existing local deployment."""
import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import time
from urllib.parse import urlencode
from urllib.request import urlopen

from dotenv import dotenv_values
import psutil

DEFAULT_ROOT = Path(__file__).resolve().parents[2]


def api(base, path, params=None):
    url = base.rstrip('/') + path + ('?' + urlencode(params) if params else '')
    with urlopen(url, timeout=30) as stream:
        body = json.load(stream)
    if body.get('status') != 'success':
        raise RuntimeError('Prometheus query failed')
    return body['data']


def environment(root, containers, frontend_dir=Path("/var/www/lha")):
    config = dotenv_values(root / '.env')
    keys = ['LLM_MODEL', 'SMALL_LLM_MODEL', 'VLM_MODEL', 'OCR_ENGINE', 'RERANKER_PROVIDER',
            'RERANKER_MODEL', 'EMBEDDING_MODEL', 'MILVUS_COLLECTION', 'AUTH_REQUIRED',
            'TASK_TOKEN_BUDGET', 'USER_DAILY_TOKEN_QUOTA', 'CACHE_ENABLED', 'HYDE_ENABLED']
    hashes = {}
    for folder, patterns in [('python-ai/app', ('*.py',)), ('go-backend', ('*.go',)),
                             ('go-backend/migrations', ('*.sql',)),
                             ('deploy', ('*.yml', '*.yaml', '*.conf', '*.py', '*.json')),
                             ('web/dist', ('*.js', '*.css', '*.html'))]:
        for pattern in patterns:
            for path in sorted((root / folder).rglob(pattern)):
                hashes[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    binary = root / '.run/lha-go'
    if binary.exists():
        hashes['.run/lha-go'] = hashlib.sha256(binary.read_bytes()).hexdigest()
    deployed_frontend = {}
    for pattern in ['*.js', '*.css', '*.html']:
        for path in sorted(frontend_dir.rglob(pattern)):
            deployed_frontend[str(path.relative_to(frontend_dir))] = hashlib.sha256(path.read_bytes()).hexdigest()
    limits, issues = [], []
    try:
        raw = subprocess.check_output(['sudo', '-n', 'docker', 'inspect', *containers], timeout=8, stderr=subprocess.DEVNULL)
        for item in json.loads(raw):
            limits.append({'name': item['Name'], 'image': item['Config']['Image'], 'image_id': item['Image'],
                           'memory_limit_bytes': item['HostConfig']['Memory'], 'nano_cpus': item['HostConfig']['NanoCpus'],
                           'restart_policy': item['HostConfig']['RestartPolicy'], 'state': {
                               k: item['State'].get(k) for k in ['Running', 'OOMKilled', 'StartedAt']},
                           'restart_count': item.get('RestartCount')})
    except Exception as exc:
        issues.append('container_snapshot:' + type(exc).__name__)
    migration = None
    try:
        import psycopg
        with psycopg.connect(config['DATABASE_URL'], connect_timeout=3) as connection:
            connection.execute('SET TRANSACTION READ ONLY')
            migration = connection.execute('SELECT version, dirty FROM schema_migrations').fetchall()
    except Exception as exc:
        issues.append('migration_snapshot:' + type(exc).__name__)
    return {'captured_at': datetime.now(timezone.utc).isoformat(),
            'deployment_sha256': hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
            'files_sha256': hashes, 'deployed_frontend_sha256': deployed_frontend, 'migration': migration,
            'hardware': {'cpu_logical': psutil.cpu_count(), 'ram_bytes': psutil.virtual_memory().total,
                         'swap_bytes': psutil.swap_memory().total, 'kernel': platform.release()},
            'model_config': {key: config[key] for key in keys if key in config},
            'containers': limits, 'snapshot_issues': issues,
            'version_note': 'File hashes include source, local build and static artifacts; they do not prove which Python modules are already loaded.'}


def timestamp(row):
    if 'ts_unix' in row:
        return float(row['ts_unix'])
    value = row.get('ts')
    if isinstance(value, (int, float)):
        return float(value)
    return datetime.fromisoformat(value.replace('Z', '+00:00')).timestamp()


def window_rows(paths, start, end):
    for path in paths:
        opener = gzip.open if path.suffix == '.gz' else open
        try:
            with opener(path, 'rt') as stream:
                for line in stream:
                    try:
                        row = json.loads(line)
                        if start <= timestamp(row) <= end:
                            yield row
                    except (ValueError, TypeError, KeyError, AttributeError):
                        continue
        except OSError:
            continue


def export_logs(base, out, run_id, start, end, nginx_log):
    app = sorted(set(p for prefix in ['task-events.jsonl', 'go-events.jsonl']
                     for p in (base / 'logs').glob(prefix + '*') if p.is_file()))
    tasks = {r['task_id'] for r in window_rows(app, start, end)
             if r.get('run_id') == run_id and r.get('task_id')}
    sources = {'task-events': app,
               'resource-samples': sorted((base / 'logs').glob('resource-samples.jsonl*')),
               'nginx-events': sorted(nginx_log.parent.glob(nginx_log.name + '*'))}
    counts = {}
    for name, paths in sources.items():
        count = 0
        with gzip.open(out / (name + '.jsonl.gz'), 'wt') as stream:
            for row in window_rows(paths, int(start) if name == 'nginx-events' else start, end):
                if name != 'resource-samples' and row.get('run_id') != run_id and row.get('task_id') not in tasks:
                    continue
                stream.write(json.dumps(row, ensure_ascii=False) + '\n')
                count += 1
        counts[name] = {'records': count, 'sources': [str(p) for p in paths],
                        'available': bool(paths), 'readable': bool(paths) and all(os.access(p, os.R_OK) for p in paths)}
    return counts


def export_metrics(base, out, start, end):
    # Chunking bounds memory and Prometheus query size during 8-hour windows.
    selectors = ['{__name__=~"lha_.*|up"}', '{job="lha-milvus",__name__=~"milvus_.*|process_.*|go_.*"}']
    errors = []
    with gzip.open(out / 'metrics.jsonl.gz', 'wt') as stream:
        for query in selectors:
            cursor = start
            while cursor <= end:
                stop = min(end, cursor + 1800)
                record = {'query': query, 'start': cursor, 'end': stop, 'step': 15}
                try:
                    record['data'] = api(base, '/api/v1/query_range', {'query': query, 'start': cursor, 'end': stop, 'step': 15})
                except Exception as exc:
                    record['error'] = type(exc).__name__
                    errors.append({'query': query, 'start': cursor, 'error': type(exc).__name__})
                stream.write(json.dumps(record) + '\n')
                cursor = stop + 15
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=DEFAULT_ROOT)
    parser.add_argument('--output-root', type=Path)
    parser.add_argument('--prometheus-url', default=os.getenv('LHA_PROMETHEUS_URL', 'http://127.0.0.1:9190'))
    parser.add_argument('--frontend-dir', type=Path, default=Path('/var/www/lha'))
    parser.add_argument('--nginx-log', type=Path, default=Path('/var/log/nginx/lha-observation.log'))
    parser.add_argument('--containers', default='lha-postgres,lha-redis,lha-milvus,lha-prometheus')
    parser.add_argument('action', choices=['begin', 'finish'])
    parser.add_argument('run_id')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,99}', args.run_id):
        parser.error('invalid run_id')
    os.umask(0o077)
    root = args.project_root.resolve()
    base = args.output_root or root.parent / '线上测试部署'
    out = base / 'results' / args.run_id
    containers = [s for s in args.containers.split(',') if s]
    if args.action == 'begin':
        out.mkdir(parents=True, exist_ok=False)
        manifest = {'format_version': 2, 'run_id': args.run_id, 'start_unix': time.time(),
                    'environment': environment(root, containers, args.frontend_dir), 'prometheus_url': args.prometheus_url}
        (out / 'run.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        targets = api(args.prometheus_url, '/api/v1/targets')
        (out / 'targets-start.json').write_text(json.dumps(targets, indent=2))
    else:
        manifest = json.loads((out / 'run.json').read_text())
        if manifest['prometheus_url'] != args.prometheus_url:
            parser.error('Prometheus URL differs from begin')
        end = time.time()
        manifest.update(end_unix=end, end_environment=environment(root, containers, args.frontend_dir))
        manifest['metric_export_errors'] = export_metrics(args.prometheus_url, out, manifest['start_unix'], end)
        manifest['log_exports'] = export_logs(base, out, args.run_id, manifest['start_unix'], end, args.nginx_log)
        try:
            targets = api(args.prometheus_url, '/api/v1/targets')
            (out / 'targets-end.json').write_text(json.dumps(targets, indent=2))
        except Exception as exc:
            manifest['targets_end_error'] = type(exc).__name__
        manifest['log_export_warnings'] = [name for name, status in manifest['log_exports'].items() if not status['readable']]
        manifest['export_complete'] = not manifest['metric_export_errors'] and not manifest.get('targets_end_error') and not manifest['log_export_warnings']
        (out / 'run.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
        if not manifest['export_complete']:
            print('Partial export saved; inspect run.json')
            return 1
    print(out)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
