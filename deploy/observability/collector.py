#!/usr/bin/env python3
"""Sample host, services and dependencies; no application payloads are collected."""
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import subprocess
import time

import psutil
import psycopg
import redis
from dotenv import dotenv_values
from prometheus_client import Gauge, start_http_server

ROOT = Path('/home/ubuntu/RAG-job/LLMHealthyAssistant')
OUT = Path('/home/ubuntu/RAG-job/线上测试部署/logs')
CONFIG = dotenv_values(ROOT / '.env')
METRICS = {}
for name, description in {
 'host_cpu_percent':'Host CPU utilization', 'host_memory_available_bytes':'Available host memory',
 'host_memory_total_bytes':'Host RAM', 'host_swap_used_bytes':'Swap used',
 'host_disk_free_bytes':'Free bytes on workspace filesystem', 'host_load1':'One minute load',
 'host_disk_read_bytes_total':'Host disk bytes read', 'host_disk_write_bytes_total':'Host disk bytes written',
 'host_tcp_established':'TCP established sockets', 'host_tcp_time_wait':'TCP TIME_WAIT sockets',
 'postgres_connections':'Database connections', 'postgres_active':'Active database sessions',
 'postgres_waiting':'Waiting database sessions excluding idle client waits',
 'postgres_xact_commit_total':'Committed transactions', 'postgres_deadlocks_total':'Deadlocks',
 'postgres_blks_hit_total':'Buffer hits', 'postgres_blks_read_total':'Disk block reads',
 'postgres_max_connections':'Database connection limit',
 'redis_used_memory_bytes':'Redis memory', 'redis_connected_clients':'Redis clients',
 'redis_blocked_clients':'Redis blocked clients', 'redis_evicted_keys_total':'Redis evictions',
 'redis_keyspace_hits_total':'Redis hits', 'redis_keyspace_misses_total':'Redis misses',
 'redis_rejected_connections_total':'Redis rejected connections',
}.items():
 METRICS[name] = Gauge('lha_'+name, description)
SERVICE = Gauge('lha_service_process', 'Process tree values; cpu_seconds is cumulative', ['service','measure'])
CONTAINER = Gauge('lha_container_state', 'Container state and limits', ['container','measure'])
UP = Gauge('lha_dependency_up', 'Last collector query succeeded', ['dependency'])
DURATION = Gauge('lha_collection_seconds', 'Full collector cycle duration')
LOG = logging.getLogger('resource-samples')
LOG.setLevel(logging.INFO)
OUT.mkdir(parents=True, exist_ok=True)
h = RotatingFileHandler(OUT/'resource-samples.jsonl',maxBytes=20*1024*1024,backupCount=10)
h.setFormatter(logging.Formatter('%(message)s')); LOG.addHandler(h)


def command(args):
 return subprocess.check_output(args,timeout=3,text=True).strip()


def sample():
 values = {}
 def put(name,value):
  METRICS[name].set(value); values[name]=value
 started=time.monotonic()
 put('host_cpu_percent',psutil.cpu_percent())
 mem=psutil.virtual_memory()
 put('host_memory_available_bytes',mem.available);put('host_memory_total_bytes',mem.total)
 put('host_swap_used_bytes',psutil.swap_memory().used)
 put('host_disk_free_bytes',psutil.disk_usage(str(ROOT)).free)
 put('host_load1',os.getloadavg()[0])
 io=psutil.disk_io_counters()
 put('host_disk_read_bytes_total',io.read_bytes);put('host_disk_write_bytes_total',io.write_bytes)
 sockets=psutil.net_connections(kind='tcp')
 put('host_tcp_established',sum(c.status=='ESTABLISHED' for c in sockets))
 put('host_tcp_time_wait',sum(c.status=='TIME_WAIT' for c in sockets))
 pids={}
 for name,unit in [('go','lha-local-go'),('python','lha-local-python'),('minio','lha-local-minio'),('nginx','nginx')]:
  try:pids[name]=int(command(['systemctl','show',unit,'--property=MainPID','--value']))
  except Exception:UP.labels(name).set(0)
 try:
  containers=json.loads(command(['docker','inspect','lha-postgres','lha-redis','lha-milvus','lha-otel-collector']))
  for c in containers:
   name=c['Name'].lstrip('/')
   pids[name]=c['State']['Pid']
   for label,value in [('running',int(c['State']['Running'])),('oom_killed',int(c['State']['OOMKilled'])),('restart_count',c['RestartCount']),('memory_limit_bytes',c['HostConfig']['Memory'])]:
    CONTAINER.labels(name,label).set(value)
 except Exception: UP.labels('docker').set(0)
 else:UP.labels('docker').set(1)
 for name,pid in pids.items():
  try:
   if pid<=0:raise RuntimeError('not running')
   parent=psutil.Process(pid);procs=[parent]+parent.children(recursive=True)
   result={'pid':pid,'threads':0,'fds':0,'rss_bytes':0,'cpu_seconds':0,'io_read_bytes_total':0,'io_write_bytes_total':0}
   for p in procs:
    try:
     result['threads']+=p.num_threads();result['fds']+=p.num_fds();result['rss_bytes']+=p.memory_info().rss
     cpu=p.cpu_times();result['cpu_seconds']+=cpu.user+cpu.system
     io=p.io_counters();result['io_read_bytes_total']+=io.read_bytes;result['io_write_bytes_total']+=io.write_bytes
    except (psutil.NoSuchProcess,psutil.AccessDenied):pass
   for label,value in result.items():SERVICE.labels(name,label).set(value)
   values[name]=result;UP.labels(name).set(1)
  except Exception:UP.labels(name).set(0)
 try:
  with psycopg.connect(CONFIG['DATABASE_URL'],connect_timeout=2,options='-c statement_timeout=2000') as conn:
   row=conn.execute("SELECT count(*),count(*) FILTER (WHERE state='active'),count(*) FILTER (WHERE wait_event IS NOT NULL AND state<>'idle') FROM pg_stat_activity WHERE datname=current_database() AND pid<>pg_backend_pid()").fetchone()
   for name,value in zip(['postgres_connections','postgres_active','postgres_waiting'],row):put(name,value)
   row=conn.execute('SELECT xact_commit,deadlocks,blks_hit,blks_read FROM pg_stat_database WHERE datname=current_database()').fetchone()
   for name,value in zip(['postgres_xact_commit_total','postgres_deadlocks_total','postgres_blks_hit_total','postgres_blks_read_total'],row):put(name,value)
   put('postgres_max_connections',int(conn.execute('SHOW max_connections').fetchone()[0]))
  UP.labels('postgres').set(1)
 except Exception as exc:
  UP.labels('postgres').set(0);values['postgres_error']=type(exc).__name__
 try:
  client=redis.Redis.from_url(CONFIG['REDIS_URL'],socket_connect_timeout=2,socket_timeout=2)
  try:info=client.info()
  finally:client.close()
  for key in ['used_memory','connected_clients','blocked_clients','evicted_keys','keyspace_hits','keyspace_misses','rejected_connections']:
   target='redis_'+key+('_bytes' if key=='used_memory' else '_total' if key in ['evicted_keys','keyspace_hits','keyspace_misses','rejected_connections'] else '')
   put(target,info.get(key,0))
  UP.labels('redis').set(1)
 except Exception as exc:
  UP.labels('redis').set(0);values['redis_error']=type(exc).__name__
 DURATION.set(time.monotonic()-started)
 LOG.info(json.dumps({'ts_unix':time.time(),'duration_seconds':time.monotonic()-started,'values':values},ensure_ascii=False))


if __name__=='__main__':
 start_http_server(9110,addr='127.0.0.1')
 psutil.cpu_percent()
 while True:
  start=time.monotonic()
  try:sample()
  except Exception as exc:LOG.info(json.dumps({'ts_unix':time.time(),'collector_error':type(exc).__name__}))
  time.sleep(max(1,15-(time.monotonic()-start)))
