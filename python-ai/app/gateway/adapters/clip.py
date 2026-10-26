from __future__ import annotations
import base64
import logging
import os
logger = logging.getLogger(__name__)

def clip_dim() -> int:
    return int(os.getenv('CLIP_DIM', '4096'))

class CLIPAdapter:

    def __init__(self):
        self.api_key = os.getenv('SILICONFLOW_API_KEY', '')
        self.model = os.getenv('CLIP_MODEL', 'Qwen/Qwen3-VL-Embedding-8B')
        self.base_url = 'https://api.siliconflow.cn/v1'
        self.dim = clip_dim()

    def embed_image(self, image_data: bytes, content_type: str='image/jpeg') -> list[float]:
        if not self.api_key:
            raise RuntimeError('未配置 SILICONFLOW_API_KEY，图像向量化不可用')
        return self._embed_via_api(image_data, content_type)

    def embed_url(self, url: str) -> list[float]:
        import httpx
        if url.startswith('/uploads/'):
            from app.security.uploads import read_upload
            data = read_upload(url)
            if data is None:
                raise RuntimeError('Upload image unavailable')
            ext = url.rsplit('.', 1)[-1]
            content_type = 'image/jpeg' if ext == 'jpg' else f'image/{ext}'
            return self.embed_image(data, content_type)
        try:
            resp = httpx.get(url, timeout=30)
            resp.raise_for_status()
            content_type = resp.headers.get('content-type', 'image/jpeg')
            return self.embed_image(resp.content, content_type)
        except Exception as e:
            logger.warning('[CLIP] URL 下载/向量化失败: %s → %s', url[:80], e)
            raise RuntimeError(f'图片下载/向量化失败: {url[:80]} → {e}') from e

    def _embed_via_api(self, image_data: bytes, content_type: str) -> list[float]:
        import httpx
        b64 = base64.b64encode(image_data).decode('ascii')
        data_url = f'data:{content_type};base64,{b64}'
        with httpx.Client(base_url=self.base_url, timeout=60) as client:
            resp = client.post('/embeddings', json={'model': self.model, 'input': [data_url]}, headers={'Authorization': f'Bearer {self.api_key}'})
            resp.raise_for_status()
            data = resp.json()
        vec = data['data'][0]['embedding']
        if not vec or all((v == 0.0 for v in vec)):
            raise RuntimeError(f'图像向量化返回无效向量（model={self.model}）')
        logger.info('[CLIP] 云端向量化成功 model=%s dim=%d', self.model, len(vec))
        return vec
