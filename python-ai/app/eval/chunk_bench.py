from __future__ import annotations
import json
import logging
import os
import sys
from datetime import datetime
from app.eval.retrieval_bench import HEALTH_METRICS, _BM25, metric_text
from app.retrieval.chunk_strategies import chunk_fixed_length, chunk_fixed_symbol, chunk_semantic_by_similarity, chunk_sliding_window
logger = logging.getLogger(__name__)
REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
CHUNK_MAX = 400
_NOISE_TEXTS = ['体检报告首页信息：姓名、性别、年龄、体检编号、体检日期、体检机构', '本报告仅反映本次检查结果，如有异常请结合临床由医生综合判断', '检验结果受采样时间、饮食、运动等因素影响，建议定期复查', '参考区间依据本机构检验方法设定，不同机构可能存在差异', '异常结果建议至相应专科门诊进一步诊治，切勿自行用药'] * 6

def _load_real_rows() -> list[dict]:
    try:
        from app.factory.repository import list_metric_catalog
        rows = [m.model_dump() for m in list_metric_catalog()]
    except Exception:
        return []
    return rows

def _mock_rows() -> list[dict]:
    return [dict(m) for m in HEALTH_METRICS]
_REAL_DATA: list[dict] | None = None
_USING_REAL: bool = False

def _build_rows() -> list[dict]:
    global _REAL_DATA, _USING_REAL
    if _REAL_DATA is None:
        real = _load_real_rows()
        _USING_REAL = bool(real)
        _REAL_DATA = real or _mock_rows()
    return _REAL_DATA

def _row_text(row: dict) -> str:
    return metric_text(row)

def _naturalized_rows() -> list[str]:
    return [_row_text(r) for r in _build_rows()]

def _ref_marker(row: dict) -> str:
    if row.get('ref_text'):
        return str(row['ref_text'])
    for key in ('ref_high', 'ref_low'):
        if row.get(key) is not None:
            return str(row[key])
    return ''

def _make_embed_fn():
    try:
        from app.gateway.adapters.embedding import EmbeddingAdapter
        adapter = EmbeddingAdapter()
    except Exception as e:
        logger.warning('[chunk_bench] Embedding 适配器不可用：%s', e)
        return None

    def _fn(texts):
        return adapter.embed([t if t and t.strip() else ' ' for t in texts])
    return _fn

def _build_corpus(strategy: str) -> list[str]:
    rows = _build_rows()
    noise = list(_NOISE_TEXTS)
    if strategy == 'baseline':
        full = '\n'.join(_naturalized_rows() + noise)
        return [full[:CHUNK_MAX]]
    if strategy == 'fixed_length':
        full = '\n'.join(_naturalized_rows() + noise)
        return chunk_fixed_length(full, chunk_size=CHUNK_MAX)
    if strategy == 'fixed_symbol':
        full = '\n'.join(_naturalized_rows() + noise)
        return chunk_fixed_symbol(full, chunk_size=CHUNK_MAX)
    if strategy == 'semantic_split':
        full = '\n'.join(_naturalized_rows() + noise)
        embed_fn = _make_embed_fn()
        if embed_fn is None:
            raise RuntimeError('语义切分需要 Embedding API，当前不可用')
        return chunk_semantic_by_similarity(full, embed_fn=embed_fn, chunk_size=CHUNK_MAX, overlap=64)
    if strategy == 'semantic_window':
        full = '\n'.join(_naturalized_rows() + noise)
        return chunk_sliding_window(full, chunk_size=CHUNK_MAX, overlap=64)
    if strategy == 'structured_row':
        return [_row_text(r) for r in rows]
    raise ValueError(strategy)

def _build_queries() -> list[tuple[str, str, str]]:
    rows = _build_rows()
    queries: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for r in rows:
        code = r.get('metric_code', '')
        if not code or code in seen:
            continue
        seen.add(code)
        queries.append((f"{r.get('name_cn', '')} {r.get('category', '')} 参考区间", r.get('name_cn', ''), _ref_marker(r)))
    return queries[::3] + queries[1::3] + queries[2::3]

def _relevant(text: str, name: str, marker: str) -> bool:
    return bool(name) and name in text and (not marker or marker in text)

def run_bench() -> dict:
    strategies = ['baseline', 'fixed_length', 'fixed_symbol', 'semantic_window', 'semantic_split', 'structured_row']
    results: dict[str, dict] = {}
    queries = _build_queries()
    for strategy in strategies:
        try:
            corpus = _build_corpus(strategy)
        except Exception as e:
            logger.warning('[chunk_bench] 策略 %s 跳过：%s', strategy, e)
            results[strategy] = {'status': 'skipped', 'reason': str(e)}
            continue
        bm25 = _BM25(corpus)
        recall_5, mrr_sum, hit_1 = (0, 0.0, 0)
        for query, name, marker in queries:
            scored = sorted(((bm25.score(query, d), i, d) for i, d in enumerate(corpus)), key=lambda x: x[0], reverse=True)
            top5 = [d for _, _, d in scored[:5]]
            if any((_relevant(d, name, marker) for d in top5)):
                recall_5 += 1
            for rank, (_, _, d) in enumerate(scored, 1):
                if _relevant(d, name, marker):
                    mrr_sum += 1.0 / rank
                    if rank == 1:
                        hit_1 += 1
                    break
        n = max(len(queries), 1)
        results[strategy] = {'num_chunks': len(corpus), 'num_queries': len(queries), 'recall@5': round(recall_5 / n, 3), 'mrr': round(mrr_sum / n, 3), 'hit@1': round(hit_1 / n, 3)}
    return {'benchmark': 'chunk_strategy', 'strategies': results, 'chunk_max': CHUNK_MAX, 'timestamp': datetime.now().isoformat(timespec='seconds')}

def main():
    report = run_bench()
    rows = _build_rows()
    mode = '真实 metric_catalog' if _USING_REAL else '自包含健康指标语料'
    if '--json' in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print('\n=== Chunk 策略对比（亮点2）===')
        print(f'语料: {len(rows)} 条指标行（{mode}） + {len(_NOISE_TEXTS)} 干扰项, chunk 上限 {CHUNK_MAX} 字符（超限截断）\n')
        print(f"{'策略':<16}{'chunks':>7}{'Recall@5':>10}{'MRR':>8}{'Hit@1':>8}")
        for name, r in report['strategies'].items():
            print(f"{name:<16}{r['num_chunks']:>7}{r['recall@5']:>10}{r['mrr']:>8}{r['hit@1']:>8}")
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f'chunk_bench_{datetime.now():%Y%m%d}.json')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n报告已落库: {path}')
    except PermissionError:
        alt = f'/tmp/chunk_bench_{datetime.now():%Y%m%d}.json'
        with open(alt, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
        print(f'\n报告落库到项目目录被拒（只读），已写 /tmp: {alt}')
if __name__ == '__main__':
    main()
