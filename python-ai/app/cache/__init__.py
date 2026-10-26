from __future__ import annotations
import hashlib
import json
import logging
import os
import random
import threading
import time
from contextlib import contextmanager
from typing import Any, Callable, Optional
logger = logging.getLogger(__name__)
DEFAULT_PREFIX = 'lha:cache:'
BREAKER_SECONDS = 30
TTL_JITTER_RATIO = 0.1

def _short_hash(text: str, n: int=16) -> str:
    return hashlib.md5(text.encode('utf-8')).hexdigest()[:n]

class RedisCache:

    def __init__(self, url: Optional[str]=None, enabled: Optional[bool]=None, prefix: str=DEFAULT_PREFIX):
        self.url = url or os.getenv('REDIS_URL', 'redis://localhost:6379/0')
        if enabled is None:
            enabled = os.getenv('CACHE_ENABLED', 'true').lower() in ('1', 'true', 'yes')
        self.enabled = enabled
        self.prefix = prefix
        self._client = None
        self._breaker_until = 0.0
        self._lock = threading.Lock()
        self.stats = {'hit': 0, 'miss': 0, 'error': 0, 'bypass': 0, 'set': 0}

    def _get_client(self):
        if not self.enabled:
            return None
        if time.time() < self._breaker_until:
            return None
        if self._client is not None:
            return self._client
        with self._lock:
            if self._client is not None:
                return self._client
            try:
                import redis
                client = redis.from_url(self.url, decode_responses=True, socket_connect_timeout=1.5, socket_timeout=1.5)
                client.ping()
                self._client = client
                logger.info('[Cache] Redis 已连接 %s', self.url)
                return self._client
            except Exception as e:
                self._breaker_until = time.time() + BREAKER_SECONDS
                logger.warning('[Cache] Redis 不可用，熔断 %ss 后重试: %s', BREAKER_SECONDS, e)
                return None

    def get(self, key: str) -> Optional[Any]:
        client = self._get_client()
        if client is None:
            self.stats['bypass'] += 1
            return None
        try:
            raw = client.get(self.prefix + key)
            if raw is None:
                self.stats['miss'] += 1
                return None
            self.stats['hit'] += 1
            return json.loads(raw)
        except Exception as e:
            self.stats['error'] += 1
            self._breaker_until = time.time() + BREAKER_SECONDS
            logger.warning('[Cache] get 失败（降级回源）: %s', e)
            return None

    def set(self, key: str, value: Any, ttl: int=3600) -> bool:
        client = self._get_client()
        if client is None:
            self.stats['bypass'] += 1
            return False
        jitter = int(ttl * TTL_JITTER_RATIO)
        ttl_actual = ttl + random.randint(-jitter, jitter) if jitter > 0 else ttl
        try:
            client.setex(self.prefix + key, max(1, ttl_actual), json.dumps(value, ensure_ascii=False))
            self.stats['set'] += 1
            return True
        except Exception as e:
            self.stats['error'] += 1
            logger.warning('[Cache] set 失败（忽略）: %s', e)
            return False

    def invalidate_version(self, knowledge_version: str) -> int:
        client = self._get_client()
        if client is None:
            return 0
        removed = 0
        try:
            for k in client.scan_iter(match=f'{self.prefix}*{knowledge_version}*', count=200):
                client.delete(k)
                removed += 1
        except Exception as e:
            logger.warning('[Cache] invalidate 失败: %s', e)
        return removed

    def clear_all(self) -> int:
        client = self._get_client()
        if client is None:
            return 0
        removed = 0
        try:
            for k in client.scan_iter(match=f'{self.prefix}*', count=500):
                client.delete(k)
                removed += 1
        except Exception as e:
            logger.warning('[Cache] clear_all 失败: %s', e)
        return removed

    def reset_stats(self) -> None:
        for k in self.stats:
            self.stats[k] = 0

    def hit_rate(self) -> float:
        total = self.stats['hit'] + self.stats['miss']
        return round(self.stats['hit'] / total, 4) if total else 0.0

def embedding_key(query: str, model: str, dim: int) -> str:
    return f'emb:{model}:{dim}:{_short_hash(query)}'

def retrieval_key(query: str, tenant_id: str, knowledge_version: str, channels: str, top_k: int) -> str:
    sig = f'{query}|{tenant_id}|{knowledge_version}|{channels}|{top_k}'
    return f'ret:{knowledge_version}:{_short_hash(sig)}'

def rerank_key(query: str, doc_ids: list[str], model: str, top_k: int=10) -> str:
    ids = ','.join(sorted((str(d) for d in doc_ids)))
    return f"rrk:{model}:{top_k}:{_short_hash(f'{query}|{ids}')}"

def hyde_key(query: str, model: str) -> str:
    return f'hyde:{model}:{_short_hash(query)}'
_inflight: dict[str, threading.Lock] = {}
_inflight_guard = threading.Lock()

@contextmanager
def singleflight(key: str):
    with _inflight_guard:
        lock = _inflight.setdefault(key, threading.Lock())
    acquired = lock.acquire(timeout=30)
    try:
        yield acquired
    finally:
        if acquired:
            lock.release()
        with _inflight_guard:
            if key in _inflight and (not _inflight[key].locked()):
                _inflight.pop(key, None)
_cache: Optional[RedisCache] = None

def get_cache() -> RedisCache:
    global _cache
    if _cache is None:
        _cache = RedisCache()
    return _cache

def cached_json(cache_key: str, ttl: int, loader: Callable[[], Any]) -> Any:
    cache = get_cache()
    hit = cache.get(cache_key)
    if hit is not None:
        return hit
    with singleflight(cache_key) as acquired:
        if acquired:
            hit = cache.get(cache_key)
            if hit is not None:
                return hit
        value = loader()
        if value is not None:
            cache.set(cache_key, value, ttl)
        return value
