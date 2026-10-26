from __future__ import annotations
import json
import os
import sys
from datetime import datetime
from app.eval.retrieval_bench import case_text
REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
TOP_K = 10
BENCH_CHUNK_SIZE = 200
BENCH_OVERLAP = 50
BENCH_PARENT_MIN_CHARS = 400
VALUE_MARKER = '运动'

def _load_grouped_docs() -> dict[str, list[str]]:
    try:
        from app.factory.repository import list_cases, list_guidelines
    except Exception:
        return {}
    grouped: dict[str, list[str]] = {}
    try:
        for g in list_guidelines():
            row = g.model_dump()
            topic = str(row.get('topic') or '').split(',')[0].strip()
            if not topic:
                continue
            grouped.setdefault(topic, []).append(str(row.get('content') or '').strip())
        for c in list_cases():
            row = c.model_dump()
            topic = str(row.get('diagnosis') or '').strip()
            if not topic:
                continue
            grouped.setdefault(topic, []).append(case_text(row))
    except Exception:
        return {}
    return grouped

def _to_long_doc(topic: str, bodies: list[str], doc_idx: int) -> dict:
    subject = f'{topic}管理主题'
    lines = [subject] + [b for b in bodies if b]
    return {'id': f'topic-{doc_idx}', 'source_id': f'topic-{topic}', 'source_level': 1, 'knowledge_version': 'bench', 'content': {'raw_text': '\n'.join(lines)}, 'subject': subject}

def _embed(texts: list[str]) -> list[list[float]]:
    from app.gateway.adapters.embedding import EmbeddingAdapter
    out: list[list[float]] = []
    batch = 32
    for i in range(0, len(texts), batch):
        out.extend(EmbeddingAdapter().embed(texts[i:i + batch]))
    return out

def _cosine_topk(qvec: list[float], mat, texts: list[str], ids: list[str], k: int):
    import numpy as np
    q = np.array(qvec, dtype='float32')
    qn = np.linalg.norm(q)
    if qn > 0:
        q = q / qn
    m = mat / np.maximum(np.linalg.norm(mat, axis=1, keepdims=True), 1e-09)
    sims = m @ q
    order = np.argsort(-sims)[:k]
    return [{'id': ids[i], 'snippet': texts[i], 'score': float(sims[i])} for i in order]

def main():
    dry = '--dry-run' in sys.argv
    if dry:
        print('\n=== 父子 chunk 效果实验 dry-run ===')
        print('语料: 真实健康指南/病历按主题拼成长段落（主题仅首行出现）')
        print(f'切分: chunk_size={BENCH_CHUNK_SIZE} overlap={BENCH_OVERLAP} parent_min_chars={BENCH_PARENT_MIN_CHARS}')
        print('对比: A=子块直出  B=子块检索+父块扩展')
        print('指标: doc_hit@10 / 证据主题完整率 / 干预词完整率 / 平均证据长度')
        print('需要: DATABASE_URL（真实数据）+ SILICONFLOW_API_KEY（真实 embedding）')
        return
    grouped = _load_grouped_docs()
    if not grouped:
        print('[ERROR] 健康知识库为空（health_guidelines / medical_cases 无数据），无法跑父子 chunk 实验。请先 ingest 健康语料并 publish 版本。', file=sys.stderr)
        sys.exit(1)
    if not os.getenv('SILICONFLOW_API_KEY'):
        print('[ERROR] SILICONFLOW_API_KEY 未配置，无法生成真实 embedding。', file=sys.stderr)
        sys.exit(1)
    from app.cache import get_cache
    from app.retrieval.chunk_strategies import expand_to_parent
    from app.retrieval.chunker import build_index_chunks
    get_cache().enabled = False
    print('\n=== 父子 chunk 效果实验（真实数据 + 真实 embedding）===\n')
    long_docs = []
    for i, (topic, bodies) in enumerate(grouped.items()):
        doc = _to_long_doc(topic, bodies, i)
        if len(doc['content']['raw_text']) >= BENCH_PARENT_MIN_CHARS:
            long_docs.append(doc)
    print(f'  语料: {len(grouped)} 个主题，其中 {len(long_docs)} 个构成长文档')
    if not long_docs:
        print(f'[ERROR] 没有足够长的主题文档（>= {BENCH_PARENT_MIN_CHARS} 字），无法触发切分。', file=sys.stderr)
        sys.exit(1)
    chunks_all: list = []
    parents: dict[str, str] = {}
    for d in long_docs:
        cs, ps = build_index_chunks([d], embed_fn=_embed, use_parent_child=True, chunk_size=BENCH_CHUNK_SIZE, overlap=BENCH_OVERLAP, parent_min_chars=BENCH_PARENT_MIN_CHARS)
        chunks_all.extend(cs)
        parents.update(ps)
    children = [c for c in chunks_all if c.role == 'child']
    multi = [c for c in children if c.strategy in ('semantic_split', 'semantic_window')]
    child_parent_of = {c.index_key: c.parent_key for c in children if c.parent_key}
    print(f'  切分: 父块 {len(parents)} 个 / 子块 {len(children)} 个（其中被切分的 {len(multi)} 个）')
    if not multi:
        print('[ERROR] 样本不足以触发切分（无 semantic_window 子块）。', file=sys.stderr)
        sys.exit(1)
    print('  向量化子块 ...')
    child_texts = [c.text for c in children]
    child_ids = [c.index_key for c in children]
    child_vecs = _embed(child_texts)
    import numpy as np
    child_mat = np.array(child_vecs, dtype='float32')
    queries: list[dict] = []
    for doc in long_docs:
        lines = doc['content']['raw_text'].split('\n')
        body = lines[1:]
        if not body:
            continue
        pick = sorted({0, len(body) // 2, len(body) - 1})
        for li in pick:
            line = body[li]
            bucket = 'head' if li == 0 else 'tail' if li == len(body) - 1 else 'mid'
            queries.append({'query': f"{doc['subject']} {line[:10]}", 'subject': doc['subject'], 'doc_id': doc['id'], 'pos': li, 'bucket': bucket})
    print(f'  查询: {len(queries)} 条（每文档覆盖前/中/尾三行，后缀行的主题标识只出现在父块首行）\n')
    q_vecs = _embed([q['query'] for q in queries])
    sums = {m: {'subject_rate': 0.0, 'value_rate': 0.0, 'doc_hit': 0.0, 'n_target': 0.0, 'chars': 0.0} for m in ('child', 'parent')}
    bucket_acc: dict[str, dict] = {}
    per_query = []
    n = 0
    for q, qvec in zip(queries, q_vecs):
        ranked = _cosine_topk(qvec, child_mat, child_texts, child_ids, TOP_K)
        ev_child = ranked
        ev_parent = expand_to_parent(ranked, parents, child_of=child_parent_of)

        def _doc_hit(evidence):
            for e in evidence:
                if str(e['id']).rsplit(':', 1)[0] == q['doc_id']:
                    return 1.0
            return 0.0

        def _target_rate(evidence, needle, doc_id):
            targets = [e for e in evidence if str(e.get('id', '')).rsplit(':', 1)[0] == doc_id]
            if not targets:
                return 0.0
            hit = sum((1 for e in targets if needle in str(e.get('snippet', ''))))
            return hit / len(targets)

        def _n_target(evidence, doc_id):
            return sum((1 for e in evidence if str(e.get('id', '')).rsplit(':', 1)[0] == doc_id))
        m_child = {'subject_rate': _target_rate(ev_child, q['subject'], q['doc_id']), 'value_rate': _target_rate(ev_child, VALUE_MARKER, q['doc_id']), 'doc_hit': _doc_hit(ev_child), 'n_target': float(_n_target(ev_child, q['doc_id'])), 'chars': round(sum((len(str(e.get('snippet', ''))) for e in ev_child)) / max(len(ev_child), 1), 1)}
        m_parent = {'subject_rate': _target_rate(ev_parent, q['subject'], q['doc_id']), 'value_rate': _target_rate(ev_parent, VALUE_MARKER, q['doc_id']), 'doc_hit': _doc_hit(ev_parent), 'n_target': float(_n_target(ev_parent, q['doc_id'])), 'chars': round(sum((len(str(e.get('snippet', ''))) for e in ev_parent)) / max(len(ev_parent), 1), 1)}
        for key in sums['child']:
            sums['child'][key] += m_child[key]
            sums['parent'][key] += m_parent[key]
        b = q.get('bucket', 'mid')
        bucket_acc.setdefault(b, {'child': {'subject_rate': 0.0, 'n': 0}, 'parent': {'subject_rate': 0.0, 'n': 0}})
        bucket_acc[b]['child']['subject_rate'] += m_child['subject_rate']
        bucket_acc[b]['child']['n'] += 1
        bucket_acc[b]['parent']['subject_rate'] += m_parent['subject_rate']
        bucket_acc[b]['parent']['n'] += 1
        n += 1
        per_query.append({'query': q['query'], 'bucket': b, 'child': m_child, 'parent': m_parent})
    if n == 0:
        print('[ERROR] 无有效查询。', file=sys.stderr)
        sys.exit(1)

    def avg(mode: str) -> dict:
        return {k: round(v / n, 4) for k, v in sums[mode].items()}
    a_child, a_parent = (avg('child'), avg('parent'))
    print(f'  共 {n} 条查询，平均指标（top-{TOP_K} 证据）:\n')
    print(f"  {'指标':<26}{'A. 子块直出':>14}{'B. 父块扩展':>14}")
    for label, key in (('目标证据含主题标识比例', 'subject_rate'), ('目标证据含干预词比例', 'value_rate'), ('目标文档命中率', 'doc_hit'), ('top-K 内目标证据条数', 'n_target'), ('平均证据长度(字符)', 'chars')):
        print(f'  {label:<26}{a_child[key]:>14.3f}{a_parent[key]:>14.3f}')
    by_bucket = {}
    print(f"\n  {'按目标行位置分桶':<26}{'样本':>6}{'A 子块':>10}{'B 父块':>10}")
    for bk in ('head', 'mid', 'tail'):
        acc = bucket_acc.get(bk)
        if not acc or not acc['child']['n']:
            continue
        cn, pn = (acc['child']['n'], acc['parent']['n'])
        c_rate = round(acc['child']['subject_rate'] / cn, 3)
        p_rate = round(acc['parent']['subject_rate'] / pn, 3)
        by_bucket[bk] = {'n': cn, 'child_subject_rate': c_rate, 'parent_subject_rate': p_rate}
        print(f'  {bk:<26}{cn:>6}{c_rate:>10.3f}{p_rate:>10.3f}')
    report = {'benchmark': 'parent_child_chunk', 'question': '子块检索 vs 子块检索+父块扩展（证据主题完整性）', 'num_queries': n, 'num_parents': len(parents), 'num_children': len(children), 'chunk_size': BENCH_CHUNK_SIZE, 'overlap': BENCH_OVERLAP, 'parent_min_chars': BENCH_PARENT_MIN_CHARS, 'child_only': a_child, 'parent_expanded': a_parent, 'by_position': by_bucket, 'per_query': per_query, 'insight': f"长文档（主题标识只在首行出现）被定长窗口切开后，后续子块**丢失主语**：目标证据含主题标识的比例，子块直出仅 {a_child['subject_rate']:.1%}，父子扩展后 {a_parent['subject_rate']:.1%}；目标文档命中率两者相同（{a_child['doc_hit']:.1%}）——扩展不改变召回范围，改变的是**送进精排/LLM 的证据质量**（是否带主语与完整字段），这正是'证据可追溯 + 不张冠李戴'的前提。代价：平均证据长度 {a_child['chars']:.0f} 字 → {a_parent['chars']:.0f} 字，生产上只对命中的目标证据做一次父块替换，token 增量可控。", 'timestamp': datetime.now().isoformat(timespec='seconds')}
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f'parent_child_bench_{datetime.now():%Y%m%d}.json')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n报告已落库: {path}')
    except PermissionError:
        alt = f'/tmp/parent_child_bench_{datetime.now():%Y%m%d}.json'
        with open(alt, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n报告落库到项目目录被拒（只读），已写 /tmp: {alt}')
if __name__ == '__main__':
    main()
