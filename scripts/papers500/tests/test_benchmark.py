"""Offline checks for benchmark labels, rank metrics, channel calls and dry-run."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


maker = load('make_eval_set')
bench = load('benchmark')


def test_real_dataset_is_complete_and_consistent(capsys):
    rows, meta = bench.load_dataset(ROOT / 'eval_set_v1.jsonl')
    assert len(rows) == 562
    assert meta['papers'] == 500
    assert len({row['expected_doc_id'] for row in rows if row['suite'] == 'coverage'}) == 500
    bench.main(['--dry-run', '--suite', 'human', '--limit', '3'])
    report = json.loads(capsys.readouterr().out)
    assert report['cases'] == 3
    assert report['by_suite'] == {'human': 3}


def test_generator_uses_literal_source_and_rejects_wrong_human_label(tmp_path):
    papers = tmp_path / 'papers.jsonl'
    human = tmp_path / 'human.jsonl'
    body = 'Abstract. ' + ('Exercise and nutrition outcomes were measured. ' * 210)
    docs = [dict(id=f'doc{i}', knowledge_version='kv', content={
        'pmcid': f'PMC{i}', 'raw_text': body + str(i), 'title': f'Title {i}'}) for i in range(2)]
    papers.write_text(''.join(json.dumps(row) + '\n' for row in docs))
    item = dict(id='paper_1', pmcid='PMC0', expected_doc_id='doc0',
                query_zh='研究了什么？', query_en='What was studied?', evidence_anchor='Exercise',
                source_set='set', topic='exercise', file_format='pdf', title='Title 0')
    human.write_text(json.dumps(item) + '\n')
    rows, meta = maker.build(papers, human, expected_papers=2)
    assert meta['human_query_variants'] == 2
    assert meta['coverage_queries'] == 2
    assert len(rows) == 4
    for row in rows:
        if row['suite'] == 'coverage':
            source = next(doc for doc in docs if doc['content']['pmcid'] == row['pmcid'])
            assert row['evidence_anchor'] in source['content']['raw_text']
            assert row['expected_doc_id'] == source['id']
    item['expected_doc_id'] = 'wrong'
    human.write_text(json.dumps(item) + '\n')
    with pytest.raises(ValueError, match='mismatched PMCID'):
        maker.build(papers, human, expected_papers=2)


def test_rank_metrics_deduplicate_many_chunks_from_one_paper():
    hits = [dict(chunk_id=f'a{i}', doc_id='other', score=1.0) for i in range(8)]
    hits += [dict(chunk_id='target', doc_id='wanted', score=.5)]
    ranked = bench.collapse_documents(hits, 10)
    assert [row['doc_id'] for row in ranked] == ['other', 'wanted']
    score = bench.score_one(ranked, 'wanted', 10)
    assert score['rank'] == 2 and score['hit@5'] == 1
    assert score['mrr@10'] == .5
    assert bench.score_one(ranked, 'absent', 10)['mrr@10'] == 0


def test_rrf_combines_chunk_rank_lists_without_mixing_documents():
    dense = [dict(chunk_id='a', doc_id='doc-a', score=.99),
             dict(chunk_id='b', doc_id='doc-b', score=.5)]
    bm25 = [dict(chunk_id='b', doc_id='doc-b', score=100),
            dict(chunk_id='c', doc_id='doc-c', score=50)]
    fused = bench.reciprocal_rank_fusion(dense, bm25)
    assert fused[0]['chunk_id'] == 'b'
    assert len(fused) == 3


def test_search_uses_expected_dense_and_bm25_fields():
    calls = []

    class Hit:
        id = 'chunk'
        score = .9
        entity = {'doc_id': 'paper', 'pmcid': 'PMC1', 'chunk_index': 3}

    def fake_search(**kwargs):
        calls.append(kwargs)
        return [[Hit()]]

    collection = SimpleNamespace(search=fake_search)
    dense, _ = bench.search(collection, 'question', [1, 0], 'dense', 50, 'filter', 128)
    bm25, _ = bench.search(collection, 'question', None, 'bm25', 50, 'filter', 128)
    assert dense == bm25
    assert calls[0]['anns_field'] == 'embedding'
    assert calls[0]['param']['metric_type'] == 'COSINE'
    assert calls[1]['anns_field'] == 'sparse_vector'
    assert calls[1]['data'] == ['question']
    assert calls[0]['expr'] == calls[1]['expr'] == 'filter'


def test_evaluate_outputs_separate_channel_rows(tmp_path):
    class Hit:
        id = 'c'
        score = 1.0
        entity = {'doc_id': 'doc', 'pmcid': 'PMC1', 'chunk_index': 0}

    coll = SimpleNamespace(name='papers500_baseline', search=lambda **kwargs: [[Hit()]])
    cases = [dict(id='q', suite='human', language='en', query='query',
                  expected_doc_id='doc', pmcid='PMC1')]
    args = SimpleNamespace(channels=['dense', 'bm25', 'hybrid'], candidate_k=10, ef=128,
                           top_k=10, current_strategy='baseline')
    rows = bench.evaluate_collection(coll, cases, {'query': [1, 0]}, args, 'filter',
                                     tmp_path / 'out.jsonl')
    assert [row['channel'] for row in rows] == ['dense', 'bm25', 'hybrid']
    assert all(row['metrics']['hit@1'] == 1 for row in rows)
    assert len((tmp_path / 'out.jsonl').read_text().splitlines()) == 3
    summary = bench.summarize_strategy(rows)
    assert len([entry for entry in summary if entry['group'] == 'all']) == 3
