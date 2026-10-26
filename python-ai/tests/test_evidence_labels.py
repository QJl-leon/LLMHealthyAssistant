import hashlib
import json

import pytest

from app.eval.evidence_labels import EvidenceLabels, aggregate_label_comparison


@pytest.fixture
def scorer(tmp_path):
    documents = [{'doc_id': 'topic_only', 'text': '血糖诊断阈值'},
                 {'doc_id': 'answer', 'text': '有氧配合抗阻训练'},
                 {'doc_id': 'outside', 'text': '餐后散步'}]
    labels = []
    for d in documents:
        effective = d['doc_id'] != 'topic_only'
        labels.append({'query': '怎样锻炼', 'doc_id': d['doc_id'],
                       'snippet_sha256': hashlib.sha256(d['text'].encode()).hexdigest(),
                       'answer_relevance': 2 if effective else 1,
                       'relation': 'supports' if effective else 'background',
                       'is_effective_evidence': effective, 'needs_source_review': False,
                       'confirmed_contradiction': False})
    p = tmp_path / 'labels.json'
    p.write_text(json.dumps({'knowledge_version': 'v1', 'documents': documents, 'labels': labels}))
    return EvidenceLabels(p, 'v1'), documents


def test_topic_only_and_semantic_answer_are_distinguished(scorer):
    labels, docs = scorer
    scores = labels.score_pair({'query': '怎样锻炼', 'topic': '血糖'}, docs[:2], ['topic_only', 'answer'], ['answer', 'topic_only'])
    assert scores['old_topic']['pre']['mrr@10'] == 1
    assert scores['old_topic']['post']['mrr@10'] == .5
    assert scores['new_candidate']['pre']['mrr@10'] == .5
    assert scores['new_candidate']['post']['mrr@10'] == 1
    assert scores['new_candidate']['post']['recall@10'] == 1
    assert scores['new_child_universe']['post']['recall@10'] == .5
    assert scores['new_child_universe']['candidate_recall'] == .5


def test_zero_answer_candidate_is_retained_in_average(scorer):
    labels, docs = scorer
    scores = labels.score_pair({'query': '怎样锻炼', 'topic': '血糖'}, docs[:1], ['topic_only'], ['topic_only'])
    assert scores['new_candidate']['n_relevant'] == 0
    assert scores['new_candidate']['post']['recall@10'] == 0
    summary = aggregate_label_comparison([{'label_scores': scores}])
    assert summary['new_candidate']['post']['recall@10'] == 0


def test_unknown_candidate_is_not_silently_labeled_irrelevant(scorer):
    labels, _ = scorer
    with pytest.raises(ValueError, match='缺少证据标注'):
        labels.validate_candidates('怎样锻炼', [{'doc_id': 'unknown', 'text': 'text'}])


def test_same_id_changed_text_is_rejected(scorer):
    labels, _ = scorer
    with pytest.raises(ValueError, match='内容与证据标注不一致'):
        labels.validate_candidates('怎样锻炼', [{'doc_id': 'answer', 'text': '完全不同的内容'}])


def test_ranked_id_outside_candidates_is_rejected(scorer):
    labels, docs = scorer
    with pytest.raises(ValueError, match='候选外ID'):
        labels.score_pair({'query': '怎样锻炼', 'topic': '血糖'}, docs[:2], ['topic_only'], ['outside'])
