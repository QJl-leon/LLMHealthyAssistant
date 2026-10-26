#!/usr/bin/env python3
"""Read-only server readiness check. Does not invoke models or deploy anything."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse

from dotenv import dotenv_values
import psycopg

ROOT = Path(__file__).resolve().parents[2]


def executor_idle(text):
    values={name:[] for name in ['lha_executor_busy','lha_executor_queued','lha_grpc_active']}
    for line in text.splitlines():
        if line.startswith('#') or not line.strip(): continue
        name=line.split()[0].split('{',1)[0]
        if name in values: values[name].append(float(line.split()[-1]))
    return bool(values['lha_executor_busy'] and values['lha_executor_queued']) and all(value==0 for group in values.values() for value in group)


def check(root, base, prometheus, gates_path, environment, expected_binary):
    config = dotenv_values(root / '.env')
    gates = json.loads(gates_path.read_text())
    result = {'checked_unix': time.time(), 'base_url': base.rstrip('/'), 'environment': environment,
              'checks': {}, 'ready_for_smoke': False, 'ready_for_load': False, 'blockers': []}
    checks = result['checks']
    checks['testing_not_paused'] = gates.get('testing_paused') is not True
    checks['forced_auth'] = str(config.get('AUTH_REQUIRED', '')).lower() in ('true', '1', 'yes') and bool(config.get('JWT_SECRET'))
    try:
        with urlopen(base.rstrip('/') + '/', timeout=10) as response:
            checks['website'] = response.status == 200
        try:
            with urlopen(Request(base.rstrip('/') + '/api/v1/uploads', data=b''), timeout=10) as response:
                status = response.status
        except HTTPError as exc:
            status = exc.code
        checks['anonymous_upload_denied'] = status == 401
    except Exception as exc:
        checks['website'] = False
        result['http_check_error'] = type(exc).__name__
    try:
        with psycopg.connect(config['DATABASE_URL'], connect_timeout=5) as connection:
            connection.execute('SET TRANSACTION READ ONLY')
            rows = connection.execute('SELECT version, dirty FROM schema_migrations').fetchall()
            result['migration_version'] = rows
            checks['ownership_migration'] = bool(rows and rows[0][0] >= 4 and not rows[0][1]) and bool(connection.execute("SELECT to_regclass('uploaded_files')").fetchone()[0])
            checks['postgres'] = connection.execute('SELECT 1').fetchone() == (1,)
    except Exception as exc:
        checks['postgres'] = False
        checks['ownership_migration'] = False
        result['database_check_error'] = type(exc).__name__
    binary = root / '.run/lha-go'
    checks['expected_go_binary_deployed'] = binary.is_file() and expected_binary.is_file() and hashlib.sha256(binary.read_bytes()).digest() == hashlib.sha256(expected_binary.read_bytes()).digest()
    try:
        with urlopen(prometheus.rstrip('/') + '/api/v1/targets', timeout=10) as response:
            targets = json.load(response)['data']['activeTargets']
        result['targets'] = {item['labels']['job']: item['health'] for item in targets}
        checks['metrics_targets'] = len(targets) >= 4 and all(item['health'] == 'up' for item in targets)
        query = '{__name__=~"lha_dependency_up|lha_host_memory_available_bytes|lha_host_disk_free_bytes|lha_grpc_active|lha_executor_busy|lha_executor_queued"}'
        with urlopen(prometheus.rstrip('/') + '/api/v1/query?' + urlencode({'query': query}), timeout=10) as response:
            values = json.load(response)['data']['result']
        dependencies = [float(item['value'][1]) for item in values if item['metric']['__name__'] == 'lha_dependency_up']
        checks['dependencies'] = bool(dependencies) and all(v == 1 for v in dependencies)
        resources = {item['metric']['__name__']: float(item['value'][1]) for item in values if item['metric']['__name__'] != 'lha_dependency_up'}
        result['resources'] = resources
        active = [float(item['value'][1]) for item in values if item['metric']['__name__'] in ('lha_grpc_active','lha_executor_busy','lha_executor_queued')]
        checks['no_active_tasks'] = bool(active) and all(value==0 for value in active)
        checks['resource_headroom'] = resources.get('lha_host_memory_available_bytes', 0) >= 1073741824 and resources.get('lha_host_disk_free_bytes', 0) >= 2147483648
    except Exception as exc:
        checks['metrics_targets'] = False
        result['metrics_check_error'] = type(exc).__name__
    try:
        port=config.get('LHA_PYTHON_METRICS_PORT','9108')
        with urlopen(f'http://127.0.0.1:{port}/metrics',timeout=5) as response:
            checks['no_active_tasks']=executor_idle(response.read().decode())
        result['idle_check_source']='fresh loopback exporter; avoids Prometheus scrape lag'
    except Exception as exc:
        checks['no_active_tasks']=False
        result['idle_check_error']=type(exc).__name__
    result['units'] = {}
    for unit in ['lha-local-go', 'lha-local-python', 'lha-observer', 'nginx']:
        response = subprocess.run(['systemctl', 'is-active', unit], capture_output=True, text=True)
        result['units'][unit] = response.stdout.strip()
    checks['services'] = all(value == 'active' for value in result['units'].values())
    for key in ['sse_owner_isolation_verified', 'report_owner_isolation_verified', 'real_report_chain_verified']:
        checks[key] = gates.get(key) is True
    checks['isolated_target'] = (environment == 'isolated' and config.get('LHA_ENVIRONMENT') == 'isolated'
                                 and urlparse(base).hostname not in ('www.smproject.site', 'smproject.site'))
    smoke_checks = ['testing_not_paused', 'forced_auth', 'website', 'anonymous_upload_denied', 'postgres', 'metrics_targets', 'dependencies', 'resource_headroom', 'services']
    result['ready_for_smoke'] = all(checks.get(key, False) for key in smoke_checks)
    required_keys=['DEEPSEEK_API_KEY','DASHSCOPE_API_KEY','SILICONFLOW_API_KEY']
    if config.get('OCR_ENGINE')=='tencent': required_keys.extend(['TENCENT_SECRET_ID','TENCENT_SECRET_KEY'])
    provider=config.get('RERANKER_PROVIDER','siliconflow')
    required_keys.append({'jina':'JINA_API_KEY','qwen':'QWEN_RERANK_API_KEY'}.get(provider,'SILICONFLOW_API_KEY'))
    result['model_credentials_present'] = all(bool(config.get(key)) for key in required_keys)
    result['configured_vlm_model']=config.get('VLM_MODEL','qwen-vl-max')
    result['configured_vlm_visible']=False
    try:
        request=Request('https://dashscope.aliyuncs.com/compatible-mode/v1/models',headers={'Authorization':'Bearer '+config.get('DASHSCOPE_API_KEY','')})
        with urlopen(request,timeout=10) as response:
            models=json.load(response).get('data',[])
        result['configured_vlm_visible']=any(item.get('id')==result['configured_vlm_model'] for item in models if isinstance(item,dict))
    except Exception as exc:
        result['vlm_metadata_error']=type(exc).__name__
    result['ready_for_single_report'] = (result['ready_for_smoke'] and result['configured_vlm_visible'] and checks.get('no_active_tasks',False)
                                         and result['model_credentials_present'])
    result['single_report_scope'] = 'One synthetic image, one owner account, one task; load readiness remains separate.'
    result['ready_for_load'] = all(checks.values())
    result['blockers'] = [key for key, value in checks.items() if not value]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path, default=ROOT)
    parser.add_argument('--base-url', default='https://www.smproject.site')
    parser.add_argument('--prometheus-url', default='http://127.0.0.1:9190')
    parser.add_argument('--gates', type=Path, default=Path(__file__).parent / 'config/gates.json')
    parser.add_argument('--environment', choices=['production', 'isolated'], default='production')
    parser.add_argument('--expected-binary', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    result = check(args.project_root, args.base_url, args.prometheus_url, args.gates, args.environment,
                   args.expected_binary or args.project_root / '.run/lha-go.file-ownership-new')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result['ready_for_smoke'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
