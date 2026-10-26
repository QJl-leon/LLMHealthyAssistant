from app.observability.runtime import timed, emit, CORRELATION
import os
import logging
import math
import uuid
from httpx import Client
logger = logging.getLogger(__name__)
CACHE_TTL_SECONDS = int(os.getenv('CACHE_TTL_RERANK', '3600'))


def retry_after_seconds(value):
    # Only numeric delta-seconds are retained; never log an untrusted header string.
    try:
        seconds=float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return seconds if math.isfinite(seconds) and 0 <= seconds <= 86400 else None


class RerankerAdapter:

    def __init__(self, provider: str | None=None):
        self.provider = (provider or os.getenv('RERANKER_PROVIDER', 'siliconflow')).strip().lower()
        if self.provider == 'jina':
            self.key_name = 'JINA_API_KEY'
            self.api_key = os.getenv('JINA_API_KEY', '')
            default_model = 'jina-reranker-v3'
            default_url = 'https://api.jina.ai/v1'
            model_override = os.getenv('JINA_RERANK_MODEL')
            url_override = os.getenv('JINA_RERANK_BASE_URL')
        elif self.provider == 'qwen':
            self.key_name = 'QWEN_RERANK_API_KEY'
            self.api_key = os.getenv(self.key_name, '')
            default_model = 'qwen3-rerank'
            default_url = 'https://maas.qianwenaiapi.com/compatible-api/v1'
            model_override = os.getenv('QWEN_RERANK_MODEL')
            url_override = os.getenv('QWEN_RERANK_BASE_URL')
        elif self.provider == 'siliconflow':
            self.key_name = 'SILICONFLOW_API_KEY'
            self.api_key = os.getenv('SILICONFLOW_API_KEY', '')
            default_model = 'BAAI/bge-reranker-v2-m3'
            default_url = 'https://api.siliconflow.cn/v1'
            model_override = url_override = None
        else:
            raise ValueError(f'不支持的 RERANKER_PROVIDER: {self.provider}')
        # Explicit provider selection must not inherit another provider's active config.
        generic_model = os.getenv('RERANKER_MODEL') if provider is None else None
        generic_url = os.getenv('RERANKER_BASE_URL') if provider is None else None
        if self.provider == 'qwen':
            generic_model = generic_url = None
        self.model = model_override or generic_model or default_model
        self.base_url = (url_override or generic_url or default_url).rstrip('/')
        self.rerank_path = os.getenv('QWEN_RERANK_PATH', '/reranks') if self.provider == 'qwen' else '/rerank'
        self.client = Client(base_url=self.base_url, timeout=float(os.getenv('RERANKER_TIMEOUT', '30')))

    def rerank(self, query: str, documents: list[str], top_k: int=10) -> list[dict]:
        from app.cache import get_cache, rerank_key
        cache = get_cache()
        cache_key = None
        diagnostic_run=os.getenv('LHA_RERANK_DIAGNOSTIC_RUN_ID','').strip()
        bypass=bool(diagnostic_run and CORRELATION.get().get('run_id')==diagnostic_run)
        cache_status='bypass' if bypass else ('disabled' if not cache.enabled else 'not_applicable')
        if cache.enabled and documents and not bypass:
            cache_key = rerank_key(query, documents, f'{self.base_url}:{self.model}', top_k)
            hit = cache.get(cache_key)
            cache_status='hit' if hit is not None else 'miss'
            if hit is not None:
                emit('rerank_cache',provider=self.provider,model=self.model,cache_status=cache_status,document_count=len(documents))
                return hit
        emit('rerank_cache',provider=self.provider,model=self.model,cache_status=cache_status,document_count=len(documents))
        results = self._rerank_uncached(query, documents, top_k)
        if cache_key is not None and results:
            cache.set(cache_key, results, ttl=CACHE_TTL_SECONDS)
        return results

    @timed('model.rerank')
    def _rerank_uncached(self, query: str, documents: list[str], top_k: int=10) -> list[dict]:
        import time as _time
        if not documents:
            return []
        if not self.api_key.strip():
            raise RuntimeError(f'请先在 .env 中填写 {self.key_name}')
        _t0 = _time.monotonic()
        response = None
        outcome, error_type = 'ok', ''
        attempt_id=uuid.uuid4().hex
        try:
            response = self.client.post(self.rerank_path, json={'model': self.model, 'query': query, 'documents': documents, 'top_n': top_k}, headers={'Authorization': f'Bearer {self.api_key}'})
            response.raise_for_status()
            results = response.json().get('results', [])
        except Exception as exc:
            outcome, error_type = 'error', type(exc).__name__
            raise
        finally:
            emit('rerank_http',provider=self.provider,model=self.model,attempt_id=attempt_id,
                 http_status=response.status_code if response is not None else None,
                 duration_ms=round((_time.monotonic()-_t0)*1000,3),outcome=outcome,error_type=error_type,
                 retry_after_seconds=retry_after_seconds(response.headers.get('Retry-After')) if response is not None else None,
                 document_count=len(documents),attempt=1)

        try:
            from app.context import cost as _cost
            est_tokens = max(1, len(query) * 2 // 3) + sum((max(1, len(d) * 2 // 3) for d in documents))
            _cost.record_usage('rerank', self.model, total_tokens=est_tokens, call_count=len(documents), latency_ms=int((_time.monotonic() - _t0) * 1000))
        except Exception as e:
            logger.debug('[Rerank] usage 记录失败: %s', e)
        return results
