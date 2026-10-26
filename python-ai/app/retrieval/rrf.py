from __future__ import annotations
from typing import Optional, Sequence

def rrf_fuse(results: Sequence, k: int=60, weights: Optional[dict[str, float]]=None) -> list[dict]:
    score_map: dict[str, float] = {}
    item_map: dict[str, dict] = {}
    weights = weights or {}
    for r in results:
        channel = r.channel if hasattr(r, 'channel') else r.get('channel', 'unknown')
        w = float(weights.get(channel, 1.0))
        if hasattr(r, 'doc_ids') and hasattr(r, 'snippets'):
            if not r.doc_ids and r.snippets:
                pairs = [(f'{channel}_{i}', 1.0, sn, r.metadata[i] if i < len(r.metadata) else {}) for i, sn in enumerate(r.snippets)]
            else:
                pairs = list(zip(r.doc_ids, r.scores, r.snippets, r.metadata))
            for rank, (did, score, snippet, meta) in enumerate(pairs, start=1):
                key = str(did) or str(snippet)[:80]
                if not key:
                    continue
                score_map[key] = score_map.get(key, 0.0) + w / (k + rank)
                item_map.setdefault(key, {'doc_id': did, 'channel': channel, 'score': score, 'snippet': snippet, 'metadata': meta if isinstance(meta, dict) else {}})
        elif isinstance(r, dict):
            snippet = r.get('snippet', '')
            key = str(r.get('doc_id', '')) or str(snippet)[:80]
            if not key:
                continue
            rank = len(score_map) + 1
            score_map[key] = score_map.get(key, 0.0) + w / (k + rank)
            item_map.setdefault(key, r)
    ranked = sorted(score_map.items(), key=lambda kv: kv[1], reverse=True)
    items = []
    for key, rrf_score in ranked:
        it = dict(item_map[key])
        it['rrf_score'] = round(rrf_score, 6)
        items.append(it)
    return items
