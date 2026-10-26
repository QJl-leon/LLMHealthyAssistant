#!/usr/bin/env python3
"""Build a reproducible paper retrieval set from verified questions and all 500 exports."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

PROJECT = Path(__file__).resolve().parents[2]
WORKSPACE = PROJECT.parent
DEFAULT_PAPERS = WORKSPACE / '实验2_解析结果/parsed_papers.jsonl'
DEFAULT_HUMAN = PROJECT / 'python-ai/app/eval/datasets/paper_chunk_v1.jsonl'
DEFAULT_OUTPUT = Path(__file__).resolve().parent / 'eval_set_v1.jsonl'


def read_jsonl(path):
    with path.open(encoding='utf-8') as source:
        for number, line in enumerate(source, 1):
            if line.strip():
                try:
                    yield json.loads(line)
                except json.JSONDecodeError as exc:
                    raise ValueError(f'{path}:{number}: invalid JSON') from exc


def sha256(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def choose_excerpt(body, preferred_offset):
    """Choose literal source text; normalization is only for the query display."""
    start = min(preferred_offset, max(0, len(body) - 180))
    window = body[start:start + 3000]
    candidates = []
    for match in re.finditer(r'[^.!?。！？]{85,190}[.!?。！？]', window):
        original = match.group()
        raw = original.strip()
        words = re.findall(r'[A-Za-z]{3,}', raw)
        digits = sum(char.isdigit() for char in raw)
        if (len(words) < 13 or digits > 5 or sum(c.isalpha() for c in raw) < 65
                or re.search(r'https?://|@|copyright|all rights reserved|\d+\s*of\s*\d+', raw, re.I)):
            continue
        offset = start + match.start() + len(original) - len(original.lstrip())
        score = (len(words) - raw.count('\n') * 2 - raw.count('|') * 3
                 - raw.count('  ') * 2)
        candidates.append((score, -offset, raw, offset))
    if candidates:
        _, _, raw, offset = max(candidates)
        return raw, offset
    # PDF extraction can have no useful sentence boundary. Keep a literal slice.
    raw = window[:115]
    if not raw.strip():
        raise ValueError('empty source excerpt')
    return raw, start


def build(papers_path, human_path, expected_papers=500):
    papers = list(read_jsonl(papers_path))
    if len(papers) != expected_papers:
        raise ValueError(f'expected {expected_papers} papers, got {len(papers)}')
    by_pmcid = {}
    ids = set()
    versions = set()
    for paper in papers:
        content = paper.get('content') or {}
        pmcid, doc_id, body = content.get('pmcid'), paper.get('id'), content.get('raw_text')
        if (not pmcid or not doc_id or not isinstance(body, str) or not body.strip()
                or pmcid in by_pmcid or doc_id in ids):
            raise ValueError('paper export contains empty or duplicate identity/body')
        by_pmcid[pmcid] = paper
        ids.add(doc_id)
        versions.add(paper.get('knowledge_version'))
    if len(versions) != 1 or not next(iter(versions)):
        raise ValueError('paper export has inconsistent knowledge versions')
    version = next(iter(versions))

    rows = []
    human_records = list(read_jsonl(human_path))
    manual_ids = set()
    for question in human_records:
        pmcid = question.get('pmcid')
        if pmcid not in by_pmcid or question.get('expected_doc_id') != by_pmcid[pmcid]['id']:
            raise ValueError(f'human question has unknown or mismatched PMCID: {pmcid}')
        if question.get('id') in manual_ids:
            raise ValueError('duplicate human question ID')
        manual_ids.add(question['id'])
        for language, key in (('zh', 'query_zh'), ('en', 'query_en')):
            query = question.get(key)
            if not isinstance(query, str) or not query.strip():
                raise ValueError(f'{question["id"]} missing {key}')
            rows.append({
                'id': f'{question["id"]}_{language}', 'suite': 'human',
                'language': language, 'query': query, 'pmcid': pmcid,
                'expected_doc_id': question['expected_doc_id'], 'knowledge_version': version,
                'source_set': question.get('source_set'), 'topic': question.get('topic'),
                'file_format': question.get('file_format'), 'title': question.get('title'),
                'evidence_page': question.get('evidence_page'),
                'evidence_anchor': question.get('evidence_anchor'),
                'expected_answer_zh': question.get('expected_answer_zh'),
                'anchor_in_export': (question.get('evidence_anchor') or '')
                in by_pmcid[pmcid]['content']['raw_text'],
            })

    for index, pmcid in enumerate(sorted(by_pmcid)):
        paper = by_pmcid[pmcid]
        content = paper['content']
        body = content['raw_text']
        raw, offset = choose_excerpt(body, 2500 if index % 2 == 0 else 8000)
        passage = ' '.join(raw.split())
        if not passage or raw not in body:
            raise ValueError(f'cannot locate excerpt in {pmcid}')
        rows.append({
            'id': f'coverage_{pmcid}', 'suite': 'coverage', 'language': 'en',
            'query': f'Find the paper containing this passage: "{passage}"',
            'pmcid': pmcid, 'expected_doc_id': paper['id'],
            'knowledge_version': version, 'source_set': None,
            'topic': content.get('topic'), 'file_format': None,
            'title': content.get('title'), 'evidence_anchor': raw,
            'anchor_offset': offset, 'depth': 'late' if offset >= 6000 else 'early',
        })
    if len({row['id'] for row in rows}) != len(rows):
        raise ValueError('duplicate test-case ID')
    return rows, {
        'schema_version': 1, 'knowledge_version': version, 'papers': len(papers),
        'human_questions': len(human_records), 'human_query_variants': len(human_records) * 2,
        'coverage_queries': len(papers),
        'coverage_depth': dict(Counter(row['depth'] for row in rows if row['suite'] == 'coverage')),
        'human_anchors_in_export': sum(row['anchor_in_export'] for row in rows
                                       if row['suite'] == 'human' and row['language'] == 'en'),
        'inputs': {'papers': str(papers_path.resolve()), 'papers_sha256': sha256(papers_path),
                   'human': str(human_path.resolve()), 'human_sha256': sha256(human_path)},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--papers', type=Path, default=DEFAULT_PAPERS)
    parser.add_argument('--human', type=Path, default=DEFAULT_HUMAN)
    parser.add_argument('--output', type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument('--expected-papers', type=int, default=500)
    parser.add_argument('--force', action='store_true', help='explicitly replace an existing test set')
    args = parser.parse_args(argv)
    if args.expected_papers <= 0:
        parser.error('expected-papers must be positive')
    rows, meta = build(args.papers, args.human, args.expected_papers)
    target = args.output.resolve()
    sidecar = target.with_suffix('.meta.json')
    if not args.force and (target.exists() or sidecar.exists()):
        parser.error('output already exists; use --force to regenerate intentionally')
    target.parent.mkdir(parents=True, exist_ok=True)
    meta['test_set_sha256'] = hashlib.sha256(
        ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows).encode('utf-8')
    ).hexdigest()
    temporary = target.with_suffix('.jsonl.tmp')
    temporary.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows),
                         encoding='utf-8')
    temporary.replace(target)
    sidecar.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'test_set': str(target), 'metadata': str(sidecar), **{
        key: meta[key] for key in ('papers', 'human_questions', 'human_query_variants',
                                  'coverage_queries', 'coverage_depth')
    }}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
