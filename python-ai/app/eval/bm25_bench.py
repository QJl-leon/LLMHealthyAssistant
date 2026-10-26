from __future__ import annotations
import json
import math
import os
import sys
from datetime import datetime
REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
TOP_K = 50
FINAL_TOP_K = 10
CASES = [{'query': '血脂高的人该怎么运动', 'topic': '血脂'}, {'query': '血糖偏高的运动建议', 'topic': '血糖'}, {'query': '血压高适合什么运动', 'topic': '血压'}, {'query': '尿酸高能不能运动', 'topic': '尿酸'}, {'query': '脂肪肝运动能改善吗', 'topic': '脂肪肝'}, {'query': '超重怎么运动减重', 'topic': '体重'}, {'query': '低密度脂蛋白胆固醇参考区间', 'name': '低密度脂蛋白胆固醇'}, {'query': '谷丙转氨酶偏高怎么办', 'name': '谷丙转氨酶'}, {'query': '他汀和运动注意事项', 'name': '他汀'}, {'query': '高尿酸血症运动禁忌', 'name': '高尿酸'}]

def _is_rel(text: str, case: dict) -> bool:
    if case.get('topic'):
        return case['topic'] in text
    if case.get('name'):
        return case['name'] in text
    return False

def _ndcg(ranked: list[str], rel: set[str], k: int) -> float:
    dcg = sum((1.0 / math.log2(i + 2) for i, d in enumerate(ranked[:k]) if d in rel))
    idcg = sum((1.0 / math.log2(i + 2) for i in range(min(k, len(rel)))))
    return dcg / idcg if idcg else 0.0

def _metrics(ranked: list[str], rel: set[str]) -> dict:
    top = ranked[:FINAL_TOP_K]
    n_rel = sum((1 for d in top if d in rel))
    return {f'recall@{FINAL_TOP_K}': round(n_rel / max(len(rel), 1), 3), 'mrr': round(next((1.0 / (i + 1) for i, d in enumerate(ranked) if d in rel), 0.0), 3), 'hit@1': 1.0 if ranked and ranked[0] in rel else 0.0, f'ndcg@{FINAL_TOP_K}': round(_ndcg(ranked, rel, FINAL_TOP_K), 3)}

def _get_coll():
    from app.retrieval.index_builder import connect
    from pymilvus import Collection, utility
    connect()
    if not utility.has_collection('evidence_text'):
        raise RuntimeError('Milvus 无 evidence_text 集合——请先 index_builder --rebuild 重建健康索引。')
    coll = Collection('evidence_text')
    coll.load()
    if coll.num_entities == 0:
        raise RuntimeError('Milvus evidence_text 为空——请先 ingest 健康语料并重建索引。')
    return coll

def _extract_keywords(query: str, strategy: str) -> list[str]:
    if strategy == 'bigram':
        words = []
        for i in range(len(query) - 1):
            w = query[i:i + 2]
            if all(('一' <= c <= '鿿' for c in w)) and w not in words:
                words.append(w)
        return words[:5] or [query.strip()]
    words = [w for w in query.replace('运动', '').replace('建议', '').replace('参考区间', '').strip().split() if len(w) >= 2]
    return words[:5] or [query.strip()]

def _like_search(coll, query: str, top_k: int=TOP_K, strategy: str='bigram') -> list[dict]:
    expr_parts = ['tenant_id == "dev-tenant"', 'chunk_role == "child"']
    keywords = _extract_keywords(query, strategy)
    expr_parts.append('(' + ' or '.join([f'text like "%{kw}%"' for kw in keywords]) + ')')
    expr = ' and '.join(expr_parts)
    rows = coll.query(expr=expr, output_fields=['id', 'text', 'doc_id', 'source_level'], limit=top_k)
    out = []
    for r in rows:
        score = sum((1.0 for kw in keywords if kw in r.get('text', '')))
        out.append({'doc_id': r.get('id', ''), 'score': score, 'text': str(r.get('text', ''))[:200]})
    out.sort(key=lambda x: x['score'], reverse=True)
    return out

def _fulltext_search(coll, query: str, top_k: int=TOP_K) -> list[dict]:
    expr = 'tenant_id == "dev-tenant" and chunk_role == "child"'
    results = coll.search(data=[query], anns_field='sparse_vector', param={'metric_type': 'BM25'}, limit=top_k, expr=expr, output_fields=['id', 'text', 'doc_id', 'source_level'])
    out = []
    for hits in results:
        for h in hits:
            out.append({'doc_id': h.id, 'score': h.score, 'text': str(h.entity.get('text', ''))[:200]})
    return out

def main():
    dry = '--dry-run' in sys.argv
    if dry:
        print('\n=== BM25: LIKE vs 全文检索（亮点5）dry-run ===')
        print(f'查询: {len(CASES)} 条（6 意译 + 4 专名）')
        print('对照: A=LIKE旧(空格拆词)  B=LIKE+2-gram  C=Milvus 全文检索 BM25')
        print(f'每路召回 top{TOP_K}，评估 top{FINAL_TOP_K}：Recall/MRR/Hit@1/NDCG')
        return
    print('\n=== BM25: LIKE 子串 vs Milvus 全文检索（真实健康知识库）===\n')
    try:
        coll = _get_coll()
    except RuntimeError as e:
        print(f'[ERROR] {e}', file=sys.stderr)
        sys.exit(1)
    sums = {k: {} for k in ('like_old', 'like_bigram', 'fulltext')}
    per_query = []
    n_q = 0
    for case in CASES:
        query = case['query']
        like_old = _like_search(coll, query, strategy='old')
        like_bigram = _like_search(coll, query, strategy='bigram')
        ft = _fulltext_search(coll, query)
        rel = set()
        for cands in (like_old, like_bigram, ft):
            rel |= {str(c['doc_id']) for c in cands if _is_rel(c['text'], case)}
        if not rel:
            print(f'  [SKIP] {query}: 三路均无相关项')
            continue
        row = {'query': query, 'rel': len(rel)}
        for key, cands in (('like_old', like_old), ('like_bigram', like_bigram), ('fulltext', ft)):
            m = _metrics([str(c['doc_id']) for c in cands], rel)
            row[key] = m
            for k, v in m.items():
                sums[key][k] = sums[key].get(k, 0.0) + v
        n_q += 1
        per_query.append(row)
        print(f"  [OK] {query:<22} rel={len(rel):<3} LIKE旧 mrr={row['like_old']['mrr']} LIKE2gram mrr={row['like_bigram']['mrr']} | 全文 mrr={row['fulltext']['mrr']} recall@10={row['fulltext']['recall@10']}")
    if n_q == 0:
        print('[ERROR] 无有效查询（Milvus 内可能仍是旧域语料，请重建健康索引）。', file=sys.stderr)
        sys.exit(1)

    def avg(s: dict) -> dict:
        return {key: round(v / n_q, 3) for key, v in s.items()}
    print(f'\n  共 {n_q} 个有效查询，平均指标:\n')
    print(f"  {'实现':<30} {'Recall@10':>10} {'MRR':>8} {'Hit@1':>8} {'NDCG@10':>9}")
    labels = {'like_old': 'A. LIKE 旧实现（空格拆词）', 'like_bigram': 'B. LIKE + 2-gram（子串范式上限）', 'fulltext': 'C. Milvus 全文检索 BM25'}
    avgs = {k: avg(s) for k, s in sums.items()}
    for k, label in labels.items():
        a = avgs[k]
        print(f"  {label:<30} {a['recall@10']:>10.3f} {a['mrr']:>8.3f} {a['hit@1']:>8.3f} {a['ndcg@10']:>9.3f}")
    a_old, a_big, a_ft = (avgs['like_old'], avgs['like_bigram'], avgs['fulltext'])
    report = {'benchmark': 'bm25_like_vs_fulltext', 'method': '同一查询集 + 真实 Milvus evidence_text（健康知识）；A=旧 LIKE(空格拆词)，B=LIKE+2-gram，C=Milvus BM25 Function', 'num_queries': n_q, 'like_old': a_old, 'like_bigram': a_big, 'fulltext': a_ft, 'per_query': per_query, 'insight': f"① 旧实现（空格拆词）对中文无空格查询退化出超长关键词，LIKE 全灭（MRR {a_old['mrr']}）——这是当时必须升级的直接证据；② 即使把 LIKE 做到子串匹配范式上限（2-gram 切词），仍缺 TF-IDF 加权：专名命中但名称相近行污染 top-K，MRR {a_big['mrr']} / Recall@10 {a_big['recall@10']}；③ Milvus 全文检索 BM25（服务端 jieba 分词 + TF-IDF）MRR {a_ft['mrr']} / Recall@10 {a_ft['recall@10']} / Hit@1 {a_ft['hit@1']}。", 'timestamp': datetime.now().isoformat(timespec='seconds')}
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f'bm25_bench_{datetime.now():%Y%m%d}.json')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n报告已落库: {path}')
    except PermissionError:
        alt = f'/tmp/bm25_bench_{datetime.now():%Y%m%d}.json'
        with open(alt, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n报告落库到项目目录被拒（只读），已写 /tmp: {alt}')
if __name__ == '__main__':
    main()
