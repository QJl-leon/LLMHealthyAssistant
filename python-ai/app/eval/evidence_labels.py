"""Evaluate the same rankings using legacy topics and explicit answer evidence."""
import hashlib
import json
import math
from pathlib import Path
from statistics import mean


def binary_metrics(ranked, relevant, k=10):
    rel = set(relevant)
    top = ranked[:k]
    hits = sum(d in rel for d in top)
    ideal = sum(1 / math.log2(i + 2) for i in range(min(k, len(rel))))
    return {'recall@10': hits / len(rel) if rel else 0.0,
            'precision@10': hits / k,
            'mrr@10': next((1 / (i + 1) for i, d in enumerate(top) if d in rel), 0.0),
            'hit@1': float(bool(top) and top[0] in rel),
            'ndcg@10': sum(1 / math.log2(i + 2) for i, d in enumerate(top) if d in rel) / ideal if ideal else 0.0}


class EvidenceLabels:
    def __init__(self, path, knowledge_version=None):
        raw = Path(path).read_bytes()
        self.data = json.loads(raw)
        self.sha256 = hashlib.sha256(raw).hexdigest()
        if knowledge_version and self.data.get('knowledge_version') != knowledge_version:
            raise ValueError('证据标注知识版本不一致')
        self.documents = {d['doc_id']: d['text'] for d in self.data['documents']}
        self.labels = {}
        self.effective = {}
        for label in self.data['labels']:
            key = (label['query'], label['doc_id'])
            if key in self.labels:
                raise ValueError('证据标注存在重复问题/片段')
            self.labels[key] = label
            qi = label['query']
            self.effective.setdefault(qi, set())
            if label['is_effective_evidence']:
                if label['answer_relevance'] != 2 or label['relation'] != 'supports' or label['needs_source_review'] or label['confirmed_contradiction']:
                    raise ValueError('有效证据标记与内容标签矛盾')
                self.effective[qi].add(label['doc_id'])

    def validate_candidates(self, query, candidates):
        ids = [c['doc_id'] for c in candidates]
        if len(ids) != len(set(ids)):
            raise ValueError('候选ID重复')
        for c in candidates:
            key = (query, c['doc_id'])
            if key not in self.labels:
                raise ValueError(f'候选缺少证据标注: {c["doc_id"]}')
            label = self.labels[key]
            digest = hashlib.sha256(c['text'].encode()).hexdigest()
            if label['snippet_sha256'] != digest or self.documents[c['doc_id']] != c['text']:
                raise ValueError(f'候选内容与证据标注不一致: {c["doc_id"]}')

    def score_pair(self, case, candidates, pre, post):
        query = case['query']
        self.validate_candidates(query, candidates)
        candidate_ids = {c['doc_id'] for c in candidates}
        for ranked in (pre, post):
            if len(ranked) != len(set(ranked)) or not set(ranked).issubset(candidate_ids):
                raise ValueError('评测排序存在重复或候选外ID')
        old_rel = {c['doc_id'] for c in candidates if case['topic'] in c['text']}
        all_new_rel = self.effective[query]
        new_rel = all_new_rel & candidate_ids
        output = {}
        for name, rel in [('old_topic', old_rel), ('new_candidate', new_rel), ('new_child_universe', all_new_rel)]:
            output[name] = {'n_relevant': len(rel), 'relevant_ids': sorted(rel),
                            'pre': binary_metrics(pre, rel), 'post': binary_metrics(post, rel)}
        output['new_child_universe']['candidate_recall'] = len(new_rel) / len(all_new_rel) if all_new_rel else 0.0
        diagnostics = {}
        for name, ranked in [('pre', pre), ('post', post)]:
            top_labels = [self.labels[(query, doc_id)] for doc_id in ranked[:10]]
            diagnostics[name] = {
                'effective_hits': sum(l['is_effective_evidence'] for l in top_labels),
                'background_hits': sum(l['answer_relevance'] == 1 for l in top_labels),
                'not_answering_hits': sum(l['answer_relevance'] == 0 for l in top_labels),
                'uncertain_hits': sum(l['needs_source_review'] for l in top_labels),
                'confirmed_contradiction_hits': sum(l['confirmed_contradiction'] for l in top_labels),
            }
        output['diagnostics'] = diagnostics
        return output


def aggregate_label_comparison(rows):
    output = {}
    for standard in ('old_topic', 'new_candidate', 'new_child_universe'):
        pre = {k: mean(r['label_scores'][standard]['pre'][k] for r in rows) for k in rows[0]['label_scores'][standard]['pre']}
        post = {k: mean(r['label_scores'][standard]['post'][k] for r in rows) for k in pre}
        output[standard] = {'pre': pre, 'post': post, 'delta': {k: post[k] - pre[k] for k in pre}}
    output['candidate_recall_new_child_universe'] = mean(r['label_scores']['new_child_universe']['candidate_recall'] for r in rows)
    return output
