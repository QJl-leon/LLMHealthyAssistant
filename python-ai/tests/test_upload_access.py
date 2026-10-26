"""No network/model calls: private upload resolution and its callers."""
import base64
from pathlib import Path

import pytest

from app.security.uploads import read_upload

KEY = '11111111-1111-4111-8111-111111111111.png'


@pytest.fixture
def uploads(tmp_path, monkeypatch):
    root = tmp_path / 'go-backend' / 'data' / 'uploads'
    root.mkdir(parents=True)
    monkeypatch.setenv('PROJECT_ROOT', str(tmp_path))
    monkeypatch.delenv('LHA_UPLOAD_DIR', raising=False)
    (root / KEY).write_bytes(b'private-image')
    return root


def test_internal_upload_resolution(uploads):
    assert read_upload('/uploads/' + KEY) == b'private-image'


@pytest.mark.parametrize('ref', [
    '/uploads/../private.png', '/uploads/nested/' + KEY,
    '/uploads/' + KEY + '?access_token=secret', '/uploads/%2e%2e/secret',
    '/etc/passwd', 'https://example.com/' + KEY, '/uploads/missing.png',
])
def test_internal_upload_rejects_uncontrolled_paths(uploads, ref):
    assert read_upload(ref) is None


def test_internal_upload_rejects_symlink(uploads, tmp_path):
    (uploads / KEY).unlink()
    secret = tmp_path / 'secret'
    secret.write_bytes(b'secret')
    (uploads / KEY).symlink_to(secret)
    assert read_upload('/uploads/' + KEY) is None


def test_callers_use_local_upload_without_http(uploads, monkeypatch):
    import httpx
    def forbidden(*args, **kwargs):
        raise AssertionError('upload must not use anonymous HTTP')
    monkeypatch.setattr(httpx.Client, 'get', forbidden)
    from app.agents.vision_agent import _fetch_image_bytes
    from app.agents.image_quality import _load_image_bytes
    from app.gateway.adapters.ocr import OCRAdapter
    from app.factory.health_parser import _to_vlm_url
    ref = '/uploads/' + KEY
    assert _fetch_image_bytes(ref) == b'private-image'
    assert _load_image_bytes('', KEY) == b'private-image'
    assert OCRAdapter()._fetch_image(ref) == b'private-image'
    assert _to_vlm_url(ref) == 'data:image/png;base64,' + base64.b64encode(b'private-image').decode()
    (uploads / KEY).unlink()
    assert _fetch_image_bytes(ref) is None
    assert OCRAdapter()._fetch_image(ref) is None
    with pytest.raises(ValueError, match='unavailable'):
        _to_vlm_url(ref)


def test_raw_local_paths_not_accepted_by_runtime_adapters(uploads):
    from app.agents.vision_agent import _fetch_image_bytes
    from app.gateway.adapters.ocr import OCRAdapter
    assert _fetch_image_bytes(str(uploads / KEY)) is None
    assert OCRAdapter()._fetch_image(str(uploads / KEY)) is None


def test_vlm_converts_private_upload_to_inline_data(uploads):
    from app.gateway.adapters.vlm import VLMAdapter
    seen = []
    class Response:
        def raise_for_status(self): pass
        def json(self): return {'choices': []}
    class Client:
        def post(self, path, **kwargs):
            seen.append(kwargs['json']['messages'][0]['content'][0]['image_url']['url'])
            return Response()
    adapter = object.__new__(VLMAdapter)
    adapter.client, adapter.api_key, adapter.model = Client(), 'test', 'test'
    adapter.analyze_image('/uploads/' + KEY, 'test')
    assert seen == ['data:image/png;base64,' + base64.b64encode(b'private-image').decode()]


def test_ocr_vlm_does_not_construct_public_upload_url(uploads, monkeypatch):
    from app.gateway.adapters.ocr import OCRAdapter
    from app.gateway.adapters.vlm import VLMAdapter
    seen = []
    def analyze(self, url, prompt):
        seen.append(url)
        return {'choices': [{'message': {'content': '{"metrics": []}'}}]}
    monkeypatch.setattr(VLMAdapter, '__init__', lambda self: None)
    monkeypatch.setattr(VLMAdapter, 'analyze_image', analyze)
    result = OCRAdapter()._extract_vlm('/uploads/' + KEY)
    assert 'error' not in result
    assert seen == ['/uploads/' + KEY]


def test_image_embedding_reads_private_upload(uploads, monkeypatch):
    from app.gateway.adapters.clip import CLIPAdapter
    adapter = CLIPAdapter()
    seen = []
    monkeypatch.setattr(adapter, 'embed_image', lambda data, content_type: seen.append((data, content_type)) or [1.0])
    assert adapter.embed_url('/uploads/' + KEY) == [1.0]
    assert seen == [(b'private-image', 'image/png')]
