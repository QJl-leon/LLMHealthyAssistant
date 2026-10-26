import logging
from typing import Optional
from app.factory.repository import latest_metrics, list_metric_history
logger = logging.getLogger(__name__)
RELATIVE_CHANGE_THRESHOLD = 0.05
ABNORMAL_FLAGS = ('low', 'high', 'critical')
DIRECTION_RISING = 'rising'
DIRECTION_FALLING = 'falling'
DIRECTION_STABLE = 'stable'
_FLAG_CN = {'low': '偏低', 'high': '偏高', 'critical': '显著异常', 'normal': '正常', 'unknown': '未知'}
_DIRECTION_CN = {DIRECTION_RISING: '上升', DIRECTION_FALLING: '下降', DIRECTION_STABLE: '平稳'}
TREND_SOURCE_NOTE = '以上指标数值均来自该用户历史体检记录。'

def _fmt(value: Optional[float]) -> str:
    if value is None:
        return '—'
    return f'{value:g}'

def _fmt_reference(ref_low: Optional[float], ref_high: Optional[float], ref_text: str) -> str:
    if ref_text:
        return ref_text
    if ref_low is not None and ref_high is not None:
        return f'{_fmt(ref_low)}-{_fmt(ref_high)}'
    if ref_high is not None:
        return f'<{_fmt(ref_high)}'
    if ref_low is not None:
        return f'>{_fmt(ref_low)}'
    return ''

def abnormal_metrics_of(user_id: str, report_id: Optional[str]=None) -> list[dict]:
    try:
        metrics = latest_metrics(user_id, report_id)
    except Exception as e:
        logger.warning('[trends] 读取体检指标失败 user=%s report=%s: %s', user_id, report_id, e)
        return []
    if not metrics:
        logger.warning('[trends] 未找到体检指标 user=%s report=%s', user_id, report_id)
        return []
    abnormal: list[dict] = []
    for m in metrics:
        flag = (m.flag or 'unknown').lower()
        if flag not in ABNORMAL_FLAGS:
            continue
        abnormal.append({'metric_code': m.metric_code, 'metric_name': m.metric_name, 'category': m.category or '', 'value_num': m.value_num, 'value_text': m.value_text or '', 'unit': m.unit or '', 'ref_low': m.ref_low, 'ref_high': m.ref_high, 'ref_text': m.ref_text or '', 'flag': flag, 'measured_at': m.measured_at or '', 'report_id': str(m.report_id)})
    logger.info('[trends] user=%s 异常指标 %d 项（共 %d 项）', user_id, len(abnormal), len(metrics))
    return abnormal

def _direction_and_delta(numeric_values: list[float]) -> tuple[str, Optional[float], Optional[float]]:
    if len(numeric_values) < 2:
        return (DIRECTION_STABLE, None, None)
    first, last = (numeric_values[0], numeric_values[-1])
    delta = last - first
    base = abs(first)
    if base == 0:
        if delta > 0:
            return (DIRECTION_RISING, delta, None)
        if delta < 0:
            return (DIRECTION_FALLING, delta, None)
        return (DIRECTION_STABLE, delta, None)
    ratio = delta / base
    if ratio > RELATIVE_CHANGE_THRESHOLD:
        return (DIRECTION_RISING, delta, ratio)
    if ratio < -RELATIVE_CHANGE_THRESHOLD:
        return (DIRECTION_FALLING, delta, ratio)
    return (DIRECTION_STABLE, delta, ratio)

def _render_summary(metric_name: str, unit: str, numeric_values: list[float], points: list[dict], direction: str, delta: Optional[float], ref_text: str, last_flag: str) -> str:
    unit_part = f' {unit}' if unit else ''
    ref_part = f'，参考区间 {ref_text}' if ref_text else ''
    flag_part = f"，最近一次{_FLAG_CN.get(last_flag, '未知')}"
    if not numeric_values:
        last_text = points[-1].get('value_text') or '—'
        return f'{metric_name} 仅有定性结果（最近一次 {last_text}），无法计算数值趋势{flag_part}'
    if len(numeric_values) == 1:
        point = next((p for p in points if isinstance(p['value'], (int, float))), points[-1])
        return f"{metric_name} 共 {len(points)} 次记录、仅 1 个有效数值（{point.get('date') or '日期未知'}: {_fmt(point['value'])}{unit_part}），暂无法判断趋势{ref_part}{flag_part}"
    first, last = (numeric_values[0], numeric_values[-1])
    times = len(points)
    pct = '' if delta is None or first == 0 else f'（{delta / abs(first) * 100:+.1f}%）'
    if direction == DIRECTION_RISING:
        move = f'由 {_fmt(first)} 升至 {_fmt(last)}'
    elif direction == DIRECTION_FALLING:
        move = f'由 {_fmt(first)} 降至 {_fmt(last)}'
    else:
        move = f'由 {_fmt(first)} 小幅波动至 {_fmt(last)}'
    return f"{metric_name} 近 {times} 次记录{move}{unit_part}{pct}，整体呈{_DIRECTION_CN.get(direction, '平稳')}趋势{ref_part}{flag_part}"

def build_trends(user_id: str, metric_codes: Optional[list[str]]=None, limit: int=10) -> list[dict]:
    if metric_codes:
        codes = list(dict.fromkeys((c for c in metric_codes if c)))
    else:
        try:
            latest = latest_metrics(user_id)
        except Exception as e:
            logger.warning('[trends] 读取最近体检指标失败 user=%s: %s', user_id, e)
            return []
        codes = list(dict.fromkeys((m.metric_code for m in latest if m.metric_code)))
    if not codes:
        logger.warning('[trends] 无可分析指标 user=%s', user_id)
        return []
    trends: list[dict] = []
    for code in codes:
        try:
            history = list_metric_history(user_id, code, limit)
        except Exception as e:
            logger.warning('[trends] 指标历史查询失败 user=%s code=%s: %s', user_id, code, e)
            continue
        if not history:
            logger.warning('[trends] 指标无历史记录 user=%s code=%s', user_id, code)
            continue
        history = list(reversed(history))
        points: list[dict] = []
        for m in history:
            points.append({'date': m.measured_at or '', 'value': m.value_num, 'flag': (m.flag or 'unknown').lower(), 'value_text': m.value_text or ''})
        last = history[-1]
        numeric_values = [p['value'] for p in points if isinstance(p['value'], (int, float))]
        direction, delta, _ratio = _direction_and_delta(numeric_values)
        ref_text = _fmt_reference(last.ref_low, last.ref_high, last.ref_text or '')
        last_flag = points[-1]['flag']
        trend = {'metric_code': code, 'metric_name': last.metric_name, 'unit': last.unit or '', 'ref_low': last.ref_low, 'ref_high': last.ref_high, 'points': points, 'first_value': numeric_values[0] if numeric_values else None, 'last_value': numeric_values[-1] if numeric_values else None, 'delta': delta, 'direction': direction, 'abnormal_now': last_flag in ABNORMAL_FLAGS, 'summary': _render_summary(last.metric_name, last.unit or '', numeric_values, points, direction, delta, ref_text, last_flag)}
        trends.append(trend)
    logger.info('[trends] user=%s 生成 %d 项趋势（limit=%d）', user_id, len(trends), limit)
    return trends

def trend_summary(user_id: str, metric_codes: Optional[list[str]]=None) -> str:
    trends = build_trends(user_id, metric_codes)
    if not trends:
        return '暂无该用户的历史体检指标记录，无法给出趋势分析。'
    lines = ['以下为该用户体检指标的时序趋势（含首次/最近一次数值与变化方向）:']
    for t in trends:
        lines.append(f"- {t['summary']}")
    lines.append(TREND_SOURCE_NOTE)
    return '\n'.join(lines)
