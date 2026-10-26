from app.observability.runtime import timed
import os
import time
import logging
from httpx import Client
logger = logging.getLogger(__name__)

class VLMAdapter:

    def __init__(self):
        self.api_key = os.getenv('DASHSCOPE_API_KEY', '')
        self.model = os.getenv('VLM_MODEL', 'qwen-vl-max')
        self.base_url = 'https://dashscope.aliyuncs.com/compatible-mode/v1'
        self.client = Client(base_url=self.base_url, timeout=60)

    @timed('model.vlm')
    def analyze_image(self, image_url: str, prompt: str) -> dict:
        if image_url.startswith('/uploads/'):
            from app.security.uploads import upload_data_url
            image_url = upload_data_url(image_url)
        started = time.monotonic()
        resp = self.client.post('/chat/completions', json={'model': self.model, 'messages': [{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': image_url}}, {'type': 'text', 'text': prompt}]}]}, headers={'Authorization': f'Bearer {self.api_key}'})
        resp.raise_for_status()
        data = resp.json()
        try:
            usage = data.get('usage') or {}
            logger.info('[VLM] model=%s prompt_tokens=%s completion_tokens=%s total_tokens=%s', self.model, usage.get('prompt_tokens'), usage.get('completion_tokens'), usage.get('total_tokens'))
            from app.context import cost as _cost
            _cost.record_usage('vlm', self.model, prompt_tokens=int(usage.get('prompt_tokens') or 0), completion_tokens=int(usage.get('completion_tokens') or 0), total_tokens=int(usage.get('total_tokens') or 0), latency_ms=int((time.monotonic()-started)*1000))
        except Exception as e:
            logger.debug('[VLM] usage 记录失败: %s', e)
        return data
