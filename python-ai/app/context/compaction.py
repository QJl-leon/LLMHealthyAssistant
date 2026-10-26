from __future__ import annotations
import logging
import os
import re
from typing import Any, Optional
logger = logging.getLogger(__name__)
COMPACTION_TRIGGER_TOKENS = int(os.getenv('COMPACTION_TRIGGER_TOKENS', '8000'))
COMPACTION_ENABLED = os.getenv('COMPACTION_ENABLED', 'true').lower() in ('1', 'true', 'yes')
COMPACTION_EVIDENCE_KEEP = int(os.getenv('COMPACTION_EVIDENCE_KEEP', '10'))
_CHARS_PER_TOKEN = 1.5
_NUM_RE = re.compile('\\d+(?:\\.\\d+)?')

def estimate_tokens(text: str) -> int:
    if not text:
        return 0
    return int(len(text) / _CHARS_PER_TOKEN) + 1

def extract_numbers(text: str) -> set[str]:
    return set(_NUM_RE.findall(text or ''))

def should_compact(*texts: str, trigger_tokens: Optional[int]=None) -> bool:
    if not COMPACTION_ENABLED:
        return False
    threshold = trigger_tokens if trigger_tokens is not None else COMPACTION_TRIGGER_TOKENS
    total = sum((estimate_tokens(t) for t in texts))
    return total > threshold

def compact_evidence(evidence: list[dict], *, cited_ids: Optional[set[str]]=None, keep_top: int=COMPACTION_EVIDENCE_KEEP) -> tuple[list[dict], dict]:
    evidence = [e for e in evidence or [] if isinstance(e, dict)]
    if not evidence:
        return ([], {'before': 0, 'after': 0, 'dropped': 0})
    if cited_ids is not None:
        cited = {str(x) for x in cited_ids if x}
        kept = [e for e in evidence if str(e.get('evidence_id') or '') in cited]
        dropped = [e for e in evidence if str(e.get('evidence_id') or '') not in cited]
    else:
        kept = list(evidence[:keep_top])
        dropped = list(evidence[keep_top:])
    out = list(kept)
    if dropped:
        dist: dict[str, int] = {}
        for e in dropped:
            key = str(e.get('source_type') or e.get('channel') or 'unknown')
            dist[key] = dist.get(key, 0) + 1
        dist_text = '、'.join((f'{k} {v} 条' for k, v in sorted(dist.items())))
        out.append({'evidence_id': '', 'evidence_type': 'compaction_summary', 'channel': 'compaction', 'quote': f'（另有 {len(dropped)} 条未引用证据已压缩：{dist_text}）', 'source_name': 'compaction_summary', 'source_url': '', 'compacted': True, 'compacted_count': len(dropped)})
    stats = {'before': len(evidence), 'after': len(out), 'dropped': len(dropped), 'kept': len(kept)}
    logger.info('[Compaction] 证据层: %d → %d（保留 %d，压缩摘要 %d）', stats['before'], stats['after'], stats['kept'], stats['dropped'])
    return (out, stats)

def compact_observations(observations: list[dict]) -> tuple[list[dict], dict]:
    observations = [o for o in observations or [] if isinstance(o, dict)]
    if not observations:
        return ([], {'before': 0, 'after': 0, 'merged': 0, 'conflicts': 0})
    metric_groups: dict[str, list[dict]] = {}
    passthrough: list[dict] = []
    for obs in observations:
        name = str(obs.get('metric_name') or '').strip()
        if obs.get('type') == 'metric' and name:
            metric_groups.setdefault(name, []).append(obs)
        else:
            passthrough.append(obs)
    merged: list[dict] = []
    merged_count = 0
    conflict_count = 0
    for name, group in metric_groups.items():
        values = {str(g.get('value') or g.get('value_text') or '') for g in group}
        if len(group) > 1 and len(values) == 1:
            head = dict(group[0])
            head['merged_count'] = len(group)
            merged.append(head)
            merged_count += len(group) - 1
        elif len(values) > 1:
            for g in group:
                g2 = dict(g)
                g2['conflict'] = True
                g2['conflict_note'] = f'指标「{name}」存在 {len(values)} 个不同取值'
                merged.append(g2)
            conflict_count += 1
        else:
            merged.extend(group)
    out = passthrough + merged
    stats = {'before': len(observations), 'after': len(out), 'merged': merged_count, 'conflicts': conflict_count}
    logger.info('[Compaction] 观察层: %d → %d（合并 %d，冲突 %d 组）', stats['before'], stats['after'], stats['merged'], stats['conflicts'])
    return (out, stats)

def compact_discussion(claims: list[dict], errors: list[dict], *, keep_errors: int=10) -> tuple[list[dict], list[dict], dict]:
    claims = [c for c in claims or [] if isinstance(c, dict)]
    errors = [e for e in errors or [] if isinstance(e, dict)]
    slim_claims = [{'claim_id': str(c.get('claim_id') or ''), 'metric_code': str(c.get('metric_code') or ''), 'type': str(c.get('type') or ''), 'text': str(c.get('text') or ''), 'evidence_ids': [str(x) for x in c.get('evidence_ids') or [] if x]} for c in claims]
    kept_errors = errors[-keep_errors:] if len(errors) > keep_errors else list(errors)
    slim_errors = [{'error_code': str(e.get('error_code') or ''), 'message': str(e.get('message') or ''), 'claim_id': str(e.get('claim_id') or '')} for e in kept_errors]
    if len(errors) > keep_errors:
        slim_errors.insert(0, {'error_code': 'COMPACTION_SUMMARY', 'message': f'（更早的 {len(errors) - keep_errors} 条错误已压缩）', 'claim_id': ''})
    stats = {'claims_before': len(claims), 'claims_after': len(slim_claims), 'errors_before': len(errors), 'errors_after': len(slim_errors)}
    logger.info('[Compaction] 讨论层: claims %d→%d, errors %d→%d', stats['claims_before'], stats['claims_after'], stats['errors_before'], stats['errors_after'])
    return (slim_claims, slim_errors, stats)

def compact_state(state: dict, *, cited_ids: Optional[set[str]]=None, trigger_tokens: Optional[int]=None) -> tuple[dict, dict]:
    out = dict(state)
    report: dict[str, Any] = {'triggered': False}
    evidence = out.get('evidence') or []
    observations = out.get('image_observations') or []
    claims = out.get('validated_claims') or []
    errors = out.get('errors') or []
    total_text = ''.join((str(e.get('quote') or '') for e in evidence if isinstance(e, dict))) + ''.join((str(o.get('text') or '') for o in observations if isinstance(o, dict))) + ''.join((str(c.get('text') or '') for c in claims if isinstance(c, dict)))
    if not should_compact(total_text, trigger_tokens=trigger_tokens):
        logger.info('[Compaction] 未达触发阈值，跳过')
        return (out, report)
    report['triggered'] = True
    new_evidence, ev_stats = compact_evidence(evidence, cited_ids=cited_ids)
    out['evidence'] = new_evidence
    report['evidence'] = ev_stats
    new_obs, obs_stats = compact_observations(observations)
    out['image_observations'] = new_obs
    report['observations'] = obs_stats
    new_claims, new_errors, dis_stats = compact_discussion(claims, errors)
    out['validated_claims'] = new_claims
    out['errors'] = new_errors
    report['discussion'] = dis_stats
    logger.info('[Compaction] state 压缩完成: %s', report)
    return (out, report)
