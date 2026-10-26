import importlib.util
from pathlib import Path

from PIL import Image
import pytest

spec = importlib.util.spec_from_file_location('ownership_tool', Path(__file__).resolve().parents[2] / 'deploy/observability/upload_ownership.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
KEY = '11111111-1111-4111-8111-111111111111.png'
USER = '22222222-2222-4222-8222-222222222222'
TENANT = '33333333-3333-4333-8333-333333333333'


class Result:
    def __init__(self, value): self.value = value
    def fetchone(self): return self.value


class DB:
    def __init__(self, existing=None):
        self.existing = existing
        self.writes = []
    def execute(self, query, params=()):
        if query.startswith('SELECT 1 FROM users'):
            return Result((1,))
        if query.startswith('SELECT tenant_id'):
            return Result(self.existing)
        if query.startswith('INSERT'):
            self.writes.append(params)
            return Result(None)
        raise AssertionError('Unexpected query')


@pytest.fixture
def fixture(tmp_path):
    Image.new('RGB', (2, 2)).save(tmp_path / KEY)
    manifest = {'assignments': [{'image_key': KEY, 'user_id': USER, 'tenant_id': TENANT,
                                'reviewed': True, 'evidence': 'manually verified upload event'}]}
    return tmp_path, manifest


def test_import_is_validation_only_by_default(fixture):
    directory, manifest = fixture
    db = DB()
    assert tool.import_reviewed(db, directory, manifest) == 1
    assert db.writes == []


def test_reviewed_import(fixture):
    directory, manifest = fixture
    db = DB()
    assert tool.import_reviewed(db, directory, manifest, apply=True) == 1
    assert db.writes[0][:3] == (KEY, TENANT, USER)


def test_import_cannot_reassign_existing_file(fixture):
    directory, manifest = fixture
    db = DB(existing=(TENANT, '44444444-4444-4444-8444-444444444444'))
    with pytest.raises(ValueError, match='reassigned'):
        tool.import_reviewed(db, directory, manifest, apply=True)
    assert db.writes == []


@pytest.mark.parametrize('field,value', [('reviewed', False), ('evidence', ''), ('image_key', '../secret.png')])
def test_import_requires_review_and_safe_path(fixture, field, value):
    directory, manifest = fixture
    manifest['assignments'][0][field] = value
    db = DB()
    with pytest.raises(ValueError):
        tool.import_reviewed(db, directory, manifest, apply=True)
    assert db.writes == []


def test_private_inventory_file_permissions(tmp_path):
    path = tmp_path / 'inventory.json'
    tool.write_private(path, {'files': []})
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        tool.write_private(path, {})
