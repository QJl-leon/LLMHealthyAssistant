from __future__ import annotations
import json
import math
import os
import sys
import time
from datetime import datetime
from app.eval.retrieval_bench import _BM25, case_text, guideline_text, metric_text
REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')

def load_health_corpus() -> list[dict]:
    try:
        from app.factory.repository import list_guidelines, list_cases, list_metric_catalog
    except Exception:
        return []
    docs: list[dict] = []
    try:
        for g in list_guidelines():
            row = g.model_dump()
            docs.append({'id': str(g.id), 'bank': 'guideline', 'name': row.get('title', ''), 'text': guideline_text(row), 'topic': row.get('topic', '')})
        for c in list_cases():
            row = c.model_dump()
            docs.append({'id': str(c.id), 'bank': 'case', 'name': row.get('diagnosis', ''), 'text': case_text(row), 'topic': row.get('diagnosis', '')})
        for m in list_metric_catalog():
            row = m.model_dump()
            docs.append({'id': f'm_{m.metric_code}', 'bank': 'metric_catalog', 'name': row.get('name_cn', ''), 'text': metric_text(row), 'metric_code': m.metric_code})
    except Exception:
        return []
    return docs

def build_queries(corpus: list[dict]) -> list[dict]:
    queries: list[dict] = []
    for d in corpus:
        if d['bank'] == 'guideline' and d.get('topic'):
            topic = d['topic'].split(',')[0].strip()
            if not topic:
                continue
            queries.append({'query': f"{d['name']} 运动 干预 {topic}", 'topic': topic, 'bank': 'guideline'})
        elif d['bank'] == 'case' and d.get('name'):
            diag = d['name']
            key = diag[:4] if len(diag) >= 4 else diag
            queries.append({'query': f'{diag} 运动干预 方案', 'topic': key, 'bank': 'case'})
    for d in corpus:
        if d['bank'] == 'metric_catalog' and d.get('name'):
            queries.append({'query': f"{d['name']} 参考区间 异常", 'topic': d['name'], 'bank': 'metric_catalog'})
    return queries

def _metrics(ranked: list[str], related: set[str], ks=(1, 3, 5, 10)) -> dict:
    out: dict = {}
    rel_positions = [i for i, d in enumerate(ranked) if d in related]
    for k in ks:
        rel_topk = sum((1 for p in rel_positions if p < k))
        out[f'recall@{k}'] = rel_topk / max(len(related), 1)
        out[f'precision@{k}'] = rel_topk / max(min(k, len(ranked)), 1)
        dcg = sum((1.0 / math.log2(p + 2) for p in rel_positions if p < k))
        idcg = sum((1.0 / math.log2(i + 2) for i in range(min(k, len(related)))))
        out[f'ndcg@{k}'] = dcg / idcg if idcg else 0.0
    out['mrr'] = 1.0 / (rel_positions[0] + 1) if rel_positions else 0.0
    out['hit@1'] = 1.0 if rel_positions and rel_positions[0] == 0 else 0.0
    return out

def _dense_vectors(texts: list[str]):
    try:
        from app.gateway.adapters.embedding import EmbeddingAdapter
        return EmbeddingAdapter().embed(texts)
    except Exception as e:
        print(f'  [warn] Dense 通道不可用: {e}', file=sys.stderr)
        return None

def _rank(query: str, corpus: list[dict], bm25: _BM25, dense_mat=None, dense_query=None, mode: str='bm25') -> list[str]:
    docs = [d['text'] for d in corpus]
    ids = [d['id'] for d in corpus]
    bm25_order = sorted(range(len(docs)), key=lambda i: -bm25.score(query, docs[i]))
    if mode == 'bm25' or dense_mat is None or dense_query is None:
        return [ids[i] for i in bm25_order]
    import numpy as np
    q = np.array(dense_query, dtype='float32')
    qn = np.linalg.norm(q)
    if qn > 0:
        q = q / qn
    m = dense_mat / np.maximum(np.linalg.norm(dense_mat, axis=1, keepdims=True), 1e-09)
    dense_order = list(map(int, np.argsort(-(m @ q))))
    if mode == 'dense':
        return [ids[i] for i in dense_order]
    scores: dict[int, float] = {}
    for rank, i in enumerate(bm25_order, 1):
        scores[i] = scores.get(i, 0.0) + 1.0 / (int(os.getenv('REAL_EVAL_RRF_K', '60')) + rank)
    for rank, i in enumerate(dense_order, 1):
        scores[i] = scores.get(i, 0.0) + 1.0 / (int(os.getenv('REAL_EVAL_RRF_K', '60')) + rank)
    return [ids[i] for i, _ in sorted(scores.items(), key=lambda kv: -kv[1])]

def run_real_eval(limit: int | None=None, with_dense: bool=True) -> dict:
    corpus = load_health_corpus()
    if not corpus:
        raise RuntimeError('健康知识库为空（health_guidelines / medical_cases / metric_catalog 无数据）——请先 ingest 健康语料并 publish 版本，再跑 real_eval。')
    queries = build_queries(corpus)
    if limit:
        queries = queries[:limit]
    bm25 = _BM25([d['text'] for d in corpus])
    dense_mat = dense_query_fn = None
    if with_dense and os.getenv('SILICONFLOW_API_KEY'):
        vecs = _dense_vectors([d['text'] for d in corpus])
        if vecs:
            import numpy as np
            dense_mat = np.array(vecs, dtype='float32')
            dense_query_fn = _dense_vectors
    per_query: list[dict] = []
    sums: dict[str, dict[str, float]] = {'bm25': {}, 'dense': {}, 'hybrid': {}}
    empty = 0
    t0 = time.time()
    for q in queries:
        related = {d['id'] for d in corpus if q['topic'] and q['topic'] in d['text']}
        if not related:
            continue
        ranked_bm25 = _rank(q['query'], corpus, bm25, mode='bm25')
        m_bm25 = _metrics(ranked_bm25, related)
        for k, v in m_bm25.items():
            sums['bm25'][k] = sums['bm25'].get(k, 0.0) + v
        row = {'query': q['query'], 'topic': q['topic'], 'bank': q['bank'], 'related_count': len(related), 'bm25': m_bm25}
        if dense_mat is not None and dense_query_fn is not None:
            qv = dense_query_fn([q['query']])
            if qv:
                ranked_dense = _rank(q['query'], corpus, bm25, dense_mat, qv[0], 'dense')
                m_dense = _metrics(ranked_dense, related)
                for k, v in m_dense.items():
                    sums['dense'][k] = sums['dense'].get(k, 0.0) + v
                row['dense'] = m_dense
                ranked_hybrid = _rank(q['query'], corpus, bm25, dense_mat, qv[0], 'hybrid')
                m_hybrid = _metrics(ranked_hybrid, related)
                for k, v in m_hybrid.items():
                    sums['hybrid'][k] = sums['hybrid'].get(k, 0.0) + v
                row['hybrid'] = m_hybrid
        if not ranked_bm25:
            empty += 1
        per_query.append(row)
    n = max(len(per_query), 1)
    aggregated = {name: {k: round(v / n, 4) for k, v in acc.items()} for name, acc in sums.items()}
    aggregated['bm25']['empty_recall_rate'] = round(empty / n, 3)
    return {'rrf_k': int(os.getenv('REAL_EVAL_RRF_K', '60')), 'benchmark': 'real_retrieval_eval', 'method': '独立标注集（查询从指南标题/病历诊断派生）+ 真实 BM25' + ('+Dense+RRF' if dense_mat is not None else '（未配置 Dense）'), 'num_queries': n, 'num_docs': len(corpus), 'duration_sec': round(time.time() - t0, 1), 'aggregated': aggregated, 'per_query': per_query, 'timestamp': datetime.now().isoformat(timespec='seconds')}
HARD_PAIRS: list[tuple[str, list[str]]] = [('低密度脂蛋白胆固醇', ['高密度脂蛋白胆固醇']), ('谷丙转氨酶', ['谷草转氨酶']), ('空腹血糖', ['糖化血红蛋白']), ('收缩压', ['舒张压']), ('尿酸', ['肌酐']), ('总胆固醇', ['甘油三酯']), ('体重指数', ['肌酸激酶'])]

def _hard_metrics(target: str, distractors: list[str], ranked: list[str]) -> dict:
    target_rank = distractor_min_rank = None
    for i, d in enumerate(ranked):
        if d == target and target_rank is None:
            target_rank = i
        if d in distractors and (distractor_min_rank is None or i < distractor_min_rank):
            distractor_min_rank = i
    found = target_rank is not None
    confused = bool(found and distractor_min_rank is not None and (distractor_min_rank < target_rank))
    return {'target_rank': target_rank, 'found': found, 'confused': confused, 'hit1': target_rank == 0}

def run_hard_eval() -> dict:
    corpus = load_health_corpus()
    if not corpus:
        raise RuntimeError('健康知识库为空，无法跑难负例评测（请先 ingest 健康语料）。')
    name_to_id = {d['name']: d['id'] for d in corpus if d.get('name')}
    bm25 = _BM25([d['text'] for d in corpus])
    per: list[dict] = []
    for target, distractors in HARD_PAIRS:
        if target not in name_to_id:
            continue
        ranked = _rank(f'{target} 参考区间', corpus, bm25, mode='bm25')
        target_id = name_to_id[target]
        distractor_ids = [name_to_id[d] for d in distractors if d in name_to_id]
        per.append({'target': target, 'distractors': distractors, 'bm25': _hard_metrics(target_id, distractor_ids, ranked)})
    if not per:
        raise RuntimeError('难负例目标指标均不在知识库中，无法评测（请检查 metric_catalog）。')

    def _mean(field: str) -> float:
        vals = [p['bm25'].get(field) for p in per]
        return round(sum((1.0 if v in (True, 1) else v or 0.0 for v in vals)) / len(vals), 4)

    def _mrr() -> float:
        vals = [1.0 / (p['bm25']['target_rank'] + 1) if p['bm25']['target_rank'] is not None else 0.0 for p in per]
        return round(sum(vals) / len(vals), 4)
    return {'benchmark': 'hard_negative_retrieval_eval', 'method': '易混淆指标对（名称相近），BM25 排序下目标是否先于干扰项', 'num_pairs': len(per), 'bm25': {'hit@1': _mean('hit1'), 'mrr': _mrr(), 'found_rate': _mean('found'), 'confusion_rate': _mean('confused')}, 'per_pair': per, 'timestamp': datetime.now().isoformat(timespec='seconds')}
TOPIC_QUERIES = ['血脂', '血糖', '血压', '运动', '饮食', '睡眠', '代谢', '肾功能']

def run_topic_eval() -> dict:
    corpus = load_health_corpus()
    if not corpus:
        raise RuntimeError('健康知识库为空，无法跑主题语义评测（请先 ingest 健康语料）。')
    bm25 = _BM25([d['text'] for d in corpus])
    per: list[dict] = []
    for topic in TOPIC_QUERIES:
        related = {d['id'] for d in corpus if topic in d['text']}
        if not related:
            continue
        ranked = _rank(topic, corpus, bm25, mode='bm25')
        m = _metrics(ranked, related, ks=(1, 3, 5, 10))
        per.append({'topic': topic, 'gt_count': len(related), **m})
    if not per:
        raise RuntimeError('主题词均未命中知识库内容，无法评测。')

    def _avg(field: str) -> float:
        return round(sum((p[field] for p in per)) / len(per), 4)
    return {'benchmark': 'topic_semantic_retrieval_eval', 'method': '主题语义查询（相关集=含该主题的全部文档），真实 BM25 排序', 'num_queries': len(per), 'aggregated': {f'recall@{k}': _avg(f'recall@{k}') for k in (1, 3, 5, 10)}, 'per_query': per, 'timestamp': datetime.now().isoformat(timespec='seconds')}

def _write_report(report: dict, name: str):
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f'{name}_{datetime.now():%Y%m%d}.json')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'报告已落库: {path}', file=sys.stderr)
    except PermissionError:
        alt = f'/tmp/{name}_{datetime.now():%Y%m%d}.json'
        with open(alt, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'报告落库到项目目录被拒（只读），已写 /tmp: {alt}', file=sys.stderr)

def main():
    argv = sys.argv[1:]
    limit = None
    if '--limit' in argv:
        limit = int(argv[argv.index('--limit') + 1])
    try:
        if '--hard' in argv:
            report = run_hard_eval()
            if '--json' in argv:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print('\n=== 难负例评测（易混淆指标区分，BM25）===\n')
                print(f"难负例对数: {report['num_pairs']}")
                for k, v in report['bm25'].items():
                    print(f'  {k}: {v}')
                print('  （confusion_rate = 干扰项排到目标之前的比例，越低越好）')
        elif '--topic' in argv:
            report = run_topic_eval()
            if '--json' in argv:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print('\n=== 主题语义检索评测（Recall@K）===\n')
                print(f"主题查询数: {report['num_queries']}")
                for k, v in report['aggregated'].items():
                    print(f'  {k}: {v}')
                for p in report['per_query']:
                    print(f"    {p['topic']:<6} gt={p['gt_count']:<3} recall@5={p['recall@5']} mrr={p['mrr']}")
        else:
            report = run_real_eval(limit=limit)
            if '--json' in argv:
                print(json.dumps(report, ensure_ascii=False, indent=2))
            else:
                print('\n=== 真实检索评测（Recall@K / MRR / NDCG）===\n')
                print(f"查询数: {report['num_queries']}（知识库 {report['num_docs']} 条，耗时 {report['duration_sec']}s）")
                for name, agg in report['aggregated'].items():
                    print(f'  [{name}] {agg}')
                print('\n  （Recall@K 分母 = 语料中含目标主题词的文档数；命中判定 = 精确子串，非召回结果反推）')
    except RuntimeError as e:
        print(f'[ERROR] {e}', file=sys.stderr)
        sys.exit(1)
    name = 'real_eval_hard' if '--hard' in argv else 'real_eval_topic' if '--topic' in argv else 'real_eval'
    _write_report(report, name)
if __name__ == '__main__':
    main()
