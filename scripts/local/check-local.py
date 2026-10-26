"""Check real dependencies without calling paid model APIs."""
from pathlib import Path
import sys
import os
from urllib.request import urlopen

import grpc
import psycopg
import redis
from dotenv import dotenv_values
from pymilvus import connections, utility

config = dotenv_values(Path(__file__).resolve().parents[2] / '.env')
failed = []

def check(name, fn):
    try:
        print(f'{name}: OK {fn() or ""}')
    except Exception as exc:
        # Do not print connection strings, which can contain credentials.
        print(f'{name}: FAILED ({type(exc).__name__})')
        failed.append(name)

def postgres():
    with psycopg.connect(config['DATABASE_URL'], connect_timeout=5) as conn:
        assert conn.execute('SELECT 1').fetchone() == (1,)

def milvus():
    connections.connect(host=config['MILVUS_HOST'], port=config['MILVUS_PORT'], timeout=5)
    return f'version={utility.get_server_version()}, collections={utility.list_collections()}'

def grpc_ready():
    with grpc.insecure_channel('127.0.0.1:' + config.get('GRPC_SERVER_PORT', '50057')) as channel:
        grpc.channel_ready_future(channel).result(timeout=5)

def http(url):
    with urlopen(url, timeout=5) as response:
        assert response.status == 200
        return 'HTTP 200'

check('PostgreSQL', postgres)
check('Redis', lambda: redis.Redis.from_url(config['REDIS_URL'], socket_connect_timeout=5, socket_timeout=5).ping())
check('Milvus', milvus)
check('MinIO', lambda: http('http://' + config['MINIO_ENDPOINT'] + '/minio/health/live'))
check('Python gRPC', grpc_ready)
check('Go API', lambda: http('http://127.0.0.1:8080/healthz'))
check('Frontend', lambda: http(os.getenv('LHA_FRONTEND_URL', 'http://127.0.0.1:5173/')))
sys.exit(bool(failed))
