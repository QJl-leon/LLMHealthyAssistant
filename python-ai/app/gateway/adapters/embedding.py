from app.observability.runtime import timed
import os
from httpx import Client
CACHE_MAX_BATCH = int(os.getenv('CACHE_EMBEDDING_MAX_BATCH', '32'))
CACHE_TTL_SECONDS = int(os.getenv('CACHE_TTL_EMBEDDING', '86400'))

class EmbeddingAdapter:

    def __init__(self):
        self.api_key = os.getenv('SILICONFLOW_API_KEY', '')
        self.model = os.getenv('EMBEDDING_MODEL', 'BAAI/bge-m3')
        self.base_url = 'https://api.siliconflow.cn/v1'
        self.timeout = float(os.getenv('EMBEDDING_TIMEOUT', '30'))
        self.client = Client(base_url=self.base_url, timeout=self.timeout)

    def embed(self, texts: list[str]) -> list[list[float]]:
        from app.cache import get_cache, embedding_key
        if not texts:
            return []
        dim = int(os.getenv('EMBEDDING_DIM', '1024'))
        cache = get_cache()
        use_cache = cache.enabled and len(texts) <= CACHE_MAX_BATCH
        if not use_cache:
            return self._embed_uncached(texts)
        keys = [embedding_key(t, self.model, dim) for t in texts]
        results: list[list[float] | None] = [None] * len(texts)
        miss_idx: list[int] = []
        for i, k in enumerate(keys):
            hit = cache.get(k)
            if hit is not None:
                results[i] = hit
            else:
                miss_idx.append(i)
        if miss_idx:
            vecs = self._embed_uncached([texts[i] for i in miss_idx])
            for i, vec in zip(miss_idx, vecs):
                results[i] = vec
                cache.set(keys[i], vec, ttl=CACHE_TTL_SECONDS)
        return [v if v is not None else [] for v in results]

    @timed('model.embedding')
    def _embed_uncached(self, texts: list[str]) -> list[list[float]]:
        import time as _time
        _t0 = _time.monotonic()
        resp = self.client.post('/embeddings', json={'model': self.model, 'input': texts}, headers={'Authorization': f'Bearer {self.api_key}'})
        resp.raise_for_status()
        data = resp.json()
        try:
            from app.context import cost as _cost
            usage = data.get('usage') or {}
            total = int(usage.get('total_tokens') or 0)
            if total <= 0:
                total = sum((max(1, len(t) * 2 // 3) for t in texts))
            _cost.record_usage('embedding', self.model, total_tokens=total, call_count=len(texts), latency_ms=int((_time.monotonic() - _t0) * 1000))
        except Exception as e:
            logger.debug('[Embedding] usage 记录失败: %s', e)
        return [item['embedding'] for item in data['data']]
