import logging
import os
from typing import Optional, TypedDict
from uuid import uuid4
from langgraph.graph import StateGraph, START, END
from app.tools import ToolResult
logger = logging.getLogger(__name__)
_FALLBACK_METRICS: list[dict] = []
_ABNORMAL_FLAGS = ('low', 'high', 'critical')
_LOW_CONFIDENCE_THRESHOLD = float(os.getenv('VISION_CONFIDENCE_THRESHOLD', '0.5'))
_OCR_CONFIDENCE_THRESHOLD = float(os.getenv('OCR_CONFIDENCE_THRESHOLD', '0.6'))
_BASE_CONFIDENCE = float(os.getenv('VISION_BASE_CONFIDENCE', '0.5'))
_VLM_MULTIMODAL_PROMPT = '你是体检报告结构化抽取专家。请仔细阅读这张体检报告 / 化验单图片，输出严格的 JSON（不要 markdown 代码块）。\n\n要求：\n1. 逐行抽取检验指标表格：项目名（metric_name）、结果原文（value_text）、单位（unit）、参考区间原文（ref_text）、大类（category，可为空）\n2. 只抽取你确实看到的指标，不要补全、不要推测缺失数值\n3. 定性结果（阴性 / 阳性 / ±）原样写在 value_text\n4. 表头行、科室标题、医生签名、体检结论段落不要作为指标输出\n5. 标注图片质量问题；看不清整页数字时也要如实说明\n\n输出格式（metrics 为指标数组；也可直接输出该数组）：\n{"page": 1,\n "metrics": [\n   {"metric_name": "低密度脂蛋白胆固醇", "value_text": "3.4", "unit": "mmol/L",\n    "ref_text": "0-3.4", "category": "血脂"}\n ],\n "report_date": "YYYY-MM-DD 或空字符串",\n "institution": "体检机构或空字符串",\n "quality_issues": ["反光 / 模糊 / 裁切 / 遮挡，无问题写空数组"],\n "confidence": 0.0}\n\n规则：\n- metric_name 保持报告原文写法（如"低密度脂蛋白胆固醇"不要简化成"LDL"）\n- 结果原文含 ↑ ↓ ± < > 等标记时一并保留\n- 只输出 JSON，不要任何额外文字'

class VisionState(TypedDict):
    trace_id: str
    task_id: str
    images: list[dict]
    image_observations: list[dict]
    parsed_metrics: list[dict]
    abnormal_metrics: list[dict]
    vision_confidence: float
    errors: list[dict]

def _quality_check(state: VisionState) -> VisionState:
    from app.agents.image_quality import assess_images, guidance_from_issues
    images = state.get('images', [])
    logger.info('[Vision] quality_check images=%d', len(images))
    issues = assess_images(images)
    state['image_observations'] = []
    if issues:
        state['errors'] = [{'error_code': 'IMAGE_QUALITY_LOW', 'message': guidance_from_issues(issues), 'issues': issues, 'retryable': True}]
        logger.warning('[Vision] QC issues: %s', [i.get('action') for i in issues])
    else:
        state['errors'] = []
    return state

def _fetch_image_bytes(img_url: str) -> bytes | None:
    from httpx import Client
    if img_url.startswith('/uploads/'):
        from app.security.uploads import read_upload
        return read_upload(img_url)
    if img_url.startswith('http://') or img_url.startswith('https://'):
        try:
            with Client(timeout=15) as http:
                resp = http.get(img_url)
                resp.raise_for_status()
                return resp.content
        except Exception:
            pass
    return None

def _image_to_base64(image_bytes: bytes) -> str:
    import base64
    mime = 'image/jpeg'
    if image_bytes[:4] == b'\x89PNG':
        mime = 'image/png'
    elif image_bytes[:3] == b'GIF':
        mime = 'image/gif'
    elif image_bytes[:4] == b'RIFF':
        mime = 'image/webp'
    b64 = base64.b64encode(image_bytes).decode('utf-8')
    return f'data:{mime};base64,{b64}'

def _pick(row: dict, *keys):
    for key in keys:
        value = row.get(key)
        if value is not None:
            return value
    return None

def _pick_page(row: dict, default: Optional[int]) -> Optional[int]:
    value = row.get('page')
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default

def _parse_vlm_json(content: str):
    import json
    text = (content or '').strip()
    if not text:
        logger.warning('[Vision] VLM 输出为空')
        return {}
    if text.startswith('```'):
        text = text.split('```')[1]
        if text.startswith('json'):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, (dict, list)):
            return data
    except json.JSONDecodeError:
        pass
    for pattern in ('\\{.*\\}', '\\[.*\\]'):
        import re
        match = re.search(pattern, text, re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                if isinstance(data, (dict, list)):
                    return data
            except json.JSONDecodeError:
                continue
    logger.warning('[Vision] VLM 输出无法解析为 JSON，前 100 字符: %s', text[:100])
    return {}

def _clamp_conf(value) -> Optional[float]:
    if value is None:
        return None
    try:
        conf = float(value)
    except (TypeError, ValueError):
        return None
    if conf <= 0:
        return None
    return min(1.0, conf)

def _metrics_from_vlm(data, page: Optional[int]=None, lookup=None) -> list:
    from app.factory.health_parser import normalize_metric
    if isinstance(data, list):
        rows = data
    elif isinstance(data, dict):
        rows = data.get('metrics') or data.get('items') or []
    else:
        rows = []
    metrics = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        metric = normalize_metric(_pick(row, 'metric_name', 'name'), _pick(row, 'value_text', 'result', 'value'), _pick(row, 'unit'), _pick(row, 'ref_text', 'ref', 'reference'), page=_pick_page(row, page), lookup=lookup, category_hint=str(_pick(row, 'category') or ''))
        if metric is not None:
            metrics.append(metric)
    return metrics

def _estimate_confidence(ocr_conf: Optional[float], vlm_conf: Optional[float], ocr_names: set, vlm_names: set, metric_count: int) -> float:
    if metric_count <= 0:
        return 0.0
    available = [c for c in (ocr_conf, vlm_conf) if c is not None]
    base = sum(available) / len(available) if available else _BASE_CONFIDENCE
    if len(available) < 2:
        return round(min(1.0, base * 0.6), 4)
    union = ocr_names | vlm_names
    overlap = len(ocr_names & vlm_names) / len(union) if union else 0.0
    return round(min(1.0, base * (0.6 + 0.4 * overlap)), 4)

def _dedupe_keep_conflicts(metrics: list) -> list:
    seen: dict[str, set] = {}
    out = []
    conflicts = 0
    for metric in metrics:
        values = seen.setdefault(metric.metric_name, set())
        value_text = (metric.value_text or '').strip()
        if value_text in values:
            continue
        if values:
            conflicts += 1
            logger.warning('[Vision] 同名异值指标，两条独立保留: %s %s / %s', metric.metric_name, sorted(values), value_text)
        values.add(value_text)
        out.append(metric)
    if conflicts:
        logger.warning('[Vision] 同名异值冲突 %d 处（已独立保留，未互相覆盖）', conflicts)
    return out

def _metric_to_dict(metric, channel: str='') -> dict:
    return {'metric_code': metric.metric_code or '', 'metric_name': metric.metric_name or '', 'category': metric.category or '', 'value_num': metric.value_num, 'value_text': metric.value_text or '', 'unit': metric.unit or '', 'ref_low': metric.ref_low, 'ref_high': metric.ref_high, 'ref_text': metric.ref_text or '', 'flag': (metric.flag or 'unknown').lower(), 'page': metric.source_page, 'channel': channel}

def _append_error(errors: list[dict], payload: dict) -> None:
    if any((e.get('error_code') == payload.get('error_code') for e in errors)):
        return
    errors.append(payload)

def _multimodal_extract(state: VisionState) -> VisionState:
    from app.factory.health_parser import merge_channel_metrics, parse_metric_lines, reflow_ocr_lines
    logger.info('[Vision] multimodal_extract images=%d', len(state.get('images', [])))
    images = state.get('images', [])
    errors: list[dict] = list(state.get('errors') or [])
    observations: list[dict] = []
    all_metrics: list = []
    confidences: list[float] = []
    if not images:
        logger.info('[Vision] 无图片，不产指标（禁止 Demo 兜底）')
        state['image_observations'] = []
        state['parsed_metrics'] = []
        state['abnormal_metrics'] = []
        state['vision_confidence'] = 0.0
        _append_error(errors, {'error_code': 'NO_IMAGE', 'message': '未上传体检报告图片，无法识别体检指标（也可改传 PDF 报告）', 'retryable': True})
        state['errors'] = errors
        return state
    for img in images:
        img_url = img.get('presigned_url', '')
        img_key = img.get('key', '')
        img_position = img.get('position', 'unknown')
        page = _pick_page(img, None)
        logger.info('[Vision] 处理图片: key=%s position=%s', img_key, img_position)
        ocr_adapter = None
        ocr_text = ''
        ocr_conf: Optional[float] = None
        ocr_metrics: list = []
        vlm_metrics: list = []
        vlm_conf: Optional[float] = None
        vlm_meta: dict = {}
        try:
            from app.gateway.adapters.ocr import OCRAdapter
            ocr_adapter = OCRAdapter()
            result = ocr_adapter.extract_text(img_url)
            ocr_text = result.get('text') or ''
            ocr_conf = _clamp_conf(result.get('confidence'))
            logger.info('[Vision] OCR 完成: %d chars', len(ocr_text))
            lines = reflow_ocr_lines(result.get('raw_detections'))
            if not lines:
                lines = [str(l).strip() for l in result.get('metric_lines') or [] if str(l).strip()]
            if not lines:
                lines = [l.strip() for l in ocr_text.splitlines() if l.strip()]
            ocr_metrics = parse_metric_lines(lines, page=page)
            observations.append({'observation_id': str(uuid4()), 'image_key': img_key, 'region': img_position, 'type': 'ocr', 'text': ocr_text, 'lines': len(lines), 'metrics': len(ocr_metrics), 'confidence': ocr_conf, 'engine': result.get('engine', 'tencent')})
            if ocr_conf is not None and ocr_conf < _OCR_CONFIDENCE_THRESHOLD:
                logger.warning('[Vision] OCR 置信度偏低 image=%s conf=%.3f', img_key, ocr_conf)
                _append_error(errors, {'error_code': 'OCR_LOW_CONFIDENCE', 'message': f'「{img_position}」文字识别置信度偏低（{ocr_conf:.2f}），建议补拍体检报告：正对报告、光线充足、无遮挡，指标表格文字清晰可读', 'retryable': True})
        except Exception as e:
            logger.warning('[Vision] OCR 通道失败: %s', e)
            observations.append({'observation_id': str(uuid4()), 'image_key': img_key, 'region': img_position, 'type': 'ocr_error', 'error': str(e)})
        try:
            image_bytes = _fetch_image_bytes(img_url)
            if not image_bytes:
                logger.warning('[Vision] 无法获取图片字节: key=%s', img_key)
                raise RuntimeError('图片获取失败')
            image_b64 = _image_to_base64(image_bytes)
            logger.info('[Vision] 图片 base64: %d B → %d chars', len(image_bytes), len(image_b64))
            from app.gateway.adapters.vlm import VLMAdapter
            vlm = VLMAdapter()
            resp = vlm.analyze_image(image_b64, _VLM_MULTIMODAL_PROMPT)
            content = resp.get('choices', [{}])[0].get('message', {}).get('content', '')
            data = _parse_vlm_json(content)
            vlm_meta = data if isinstance(data, dict) else {}
            vlm_conf = _clamp_conf(vlm_meta.get('confidence'))
            vlm_metrics = _metrics_from_vlm(data, page=page)
            logger.info('[Vision] VLM 结果: metrics=%d page=%s date=%s', len(vlm_metrics), vlm_meta.get('page'), vlm_meta.get('report_date') or '未识别')
            observations.append({'observation_id': str(uuid4()), 'image_key': img_key, 'region': img_position, 'type': 'vlm_analysis', 'metrics': len(vlm_metrics), 'report_date': vlm_meta.get('report_date', ''), 'institution': vlm_meta.get('institution', ''), 'quality_issues': vlm_meta.get('quality_issues', []), 'confidence': vlm_conf})
        except Exception as e:
            logger.warning('[Vision] VLM 通道失败，将使用 OCR 文本行通道: %s', e)
            observations.append({'observation_id': str(uuid4()), 'image_key': img_key, 'region': img_position, 'type': 'vlm_error', 'error': str(e)})
        if not vlm_metrics and (not ocr_metrics) and (ocr_adapter is not None) and ocr_text.strip():
            logger.info('[Vision] 两通道均无指标，尝试 LLM 整理 OCR 文本行')
            try:
                extra_lines = ocr_adapter._llm_parse_metric_lines(ocr_text)
                ocr_metrics = parse_metric_lines(extra_lines, page=page)
                logger.info('[Vision] LLM 整理兜底: 指标 %d 项', len(ocr_metrics))
            except Exception as e:
                logger.warning('[Vision] LLM 整理兜底也失败了: %s', e)
        merged, rejected = merge_channel_metrics(ocr_metrics, vlm_metrics)
        all_metrics.extend(merged)
        if rejected:
            observations.append({'observation_id': str(uuid4()), 'image_key': img_key, 'region': img_position, 'type': 'channel_review', 'rejected': rejected, 'summary': f'VLM 审核拒绝 {len(rejected)} 条常识外/冲突值'})
        conf = _estimate_confidence(ocr_conf, vlm_conf, {m.metric_name for m in ocr_metrics}, {m.metric_name for m in vlm_metrics}, len(merged))
        if conf > 0:
            confidences.append(conf)
            logger.info('[Vision] 单图置信度 image=%s conf=%.4f', img_key, conf)
    final_metrics = _dedupe_keep_conflicts(all_metrics)
    parsed = [_metric_to_dict(m) for m in final_metrics]
    abnormal = [d for d in parsed if d['flag'] in _ABNORMAL_FLAGS]
    vision_confidence = round(sum(confidences) / len(confidences), 4) if confidences else 0.0
    state['image_observations'] = observations
    state['parsed_metrics'] = parsed
    state['abnormal_metrics'] = abnormal
    state['vision_confidence'] = vision_confidence
    if not parsed:
        logger.warning('[Vision] 有图片但未解析出体检指标，不使用 Demo 兜底')
        _append_error(errors, {'error_code': 'VISION_NO_METRIC', 'message': '未能从图片中识别出体检指标，请补拍体检报告（指标表格文字需清晰可读），或改传电子版 PDF 报告', 'retryable': True})
    elif vision_confidence < _LOW_CONFIDENCE_THRESHOLD:
        logger.warning('[Vision] 整体置信度偏低 conf=%.4f，建议补拍体检报告', vision_confidence)
        _append_error(errors, {'error_code': 'VISION_LOW_CONFIDENCE', 'message': f'体检报告图片识别置信度偏低（{vision_confidence:.2f}），建议补拍更清晰的报告照片（正对、无遮挡、指标表格文字清晰可读）', 'retryable': True})
    state['errors'] = errors
    logger.info('[Vision] 最终指标: %d 项（异常 %d 项，置信度 %.4f）', len(parsed), len(abnormal), vision_confidence)
    return state

def build_vision_agent() -> StateGraph:
    graph = StateGraph(VisionState)
    graph.add_node('quality_check', _quality_check)
    graph.add_node('multimodal_extract', _multimodal_extract)
    graph.add_edge(START, 'quality_check')
    graph.add_edge('quality_check', 'multimodal_extract')
    graph.add_edge('multimodal_extract', END)
    return graph
vision_agent = build_vision_agent().compile()
