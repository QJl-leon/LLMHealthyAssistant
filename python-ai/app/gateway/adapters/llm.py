from app.observability.runtime import timed
import os
import logging
from httpx import Client
logger = logging.getLogger(__name__)

class LLMAdapter:
    _small_instance: 'LLMAdapter | None' = None

    def __init__(self, model: str | None=None, base_url: str | None=None, api_key: str | None=None):
        self.api_key = api_key or os.getenv('DEEPSEEK_API_KEY', '')
        base_url = base_url or os.getenv('DEEPSEEK_BASE_URL', 'https://api.deepseek.com')
        base_url = base_url.rstrip('/')
        if base_url.endswith('/v1'):
            base_url = base_url[:-len('/v1')]
        self.base_url = base_url
        self.model = model or os.getenv('LLM_MODEL', 'deepseek-chat')
        self.client = Client(base_url=self.base_url, timeout=30)

    @classmethod
    def small(cls) -> 'LLMAdapter':
        if cls._small_instance is None:
            api_key = os.getenv('SMALL_LLM_API_KEY') or os.getenv('DASHSCOPE_API_KEY') or os.getenv('DEEPSEEK_API_KEY', '')
            cls._small_instance = cls(model=os.getenv('SMALL_LLM_MODEL', 'qwen-flash'), base_url=os.getenv('SMALL_LLM_BASE_URL', 'https://dashscope.aliyuncs.com/compatible-mode'), api_key=api_key)
        return cls._small_instance

    @timed('model.llm')
    def chat(self, messages: list[dict], **kwargs) -> dict:
        from app.context import cost as _cost
        _cost.check_limits()
        import time as _time
        _t0 = _time.monotonic()
        resp = self.client.post('/v1/chat/completions', json={'model': self.model, 'messages': messages, **kwargs}, headers={'Authorization': f'Bearer {self.api_key}'})
        resp.raise_for_status()
        data = resp.json()
        latency_ms = int((_time.monotonic() - _t0) * 1000)
        try:
            usage = data.get('usage') or {}
            logger.info('[LLM] model=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s', self.model, usage.get('prompt_tokens'), usage.get('completion_tokens'), usage.get('total_tokens'))
            _cost.record_usage('llm', self.model, prompt_tokens=int(usage.get('prompt_tokens') or 0), completion_tokens=int(usage.get('completion_tokens') or 0), total_tokens=int(usage.get('total_tokens') or 0), latency_ms=latency_ms)
        except Exception as e:
            logger.debug('[LLM] usage 记录失败: %s', e)
        return data
