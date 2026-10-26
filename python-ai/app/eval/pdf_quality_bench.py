from __future__ import annotations
import json
import os
import sys
from datetime import datetime
import pdfplumber
from app.factory.health_parser import _cell, _find_table_header, parse_exam_pdf, parse_metric_lines
REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')

def _default_fixtures() -> list[str]:
    base = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), 'tests', 'fixtures')
    return [os.path.join(base, 'exam_report_multipage.pdf'), os.path.join(base, 'exam_report_borderless.pdf')]

def _legacy_rows(pdf_path: str) -> list[list[str]]:
    rows: list[list[str]] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables() or []:
                if not table or len(table) < 2:
                    continue
                header_idx, col_map = _find_table_header(table)
                if header_idx < 0:
                    continue
                for row in table[header_idx + 1:]:
                    if not row or all((c is None or str(c).strip() == '' for c in row)):
                        continue
                    rows.append([_cell(row, col_map, 'name'), _cell(row, col_map, 'value')])
            try:
                text = page.extract_text() or ''
            except Exception:
                text = ''
            for m in parse_metric_lines(text.splitlines(), page=page.page_number, lookup=lambda n: None):
                rows.append([m.metric_name, m.value_text or ('' if m.value_num is None else str(m.value_num))])
    return rows

def _pipeline_rows(pdf_path: str) -> list[list[str]]:
    _, metrics = parse_exam_pdf(pdf_path, '__eval__', lookup=lambda n: None)
    return [[m.metric_name, m.value_text or ('' if m.value_num is None else str(m.value_num))] for m in metrics]

def _text_channel_names(pdf_path: str) -> dict:
    out: dict[str, str] = {}
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            try:
                text = page.extract_text() or ''
            except Exception:
                continue
            for m in parse_metric_lines(text.splitlines(), page=page.page_number, lookup=lambda n: None):
                out.setdefault(m.metric_name, m.value_text or ('' if m.value_num is None else str(m.value_num)))
    return out

def _is_value_like(v: str) -> bool:
    if not v:
        return False
    try:
        float(v)
        return True
    except ValueError:
        return v in ('阴性', '阳性', '弱阳性', '未检出', '正常', '(-)', '(+)', '±')

def _stats(rows: list[list[str]]) -> dict:
    total = len(rows)
    empty_name = 0
    aligned = 0
    bleed = 0
    for cells in rows:
        name = (cells[0] if cells else '').strip()
        value = (cells[1] if len(cells) > 1 else '').strip()
        if not name:
            empty_name += 1
            continue
        if _is_value_like(value):
            aligned += 1
        if ' ' in name or '\u3000' in name:
            bleed += 1
    return {'total_rows': total, 'empty_name_rows': empty_name, 'empty_name_rate': round(empty_name / total, 4) if total else 0.0, 'aligned_rows': aligned, 'column_alignment_rate': round(aligned / total, 4) if total else 0.0, 'bleed_rows': bleed, 'column_bleed_rate': round(bleed / total, 4) if total else 0.0, 'unique_items': len({c[0] for c in rows if c and c[0].strip()})}

def _channel_consistency(pdf_path: str) -> dict:
    table_map = {n: v for n, v in _pipeline_rows(pdf_path)}
    text_map = _text_channel_names(pdf_path)
    common = set(table_map) & set(text_map)
    if not common:
        return {'common_items': 0, 'consistent_items': 0, 'consistency_rate': None, 'note': '两通道无同名指标，无法计算一致率（不编造数字）'}
    consistent = sum((1 for n in common if table_map[n] == text_map[n]))
    return {'common_items': len(common), 'consistent_items': consistent, 'consistency_rate': round(consistent / len(common), 4)}

def _eval_one(pdf_path: str) -> dict:
    before = _stats(_legacy_rows(pdf_path))
    after = _stats(_pipeline_rows(pdf_path))
    return {'pdf': os.path.basename(pdf_path), 'before_no_structure_restore': before, 'after_with_structure_restore': after, 'channel_consistency_after': _channel_consistency(pdf_path)}

def main():
    argv = sys.argv[1:]
    pdf_path = argv[argv.index('--pdf') + 1] if '--pdf' in argv else ''
    if '--dry-run' in argv:
        print('\n=== 体检报告 PDF 解析质量评测（亮点1）dry-run ===')
        print('处理前: 无合并单元格还原 / 无跨页延续 / 无名称回填 / 重复表头不跳过')
        print('处理后: 真实解析管线 parse_exam_pdf（含表格结构还原）')
        print('指标: 空名率 / 列对齐率 / 串列率 / 通道一致率')
        print('用法: python -m app.eval.pdf_quality_bench [--pdf <体检报告.pdf>]')
        return
    if pdf_path:
        if not os.path.exists(pdf_path):
            print(f'[ERROR] PDF 不存在: {pdf_path}', file=sys.stderr)
            sys.exit(1)
        samples = [pdf_path]
        sample_kind = '真实体检报告'
    else:
        samples = [p for p in _default_fixtures() if os.path.exists(p)]
        sample_kind = '仓库合成夹具（由 tests/fixtures/make_exam_pdf.py 生成）'
        if not samples:
            print('[ERROR] 未找到内置夹具，也未提供 --pdf；请先运行 tests/fixtures/make_exam_pdf.py 或指定 --pdf', file=sys.stderr)
            sys.exit(1)
    results = []
    for p in samples:
        print(f'\n=== 体检报告 PDF 解析质量（{os.path.basename(p)}）===\n')
        r = _eval_one(p)
        b, a = (r['before_no_structure_restore'], r['after_with_structure_restore'])
        print(f"  {'指标':<22}{'处理前':>12}{'处理后':>12}{'变化':>12}")
        for label, key, pct in (('数据行数', 'total_rows', False), ('空名行数', 'empty_name_rows', False), ('空名率', 'empty_name_rate', True), ('列对齐率', 'column_alignment_rate', True), ('串列率', 'column_bleed_rate', True), ('独特项目数', 'unique_items', False)):
            bv, av = (b[key], a[key])
            fmt = (lambda x: f'{x:.2%}') if pct else lambda x: f'{x}'
            print(f"  {label:<22}{fmt(bv):>12}{fmt(av):>12}{(fmt(av - bv) if not pct else f'{av - bv:+.2%}'):>12}")
        cc = r['channel_consistency_after']
        print(f"  通道一致率              {str(cc['consistency_rate']):>12}  （共同覆盖 {cc['common_items']} 项）")
        results.append(r)
    agg_before = {k: sum((r['before_no_structure_restore'][k] for r in results)) for k in ('total_rows', 'empty_name_rows', 'unique_items')}
    agg_after = {k: sum((r['after_with_structure_restore'][k] for r in results)) for k in ('total_rows', 'empty_name_rows', 'unique_items')}
    report = {'benchmark': 'pdf_quality_before_after', 'object': '体检报告表格结构还原（合并单元格 / 跨页延续 / 名称延续）', 'sample_kind': sample_kind, 'samples': results, 'aggregate': {'before': agg_before, 'after': agg_after, 'before_empty_name_rate': round(agg_before['empty_name_rows'] / agg_before['total_rows'], 4) if agg_before['total_rows'] else 0.0, 'after_empty_name_rate': round(agg_after['empty_name_rows'] / agg_after['total_rows'], 4) if agg_after['total_rows'] else 0.0}, 'insight': f"表格结构治理前：合并单元格不还原导致名称为空（无法检索）、跨页不延续导致成片指标丢失、重复表头产生假指标；治理后空名率降为 {(round(agg_after['empty_name_rows'] / agg_after['total_rows'], 4) if agg_after['total_rows'] else 0.0):.2%}，独特项目数 {agg_before['unique_items']} → {agg_after['unique_items']}。", 'timestamp': datetime.now().isoformat(timespec='seconds'), 'note': '默认样本为仓库合成夹具（确定性回归用）；真实报告请用 --pdf 指定，不同机构版式差异较大，需按样本调优解析规则。'}
    os.makedirs(REPORT_DIR, exist_ok=True)
    out = os.path.join(REPORT_DIR, f"pdf_quality_bench_{datetime.now().strftime('%Y%m%d')}.json")
    with open(out, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'\n报告已写入: {out}')
if __name__ == '__main__':
    main()
