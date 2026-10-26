"""Offline tests for input integrity, vector failures and crash-safe replay."""
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('paper_import', Path(__file__).parents[1] / 'import_vectors.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def args(tmp_path, **updates):
    values = dict(version='v1', expected_papers=1, max_text_bytes=8192, max_text_chars=6000,
                  long_text='error', tenant_id='tenant', collection_prefix='papers500_test',
                  state_dir=tmp_path, resume=False, embedding_batch_size=2,
                  insert_batch_size=2, retries=0)
    values.update(updates)
    return SimpleNamespace(**values)


def record(index=0, text='paper text'):
    return dict(id=f'chunk{index}', doc_id='doc', source_id='source', pmcid='PMC1',
                knowledge_version='v1', strategy='fixed_length', actual_strategy='fixed_length',
                chunk_index=index, text=text, characters=len(text), metadata={'pmcid': 'PMC1'})


def export(tmp_path, rows):
    path = tmp_path / 'fixed_length.jsonl'
    path.write_text(''.join(json.dumps(row) + '\n' for row in rows), encoding='utf-8')
    return path


def test_utf8_limit_is_bytes_and_truncation_is_explicit():
    with pytest.raises(ValueError, match='超长块'):
        module.bounded_text('论文测', 5, 100, 'error')
    assert module.bounded_text('论文测', 5, 100, 'truncate') == '论'
    assert module.bounded_text('abcdef', 100, 3, 'truncate') == 'abc'


@pytest.mark.parametrize('mutation,match', [
    (lambda rows: rows[1].update(id='chunk0'), 'ID 重复'),
    (lambda rows: rows[1].update(chunk_index=3), '序号不连续'),
    (lambda rows: rows[1].update(knowledge_version='wrong'), '版本不符'),
    (lambda rows: rows[1].update(characters=0), '字符统计不符'),
    (lambda rows: rows[1].update(metadata={'pmcid': 'other'}), '元数据缺失'),
])
def test_preflight_rejects_corrupt_exports(tmp_path, mutation, match):
    rows = [record(0), record(1)]
    mutation(rows)
    with pytest.raises(ValueError, match=match):
        module.preflight(export(tmp_path, rows), 'fixed_length', args(tmp_path))


def test_preflight_reports_truncation_and_validates_paper_count(tmp_path):
    path = export(tmp_path, [record(text='文' * 3000)])
    info = module.preflight(path, 'fixed_length', args(tmp_path, long_text='truncate'))
    assert info['truncated_chunks'] == 1
    assert info['papers'] == info['chunks'] == 1
    assert len(info['sha256']) == 64
    with pytest.raises(ValueError, match='实际 1 篇'):
        module.preflight(path, 'fixed_length', args(tmp_path, expected_papers=500, long_text='truncate'))
    row = module.make_row(record(text='文' * 3000), args(tmp_path, long_text='truncate'), 'm', 2)
    assert row['text_truncated'] is True
    assert row['original_bytes'] == 9000
    assert len(row['text'].encode()) <= 8192


@pytest.mark.parametrize('vectors', [[], [[0, 0]], [[1]], [[float('nan'), 1]], [[float('inf'), 1]]])
def test_invalid_embedding_never_passes(vectors):
    adapter = SimpleNamespace(embed=lambda texts: vectors)
    with pytest.raises(RuntimeError, match='Embedding 失败'):
        module.embed_checked(adapter, ['text'], 2, 0)


def test_embedding_retries_transient_failure(monkeypatch):
    attempts = []

    def embed(texts):
        attempts.append(texts)
        if len(attempts) == 1:
            raise TimeoutError()
        return [[1, 0]]

    monkeypatch.setattr(module.time, 'sleep', lambda delay: None)
    assert module.embed_checked(SimpleNamespace(embed=embed), ['text'], 2, 1) == [[1, 0]]
    assert len(attempts) == 2


def test_schema_matches_insert_rows_with_installed_milvus_client(tmp_path, monkeypatch):
    import pymilvus
    captured = {}

    def collection(name, schema):
        captured['schema'] = schema
        return schema

    monkeypatch.setattr(pymilvus, 'Collection', collection)
    module.create_collection('papers500_test', 2, 'signature')
    schema = captured['schema']
    row = module.make_row(record(), args(tmp_path), 'model', 2)
    row['embedding'] = [1, 0]
    assert set(row) == {field.name for field in schema.fields} - {'sparse_vector'}
    assert schema.description == 'papers500:signature'
    assert next(field for field in schema.fields if field.name == 'embedding').params['dim'] == 2
    assert schema.functions[0].input_field_names == ['text']
    assert schema.functions[0].output_field_names == ['sparse_vector']


def fake_milvus(monkeypatch, flush_failure=False):
    collections = {}

    class FakeCollection:
        def __init__(self, signature):
            self.schema = SimpleNamespace(description=f'papers500:{signature}')
            self.rows = {}
            self.writes = []
            self.fail_flush = flush_failure

        def upsert(self, rows):
            self.writes.append([row['id'] for row in rows])
            self.rows.update({row['id']: row.copy() for row in rows})

        def flush(self):
            if self.fail_flush:
                self.fail_flush = False
                raise TimeoutError('flush interrupted')

    def create(name, dimension, signature):
        collections[name] = FakeCollection(signature)
        return collections[name]

    monkeypatch.setitem(sys.modules, 'pymilvus', SimpleNamespace(
        Collection=lambda name: collections[name],
        utility=SimpleNamespace(has_collection=lambda name: name in collections),
    ))
    monkeypatch.setattr(module, 'create_collection', create)
    monkeypatch.setattr(module, 'finish_indexes', lambda collection: None)
    return collections


def test_resume_replays_uncheckpointed_upsert_without_duplicates(tmp_path, monkeypatch):
    collections = fake_milvus(monkeypatch, flush_failure=True)
    settings = args(tmp_path)
    path = export(tmp_path, [record(0), record(1), record(2)])
    info = module.preflight(path, 'fixed_length', settings)
    adapter = SimpleNamespace(embed=lambda texts: [[1, 0] for _ in texts])
    with pytest.raises(TimeoutError):
        module.import_strategy('fixed_length', info, settings, adapter, 'm', 2)
    checkpoint = tmp_path / 'papers500_test_fixed_length.json'
    assert json.loads(checkpoint.read_text())['completed_rows'] == 0
    settings.resume = True
    result = module.import_strategy('fixed_length', info, settings, adapter, 'm', 2)
    collection = collections[result['collection']]
    assert result['chunks'] == len(collection.rows) == 3
    assert collection.writes == [['chunk0', 'chunk1'], ['chunk0', 'chunk1'], ['chunk2']]
    assert json.loads(checkpoint.read_text())['status'] == 'completed'
    writes_before = list(collection.writes)
    result = module.import_strategy('fixed_length', info, settings, adapter, 'm', 2)
    assert result['status'] == 'completed'
    assert collection.writes == writes_before
    settings.max_text_chars = 100
    with pytest.raises(ValueError, match='相同输入/配置'):
        module.import_strategy('fixed_length', info, settings, adapter, 'm', 2)


def test_embedding_failure_leaves_checkpoint_and_collection_empty(tmp_path, monkeypatch):
    collections = fake_milvus(monkeypatch)
    settings = args(tmp_path)
    info = module.preflight(export(tmp_path, [record()]), 'fixed_length', settings)
    adapter = SimpleNamespace(embed=lambda texts: [[0, 0]])
    with pytest.raises(RuntimeError):
        module.import_strategy('fixed_length', info, settings, adapter, 'm', 2)
    assert not collections['papers500_test_fixed_length'].rows
    state = json.loads((tmp_path / 'papers500_test_fixed_length.json').read_text())
    assert state['status'] == 'failed'
    assert state['completed_rows'] == 0


def test_dry_run_checks_summary_without_importing_network_dependencies(tmp_path, monkeypatch, capsys):
    export(tmp_path, [record()])
    summary = dict(knowledge_version='v1', strategies={
        'fixed_length': dict(status='completed', chunks=1, papers=1),
    })
    (tmp_path / 'summary.json').write_text(json.dumps(summary))
    monkeypatch.setitem(sys.modules, 'pymilvus', None)
    module.main(['--chunk-dirs', str(tmp_path), '--strategies', 'fixed_length',
                 '--version', 'v1', '--expected-papers', '1', '--dry-run'])
    assert json.loads(capsys.readouterr().out)['status'] == 'validated'
    summary['strategies']['fixed_length']['status'] = 'failed'
    (tmp_path / 'summary.json').write_text(json.dumps(summary))
    with pytest.raises(ValueError, match='完成状态'):
        module.main(['--chunk-dirs', str(tmp_path), '--strategies', 'fixed_length',
                     '--version', 'v1', '--expected-papers', '1', '--dry-run'])
