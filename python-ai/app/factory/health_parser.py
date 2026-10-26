import base64
import hashlib
import json
import logging
import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Optional
from uuid import UUID, uuid4
import pdfplumber
from app.factory.models import HealthMetric, HealthReport, MetricCatalogRow
from app.factory.repository import find_metric_by_name, find_report_by_hash, insert_health_report, insert_metrics
logger = logging.getLogger(__name__)
HEADER_ALIASES: dict[str, list[str]] = {'name': ['检查项目', '检验项目', '检测项目', '项目名称', '项目', '名称', '指标', 'item'], 'value': ['检验结果', '检测结果', '测定值', '结果', '数值', 'value', 'result'], 'unit': ['计量单位', '单位', 'unit'], 'ref': ['参考范围', '参考区间', '正常参考值', '生物参考区间', '参考值', '参考', 'reference'], 'flag': ['结果提示', '提示', '异常', '标记', '标志', 'flag'], 'category': ['项目类别', '类别', '分类', '组别', '大类', 'category']}
_NAME_EXCLUDE_WORDS = ('类别', '分类', '机构', '科室', '医师', '医生', '日期', '时间')
_NUM = '-?\\d+(?:\\.\\d+)?'
_REF_RANGE_RE = re.compile(f'({_NUM})\\s*(?:[-~—–至]|到)\\s*({_NUM})')
_REF_UPPER_RE = re.compile(f'[<≤≦]\\s*({_NUM})')
_REF_LOWER_RE = re.compile(f'[>≥≧]\\s*({_NUM})')
_VALUE_RE = re.compile(f'^(?:[<≤≦>≥≧]?\\s*{_NUM}|阴性|阳性|弱阳性|未检出|正常)$')
_UNIT_RE = re.compile('^[A-Za-zμµ%×\\*/\\^\\d\\.]+$')
_NEGATIVE_TOKENS = ('阴性', 'negative', 'neg', '正常', '未见异常', '(-)')
_POSITIVE_TOKENS = ('阳性', 'positive', 'pos', '(+)', '±', '弱阳性')
CRITICAL_RULES: dict[str, tuple[float, str]] = {'GLU': (7.0, 'mmol/L'), '空腹血糖': (7.0, 'mmol/L'), '葡萄糖': (7.0, 'mmol/L'), 'SBP': (140.0, 'mmHg'), '收缩压': (140.0, 'mmHg'), '血压': (140.0, 'mmHg'), 'DBP': (90.0, 'mmHg'), '舒张压': (90.0, 'mmHg')}
_CRITICAL_FOLD = 2.0
COMMON_SENSE_RANGES: dict[str, tuple[float, float, str]] = {'身高': (50, 250, 'cm'), '体重': (20, 500, 'kg'), 'BMI': (10, 80, ''), '腰围': (30, 300, 'cm'), 'SBP': (50, 300, 'mmHg'), '收缩压': (50, 300, 'mmHg'), 'DBP': (20, 200, 'mmHg'), '舒张压': (20, 200, 'mmHg'), '心率': (20, 300, '次/分'), 'GLU': (1, 35, 'mmol/L'), '空腹血糖': (1, 35, 'mmol/L'), '葡萄糖': (1, 35, 'mmol/L'), '血红蛋白': (20, 300, 'g/L'), '白细胞计数': (0.1, 100, '10^9/L'), '血小板计数': (10, 2000, '10^9/L'), '血肌酐': (20, 2000, 'μmol/L'), '尿酸': (50, 2000, 'μmol/L'), '总胆固醇': (1, 30, 'mmol/L')}
EXAM_VLM_PROMPT = '请识别这张体检报告图片中的检验指标。\n\n要求:\n1. 逐行提取指标：项目名称、结果值、单位、参考区间\n2. 只提取你确实看到的指标，不要补全、不要推测缺失数值\n3. 定性结果（如 阴性 / 阳性）原样输出在 result 字段\n4. 表头行、科室标题、医生签名不要输出\n\n请严格以 JSON 格式返回:\n{\n  "metrics": [\n    {"name": "空腹血糖", "result": "5.4", "unit": "mmol/L",\n     "ref": "3.9-6.1", "category": ""}\n  ],\n  "report_date": "YYYY-MM-DD 或 空字符串",\n  "institution": "体检机构或空字符串",\n  "confidence": 0.0\n}'

def _to_half(text) -> str:
    return unicodedata.normalize('NFKC', str(text if text is not None else ''))

def normalize_metric_name(raw_name) -> str:
    s = _to_half(raw_name).strip()
    s = re.sub('[↑↓*]', '', s)
    s = re.sub('^[（(]\\d+[)）]\\s*', '', s)
    s = re.sub('^\\d+\\s*[\\.、)）]\\s*', '', s)
    s = s.strip().strip('*↑↓:：')
    s = re.sub('\\s{2,}', ' ', s)
    return s.strip()

def _unit_equal(a, b) -> str:

    def _norm(s) -> str:
        s = _to_half(s).lower().replace(' ', '')
        s = s.replace('×', '').replace('*', '').replace('µ', 'μ')
        return s.strip('/')
    return _norm(a) == _norm(b)

def _metric_key_of(metric_code: str, metric_name: str) -> str:
    return '|'.join((k for k in (metric_code, metric_name) if k))

def parse_reference_text(raw_ref) -> tuple[Optional[float], Optional[float], str]:
    text = _to_half(raw_ref).strip()
    if not text:
        return (None, None, '')
    m = _REF_RANGE_RE.search(text)
    if m:
        try:
            return (float(m.group(1)), float(m.group(2)), text)
        except ValueError:
            pass
    m = _REF_UPPER_RE.search(text)
    if m:
        try:
            return (None, float(m.group(1)), text)
        except ValueError:
            pass
    m = _REF_LOWER_RE.search(text)
    if m:
        try:
            return (float(m.group(1)), None, text)
        except ValueError:
            pass
    return (None, None, text)

def parse_result_value(raw_value) -> tuple[Optional[float], str]:
    text = _to_half(raw_value).strip()
    if not text:
        return (None, '')
    cleaned = re.sub('[↑↓*]', '', text).strip()
    m = re.search(_NUM, cleaned)
    if m:
        try:
            return (float(m.group(0)), text)
        except ValueError:
            return (None, text)
    return (None, text)

def _qualitative_flag(text: str) -> str:
    t = _to_half(text).strip().lower()
    if not t:
        return 'unknown'
    for tok in _NEGATIVE_TOKENS:
        if tok in t:
            return 'normal'
    for tok in _POSITIVE_TOKENS:
        if tok in t:
            return 'high'
    return 'unknown'

def _critical_by_rule(value: float, metric_key: str, unit: str) -> bool:
    keys = [k.strip() for k in str(metric_key or '').split('|') if k.strip()]
    for key in keys:
        rule = CRITICAL_RULES.get(key)
        if rule is None:
            for rule_key, rule_val in CRITICAL_RULES.items():
                if re.search('[\\u4e00-\\u9fff]', rule_key) and rule_key in key:
                    rule = rule_val
                    break
        if rule is None:
            continue
        threshold, rule_unit = rule
        if unit and rule_unit and (not _unit_equal(unit, rule_unit)):
            continue
        if value >= threshold:
            return True
    return False

def _commonsense_violation(metric: HealthMetric) -> Optional[str]:
    if metric.value_num is None:
        return None
    keys = [k.strip() for k in _metric_key_of(metric.metric_code, metric.metric_name).split('|') if k.strip()]
    for key in keys:
        rule = COMMON_SENSE_RANGES.get(key)
        if rule is None:
            for rule_key, rule_val in COMMON_SENSE_RANGES.items():
                if re.search('[\\u4e00-\\u9fff]', rule_key) and rule_key in key:
                    rule = rule_val
                    break
        if rule is None:
            continue
        low, high, rule_unit = rule
        if metric.unit and rule_unit and (not _unit_equal(metric.unit, rule_unit)):
            continue
        if not low <= metric.value_num <= high:
            return f'{key} {metric.value_num} 不在常识范围 {low}-{high}{rule_unit}'
    return None

def flag_of(value_num, ref_low: Optional[float], ref_high: Optional[float], direction: str='both', metric_key: str='', unit: str='') -> str:
    if value_num is None or isinstance(value_num, bool):
        return 'unknown'
    if isinstance(value_num, (int, float)):
        value = float(value_num)
    else:
        text = _to_half(value_num).strip()
        qual = _qualitative_flag(text)
        if qual != 'unknown':
            return qual
        parsed, _ = parse_result_value(text)
        if parsed is None:
            return 'unknown'
        value = parsed
    if ref_low is None and ref_high is None:
        return 'unknown'
    above = ref_high is not None and value > ref_high
    below = ref_low is not None and value < ref_low
    if not above and (not below):
        return 'normal'
    side = 'high' if above else 'low'
    if direction in ('high', 'low') and direction != side:
        return 'normal'
    if _critical_by_rule(value, metric_key, unit):
        return 'critical'
    if above and ref_high and (ref_high > 0) and (value >= ref_high * _CRITICAL_FOLD):
        return 'critical'
    if below and ref_low and (ref_low > 0) and (value <= ref_low / _CRITICAL_FOLD):
        return 'critical'
    return side

def flag_from_hint(hint) -> str:
    t = _to_half(hint).strip().lower()
    if not t:
        return 'unknown'
    if any((k in t for k in ('正常', '阴性', 'normal'))):
        return 'unknown'
    if t in ('h', '↑', '↑↑') or any((k in t for k in ('high', '偏高'))):
        return 'high'
    if t in ('l', '↓', '↓↓') or any((k in t for k in ('low', '偏低'))):
        return 'low'
    if any((k in t for k in ('阳性', '异常', 'abn'))):
        return 'high'
    return 'unknown'

def _fallback_code(name: str) -> str:
    digest = hashlib.md5(name.encode('utf-8')).hexdigest()[:8].upper()
    return f'X_{digest}'

def _default_lookup(name: str) -> Optional[MetricCatalogRow]:
    try:
        return find_metric_by_name(name)
    except Exception as e:
        logger.warning('[health_parser] 指标目录查询失败，按未收录处理: %s', e)
        return None

def normalize_metric(raw_name, raw_value, raw_unit, raw_ref, page: Optional[int]=None, lookup: Optional[Callable[[str], Optional[MetricCatalogRow]]]=None, category_hint: str='') -> Optional[HealthMetric]:
    lookup_fn = lookup or _default_lookup
    name = normalize_metric_name(raw_name)
    if not name:
        logger.warning('[health_parser] 跳过无名称指标行: value=%r ref=%r', raw_value, raw_ref)
        return None
    value_num, value_text = parse_result_value(raw_value)
    unit_raw = _to_half(raw_unit).strip()
    report_low, report_high, ref_text_raw = parse_reference_text(raw_ref)
    try:
        catalog = lookup_fn(name)
    except Exception as e:
        logger.warning('[health_parser] 目录查询异常，按未收录处理 name=%s: %s', name, e)
        catalog = None
    if catalog is not None:
        metric_code = catalog.metric_code or _fallback_code(name)
        category = catalog.category or category_hint or '未分类'
        direction = catalog.direction or 'both'
        unit_match = not unit_raw or not catalog.unit or _unit_equal(unit_raw, catalog.unit)
        if unit_match:
            unit = catalog.unit or unit_raw
            no_unified_ref = catalog.ref_low is None and catalog.ref_high is None and ('无统一参考区间' in (catalog.ref_text or ''))
            if no_unified_ref:
                ref_low, ref_high = (None, None)
                ref_text = catalog.ref_text or ''
            else:
                ref_low = catalog.ref_low if catalog.ref_low is not None else report_low
                ref_high = catalog.ref_high if catalog.ref_high is not None else report_high
                ref_text = catalog.ref_text or ref_text_raw
        else:
            unit = unit_raw
            ref_low, ref_high, ref_text = (report_low, report_high, ref_text_raw)
            logger.warning('[health_parser] 单位与标准不一致，保留报告原文 name=%s 报告=%s 标准=%s', name, unit_raw, catalog.unit)
    else:
        metric_code = _fallback_code(name)
        category = category_hint or '未分类'
        unit = unit_raw
        ref_low, ref_high, ref_text = (report_low, report_high, ref_text_raw)
        direction = 'both'
    flag_input = value_num if value_num is not None else value_text or None
    flag = flag_of(flag_input, ref_low, ref_high, direction=direction, metric_key=_metric_key_of(metric_code, name), unit=unit)
    return HealthMetric(id=uuid4(), report_id=UUID(int=0), user_id='', metric_code=metric_code, metric_name=name, category=category, value_num=value_num, value_text=value_text, unit=unit, ref_low=ref_low, ref_high=ref_high, ref_text=ref_text, flag=flag, measured_at='', source_page=page)

def _is_header_line(line: str) -> bool:
    hits = sum((1 for kw in ('项目', '结果', '参考', '单位') if kw in line))
    return hits >= 3 and (not _VALUE_RE.search(line.split()[-1] if line.split() else ''))

def _looks_like_value(seg: str) -> bool:
    return bool(_VALUE_RE.match(seg))

def _looks_like_ref(seg: str) -> bool:
    if '参考' in seg:
        return True
    if '阴性' in seg or '阳性' in seg:
        return True
    if _REF_RANGE_RE.search(seg) or _REF_UPPER_RE.search(seg) or _REF_LOWER_RE.search(seg):
        return True
    return False

def _looks_like_unit(seg: str) -> bool:
    if not seg or seg.isdigit():
        return False
    if not _UNIT_RE.match(seg):
        return False
    return bool(re.search('[A-Za-zμµ%×]', seg))

def split_metric_line(line: str) -> Optional[tuple[str, str, str, str]]:
    text = _to_half(line).strip()
    if not text:
        return None
    segs = [s.strip() for s in re.split('\\s{2,}', text) if s.strip()]
    if len(segs) < 2:
        segs = text.split()
    if len(segs) < 2:
        return None
    value_idx = None
    for i in range(1, len(segs)):
        if _looks_like_value(segs[i]):
            value_idx = i
            break
    if value_idx is None:
        return None
    name = ' '.join(segs[:value_idx]).strip()
    if not name:
        return None
    unit, ref = ('', '')
    for seg in segs[value_idx + 1:]:
        if not ref and _looks_like_ref(seg):
            ref = seg
            continue
        if not unit and _looks_like_unit(seg):
            unit = seg
            continue
    return (name, segs[value_idx], unit, ref)

def parse_metric_lines(lines, page: Optional[int]=None, lookup: Optional[Callable[[str], Optional[MetricCatalogRow]]]=None, category_hint: str='') -> list[HealthMetric]:
    metrics: list[HealthMetric] = []
    for raw in lines or []:
        line = _to_half(raw).strip()
        if not line or _is_header_line(line):
            continue
        parsed = split_metric_line(line)
        if not parsed:
            continue
        name, value, unit, ref = parsed
        metric = normalize_metric(name, value, unit, ref, page=page, lookup=lookup, category_hint=category_hint)
        if metric is not None:
            metrics.append(metric)
    return metrics

def merge_channel_metrics(primary: list[HealthMetric], secondary: list[HealthMetric]) -> tuple[list[HealthMetric], list[dict]]:

    def _reject(m: HealthMetric, channel: str, reason: str) -> None:
        rejected.append({'metric_name': m.metric_name, 'value_text': m.value_text or '', 'unit': m.unit or '', 'channel': channel, 'reason': reason})
        logger.warning('[health_parser] 拒绝入库 %s=%s(%s) [%s]: %s', m.metric_name, m.value_text, m.unit, channel, reason)

    def _same_value(p: HealthMetric, m: HealthMetric) -> bool:
        return (p.value_num is None) == (m.value_num is None) and (p.value_num is None or abs(p.value_num - m.value_num) <= 1e-06) and ((p.value_text or '') == (m.value_text or ''))
    merged: list[HealthMetric] = []
    rejected: list[dict] = []
    taken_names: set[str] = set()
    for p in primary:
        same_name = [s for s in secondary if s.metric_name == p.metric_name]
        if not same_name:
            violation = _commonsense_violation(p)
            if violation:
                _reject(p, 'ocr', violation)
            else:
                merged.append(p)
            continue
        taken_names.add(p.metric_name)
        same = next((s for s in same_name if _same_value(p, s)), None)
        if same is not None:
            merged.append(p)
        else:
            best = same_name[0]
            merged.append(best)
            _reject(p, 'ocr', f'通道冲突（OCR={p.value_text} / VLM={best.value_text}），采信 VLM')
    for s in secondary:
        if s.metric_name in taken_names:
            continue
        violation = _commonsense_violation(s)
        if violation:
            _reject(s, 'vlm', violation + '（VLM 值常识越界）')
        else:
            merged.append(s)
    return (merged, rejected)

def dedupe_by_name(metrics: list[HealthMetric]) -> list[HealthMetric]:
    seen: set[str] = set()
    out: list[HealthMetric] = []
    duplicates = 0
    for m in metrics:
        if m.metric_name in seen:
            duplicates += 1
            continue
        seen.add(m.metric_name)
        out.append(m)
    if duplicates:
        logger.info('[health_parser] 同名去重 %d 条（跨通道重复）', duplicates)
    return out

def _metric_signature(m: HealthMetric) -> tuple:
    return (m.metric_name, m.metric_code, '' if m.value_num is None else f'{m.value_num:.6g}', m.value_text or '', m.unit or '', m.ref_text or '')

def compute_report_hash(user_id: str, report_date: str, metrics: list[HealthMetric]) -> str:
    payload = json.dumps({'user_id': user_id, 'report_date': report_date or '', 'metrics': sorted((_metric_signature(m) for m in metrics))}, ensure_ascii=False, sort_keys=True)
    return hashlib.md5(payload.encode('utf-8')).hexdigest()

def build_report(metrics: list[HealthMetric], user_id: str, report_date: str='', institution: str='', report_type: str='physical_exam') -> tuple[HealthReport, list[HealthMetric]]:
    if not metrics:
        logger.warning('[health_parser] 未解析出任何指标，生成空报告骨架 user=%s', user_id)
    report = HealthReport(id=uuid4(), user_id=user_id, report_date=report_date or '', institution=institution or '', report_type=report_type or 'physical_exam', content_hash=compute_report_hash(user_id, report_date, metrics))
    for m in metrics:
        m.report_id = report.id
        m.user_id = user_id
        m.measured_at = report_date or ''
    return (report, metrics)

def save_report_and_metrics(report: HealthReport, metrics: list[HealthMetric]) -> tuple[str, int]:
    try:
        existing = find_report_by_hash(report.user_id, report.content_hash)
    except Exception as e:
        logger.error('[health_parser] 报告去重查询失败: %s', e)
        raise
    if existing is not None:
        logger.info('[health_parser] 命中重复报告，跳过入库 report_id=%s user=%s', existing.id, report.user_id)
        return (str(existing.id), 0)
    insert_health_report(report)
    inserted = insert_metrics(metrics)
    logger.info('[health_parser] 报告入库完成 report_id=%s 指标=%d 条', report.id, inserted)
    return (str(report.id), inserted)
_DATE_RE = re.compile('(20\\d{2})\\s*[-/年\\.]\\s*(\\d{1,2})\\s*[-/月\\.]\\s*(\\d{1,2})')
_DATE_KEYWORDS = ('体检日期', '检查日期', '报告日期', '体检时间', '采样日期', '检验日期')
_INSTITUTION_KEYWORDS = ('体检机构', '体检单位', '体检中心', '医疗机构', '医院')

def detect_report_date(text: str) -> str:
    if not text:
        return ''
    for line in text.splitlines():
        if any((kw in line for kw in _DATE_KEYWORDS)):
            m = _DATE_RE.search(line)
            if m:
                return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    m = _DATE_RE.search(text)
    if m:
        return f'{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}'
    return ''

def detect_institution(text: str) -> str:
    if not text:
        return ''
    for line in text.splitlines():
        if any((kw in line for kw in _INSTITUTION_KEYWORDS)):
            for kw in _INSTITUTION_KEYWORDS:
                if kw in line:
                    tail = line.split(kw, 1)[1].strip(' :：-—\t')
                    return (tail or line.strip())[:64]
    return ''
_NOTE_TEXT_MIN_CHARS = 12
_NAME_CARRY_STOP_WORDS = ('小结', '结论', '建议', '总检', '综述', '备注')
_HEADER_ROW_KEYWORDS = ('项目', '结果', '参考', '单位', '提示', '类别')

@dataclass
class TableParseContext:
    header_col_map: dict[str, int] = field(default_factory=dict)
    header_ncols: int = 0
    pending_name: str = ''
    pending_category: str = ''

def _non_empty_cells(row) -> list[str]:
    return [str(c).strip() for c in row or [] if c is not None and str(c).strip()]

def _is_full_width_note_row(row) -> bool:
    filled = _non_empty_cells(row)
    if len(filled) != 1:
        return False
    text = filled[0]
    return len(text) >= _NOTE_TEXT_MIN_CHARS or text.startswith(('备注', '说明', '注：', '注:'))
_SECTION_TITLE_RE = re.compile('^[（(]*(?:续上页|第)?[一二三四五六七八九十\\d]+[、.．)）]|^[（(]续')

def _is_section_title_row(row, col_map: dict[str, int]) -> bool:
    filled = _non_empty_cells(row)
    if len(filled) != 1:
        return False
    name_idx = col_map.get('name')
    first_col_text = str(row[0] or '').strip() if row else ''
    if not first_col_text:
        return False
    if name_idx == 0:
        return False
    return bool(_SECTION_TITLE_RE.match(filled[0]))

def _row_is_header_row(row) -> bool:
    text = ' '.join(_non_empty_cells(row))
    if not text:
        return False
    return sum((1 for kw in _HEADER_ROW_KEYWORDS if kw in text)) >= 3

def _is_continuation_table(table, ctx: TableParseContext) -> bool:
    if not ctx.header_col_map or not table or (not ctx.header_ncols):
        return False
    first = table[0]
    if len(first) != ctx.header_ncols:
        return False
    name_idx = ctx.header_col_map.get('name')
    if name_idx is None or name_idx >= len(first):
        return False
    if str(first[name_idx] or '').strip():
        return True
    value_idx = ctx.header_col_map.get('value')
    has_value = value_idx is not None and value_idx < len(first) and bool(str(first[value_idx] or '').strip())
    return has_value and bool(ctx.pending_name)

def _detect_table_columns(headers) -> dict[str, int]:
    mapping: dict[str, int] = {}
    cells = [_to_half(h).strip().lower() for h in headers or []]
    for col, aliases in HEADER_ALIASES.items():
        for alias in aliases:
            for idx, cell in enumerate(cells):
                if not cell or col in mapping:
                    continue
                if col == 'name' and any((w in cell for w in _NAME_EXCLUDE_WORDS)):
                    continue
                if alias.lower() in cell:
                    mapping[col] = idx
                    break
    return mapping

def _find_table_header(table) -> tuple[int, dict[str, int]]:
    for idx in range(min(2, len(table))):
        col_map = _detect_table_columns(table[idx])
        if 'name' in col_map and ('value' in col_map or 'ref' in col_map):
            return (idx, col_map)
    return (-1, {})

def _cell(row, col_map: dict[str, int], key: str) -> str:
    idx = col_map.get(key)
    if idx is None or idx < 0 or idx >= len(row):
        return ''
    raw = row[idx]
    return _to_half(raw).replace('\n', ' ').strip() if raw is not None else ''

def _metric_from_table_row(row, col_map: dict[str, int], page_number: int, lookup, ctx: TableParseContext) -> Optional[HealthMetric]:
    if not row or not _non_empty_cells(row):
        return None
    if _row_is_header_row(row):
        return None
    if _is_full_width_note_row(row):
        return None
    if _is_section_title_row(row, col_map):
        ctx.pending_name = ''
        ctx.pending_category = ''
        return None
    raw_name = _cell(row, col_map, 'name')
    raw_value = _cell(row, col_map, 'value')
    raw_category = _cell(row, col_map, 'category')
    if raw_name and any((w in raw_name for w in _NAME_CARRY_STOP_WORDS)):
        ctx.pending_name = ''
        ctx.pending_category = ''
    if not raw_name and ctx.pending_name:
        raw_name = ctx.pending_name
    if not raw_category and ctx.pending_category:
        raw_category = ctx.pending_category
    if raw_name:
        ctx.pending_name = raw_name
    if raw_category:
        ctx.pending_category = raw_category
    if not raw_value:
        return None
    metric = normalize_metric(raw_name, raw_value, _cell(row, col_map, 'unit'), _cell(row, col_map, 'ref'), page=page_number, lookup=lookup, category_hint=raw_category)
    if metric is None:
        return None
    if metric.flag == 'unknown':
        hint_flag = flag_from_hint(_cell(row, col_map, 'flag'))
        if hint_flag != 'unknown':
            metric.flag = hint_flag
    return metric

def _metrics_from_tables(page, lookup, ctx: Optional[TableParseContext]=None) -> list[HealthMetric]:
    ctx = ctx if ctx is not None else TableParseContext()
    metrics: list[HealthMetric] = []
    try:
        tables = page.extract_tables()
    except Exception as e:
        logger.warning('[health_parser] 第 %s 页表格提取失败: %s', page.page_number, e)
        return metrics
    for table in tables or []:
        if not table:
            continue
        header_idx, col_map = _find_table_header(table)
        if header_idx >= 0:
            ctx.header_col_map = col_map
            ctx.header_ncols = len(table[header_idx])
            ctx.pending_name = ''
            ctx.pending_category = ''
            start = header_idx + 1
        elif _is_continuation_table(table, ctx):
            col_map = ctx.header_col_map
            start = 0
            logger.info('[health_parser] 第 %s 页表格为跨页续页（未重复表头），沿用上一页表头列映射', page.page_number)
        else:
            logger.warning('[health_parser] 第 %s 页存在无法识别表头的表格，已跳过', page.page_number)
            continue
        for row in table[start:]:
            metric = _metric_from_table_row(row, col_map, page.page_number, lookup, ctx)
            if metric is not None:
                metrics.append(metric)
    return metrics
_BORDERLESS_ROW_TOL = 3.0
_BORDERLESS_COL_TOL = 8.0

def _page_lines(page) -> list[list[dict]]:
    try:
        words = page.extract_words() or []
    except Exception:
        return []
    buckets: dict[float, list[dict]] = {}
    for w in words:
        key = round(float(w.get('top', 0)) / _BORDERLESS_ROW_TOL) * _BORDERLESS_ROW_TOL
        buckets.setdefault(key, []).append(w)
    return [sorted(buckets[k], key=lambda w: float(w.get('x0', 0))) for k in sorted(buckets)]

def _borderless_columns(row_words: list[dict]) -> dict[str, float]:
    texts = [str(w.get('text', '')) for w in row_words]
    col_index = _detect_table_columns(texts)
    if 'name' not in col_index or not {'value', 'ref'} & set(col_index):
        return {}
    return {col: float(row_words[idx].get('x0', 0)) for col, idx in col_index.items()}

def _assign_words_to_columns(row_words: list[dict], col_starts: dict[str, float]) -> tuple[list[str], dict[str, int]]:
    ordered = sorted(col_starts.items(), key=lambda kv: kv[1])
    cols = [c for c, _ in ordered]
    starts = [x for _, x in ordered]
    cells = [''] * len(cols)
    for w in row_words:
        x0 = float(w.get('x0', 0))
        idx = 0
        for i, s in enumerate(starts):
            if x0 + _BORDERLESS_COL_TOL >= s:
                idx = i
        text = str(w.get('text', '')).strip()
        if text:
            cells[idx] = f'{cells[idx]} {text}'.strip() if cells[idx] else text
    return (cells, {c: i for i, c in enumerate(cols)})

def _metrics_from_borderless_tables(page, lookup, ctx: Optional[TableParseContext]=None) -> list[HealthMetric]:
    ctx = ctx if ctx is not None else TableParseContext()
    metrics: list[HealthMetric] = []
    lines = _page_lines(page)
    if not lines:
        return metrics
    col_starts: dict[str, float] = {}
    col_map: dict[str, int] = {}
    for row_words in lines:
        if not col_starts:
            col_starts = _borderless_columns(row_words)
            if col_starts:
                cells, col_map = _assign_words_to_columns(row_words, col_starts)
                ctx.header_col_map = col_map
                ctx.header_ncols = len(cells)
                ctx.pending_name = ''
                ctx.pending_category = ''
            continue
        cells, _ = _assign_words_to_columns(row_words, col_starts)
        metric = _metric_from_table_row(cells, col_map, page.page_number, lookup, ctx)
        if metric is not None:
            metrics.append(metric)
    return metrics

def parse_exam_pdf(pdf_path: str, user_id: str, report_date: str='', institution: str='', report_type: str='physical_exam', lookup: Optional[Callable[[str], Optional[MetricCatalogRow]]]=None) -> tuple[HealthReport, list[HealthMetric]]:
    if not pdf_path or not os.path.exists(pdf_path):
        logger.warning('[health_parser] PDF 不存在，无法解析: %s', pdf_path)
        return build_report([], user_id, report_date, institution, report_type)
    table_metrics: list[HealthMetric] = []
    line_metrics: list[HealthMetric] = []
    raw_texts: list[str] = []
    table_ctx = TableParseContext()
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_metrics = _metrics_from_tables(page, lookup, table_ctx)
                if not page_metrics:
                    page_metrics = _metrics_from_borderless_tables(page, lookup, table_ctx)
                    if page_metrics:
                        logger.info('[health_parser] 第 %s 页无表格线，按文字块坐标还原表格结构，解析出 %d 项指标', page.page_number, len(page_metrics))
                table_metrics.extend(page_metrics)
                try:
                    page_text = page.extract_text() or ''
                except Exception as e:
                    logger.warning('[health_parser] 第 %s 页文本提取失败: %s', page.page_number, e)
                    page_text = ''
                if not page_text:
                    continue
                raw_texts.append(page_text)
                if page_metrics:
                    continue
                line_metrics.extend(parse_metric_lines(page_text.splitlines(), page=page.page_number, lookup=lookup))
    except Exception as e:
        logger.error('[health_parser] PDF 解析失败 path=%s: %s', pdf_path, e)
        return build_report([], user_id, report_date, institution, report_type)
    metrics = dedupe_by_name(table_metrics + line_metrics)
    if not metrics:
        logger.warning('[health_parser] PDF 未解析出任何指标（可能是扫描件，请走图片通道）: %s', pdf_path)
        return build_report([], user_id, report_date, institution, report_type)
    raw_text = '\n'.join(raw_texts)
    if not report_date:
        report_date = detect_report_date(raw_text)
    if not institution:
        institution = detect_institution(raw_text)
    logger.info('[health_parser] PDF 解析完成 %s: 表格通道=%d 文本通道=%d 去重后=%d 日期=%s 机构=%s', os.path.basename(pdf_path), len(table_metrics), len(line_metrics), len(metrics), report_date or '未识别', institution or '未识别')
    return build_report(metrics, user_id, report_date, institution, report_type)

def _extract_json_object(text: str) -> dict:
    if not text:
        return {}
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        pass
    m = re.search('```(?:json)?\\s*\\n?(.*?)\\n?```', text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(1))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass
    m = re.search('\\{.*\\}', text, re.DOTALL)
    if m:
        try:
            data = json.loads(m.group(0))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            pass
    logger.warning('[health_parser] VLM 输出无法解析为 JSON，前 100 字符: %s', text[:100])
    return {}

def _to_vlm_url(image_path: str) -> str:
    if image_path.startswith('/uploads/'):
        from app.security.uploads import upload_data_url
        return upload_data_url(image_path)
    if image_path.startswith(('http://', 'https://', 'data:')):
        return image_path
    if os.path.exists(image_path):
        ext = os.path.splitext(image_path)[1].lower().lstrip('.') or 'png'
        mime = 'image/jpeg' if ext in ('jpg', 'jpeg') else f'image/{ext}'
        with open(image_path, 'rb') as f:
            b64 = base64.b64encode(f.read()).decode('utf-8')
        return f'data:{mime};base64,{b64}'
    return image_path

def reflow_ocr_lines(detections) -> list[str]:
    blocks: list[tuple[float, float, float, str]] = []
    for det in detections or []:
        text = _to_half((det or {}).get('DetectedText') or '').strip()
        polygon = (det or {}).get('Polygon') or []
        if not text or not polygon:
            continue
        try:
            ys = [float(p.get('Y', 0)) for p in polygon]
            xs = [float(p.get('X', 0)) for p in polygon]
        except (TypeError, ValueError, AttributeError):
            continue
        blocks.append((sum(ys) / len(ys), min(xs), max(ys) - min(ys), text))
    if not blocks:
        return []
    heights = sorted((b[2] for b in blocks))
    tolerance = max(8.0, heights[len(heights) // 2] * 0.6)
    blocks.sort(key=lambda b: (b[0], b[1]))
    rows: list[list] = []
    for y, x, _h, text in blocks:
        if rows and abs(y - rows[-1][0]) <= tolerance:
            rows[-1][1].append((x, text))
        else:
            rows.append([y, [(x, text)]])
    lines: list[str] = []
    for _y, cells in rows:
        cells.sort(key=lambda c: c[0])
        lines.append('  '.join((t for _x, t in cells)))
    return lines

def _metrics_from_vlm(data: dict, lookup) -> list[HealthMetric]:
    metrics: list[HealthMetric] = []
    for row in data.get('metrics') or []:
        if not isinstance(row, dict):
            continue
        metric = normalize_metric(row.get('name'), row.get('result', row.get('value')), row.get('unit'), row.get('ref', row.get('reference')), lookup=lookup, category_hint=str(row.get('category') or ''))
        if metric is not None:
            metrics.append(metric)
    return metrics

def parse_exam_image(image_path: str, user_id: str, report_date: str='', institution: str='', report_type: str='lab_sheet', lookup: Optional[Callable[[str], Optional[MetricCatalogRow]]]=None, ocr_adapter=None, vlm_adapter=None) -> tuple[HealthReport, list[HealthMetric]]:
    if not image_path:
        logger.warning('[health_parser] 图片路径为空，无法解析')
        return build_report([], user_id, report_date, institution, report_type)
    ocr_metrics: list[HealthMetric] = []
    vlm_metrics: list[HealthMetric] = []
    vlm_meta: dict = {}
    try:
        from app.gateway.adapters.ocr import OCRAdapter
        adapter = ocr_adapter or OCRAdapter()
        result = adapter.extract_text(image_path)
        ocr_text = result.get('text') or ''
        lines = reflow_ocr_lines(result.get('raw_detections')) or ocr_text.splitlines()
        if lines:
            ocr_metrics = parse_metric_lines(lines, lookup=lookup)
        else:
            logger.warning('[health_parser] OCR 文本通道无内容（engine=%s）', result.get('engine'))
    except Exception as e:
        logger.warning('[health_parser] OCR 通道失败，仅使用 VLM 通道: %s', e)
    try:
        from app.gateway.adapters.vlm import VLMAdapter
        adapter = vlm_adapter or VLMAdapter()
        resp = adapter.analyze_image(_to_vlm_url(image_path), EXAM_VLM_PROMPT)
        content = resp.get('choices', [{}])[0].get('message', {}).get('content', '')
        vlm_meta = _extract_json_object(content)
        vlm_metrics = _metrics_from_vlm(vlm_meta, lookup)
    except Exception as e:
        logger.warning('[health_parser] VLM 通道失败，仅使用 OCR 通道: %s', e)
    metrics, rejected = merge_channel_metrics(ocr_metrics, vlm_metrics)
    if rejected:
        logger.warning('[health_parser] 图片解析 VLM 审核拒绝 %d 条: %s', len(rejected), [f"{r['metric_name']}={r['value_text']}({r['channel']})" for r in rejected])
    if not metrics:
        logger.warning('[health_parser] 图片未解析出任何指标: %s', image_path)
        return build_report([], user_id, report_date, institution, report_type)
    if not report_date:
        report_date = str(vlm_meta.get('report_date') or '').strip()
    if not institution:
        institution = str(vlm_meta.get('institution') or '').strip()
    logger.info('[health_parser] 图片解析完成 %s: OCR=%d VLM=%d 合并后=%d', os.path.basename(image_path), len(ocr_metrics), len(vlm_metrics), len(metrics))
    return build_report(metrics, user_id, report_date, institution, report_type)
