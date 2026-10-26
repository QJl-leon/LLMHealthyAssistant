import json
import logging
import os
import sys
sys.path.insert(0, '/niceoffer/src/LLMHealthyAssistant/python-ai')
CACHE_DIR = '/niceoffer/src/LLMHealthyAssistant/lecture/.demo_cache'

def cached_call(key, fn):
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = os.path.join(CACHE_DIR, key + '.json')
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    val = fn()
    with open(path, 'w') as f:
        json.dump(val, f, ensure_ascii=False)
    return val
logging.basicConfig(level=logging.INFO, format='[运行日志] %(levelname)s %(name)s: %(message)s')
from app.agents.vision_agent import _estimate_confidence
from app.factory.health_parser import EXAM_VLM_PROMPT, _extract_json_object, _metrics_from_vlm, _to_vlm_url, merge_channel_metrics, parse_metric_lines, reflow_ocr_lines
from app.gateway.adapters.ocr import OCRAdapter
from app.gateway.adapters.vlm import VLMAdapter
IMAGE = sys.argv[1] if len(sys.argv) > 1 else '/niceoffer/src/LLMHealthyAssistant/测试图像 2.png'

def hr(title: str):
    print('\n' + '═' * 64 + f'\n{title}\n' + '═' * 64)

def mrow(m) -> str:
    ref = m.ref_text or (f'{m.ref_low}~{m.ref_high}' if m.ref_low is not None or m.ref_high is not None else '')
    return f"{m.metric_name:<14} | 值={m.value_text!r:<10} 数值={m.value_num} | 单位={m.unit or '-':<8} | 参考={ref:<10} | flag={m.flag:<8} | 编码={m.metric_code}"
hr('① OCR 通道：OCRAdapter.extract_text（腾讯云 GeneralFastOCR）')
ocr = cached_call('ocr_test2', lambda: OCRAdapter().extract_text(IMAGE))
detections = ocr.get('raw_detections') or []
print(f"engine={ocr.get('engine')}  自报置信度={ocr.get('confidence')}  文字块数={len(detections)}  拼接文本长度={len(ocr.get('text') or '')}")
print('\n前 6 个文字块（含 Polygon 坐标 + 单块置信度）:')
for det in detections[:6]:
    print(f'  {det}')
hr('② 坐标还原：reflow_ocr_lines —— 文字块 → “一行一指标”')
lines = reflow_ocr_lines(detections) or (ocr.get('text') or '').splitlines()
print(f'还原出 {len(lines)} 行，前 12 行:')
for ln in lines[:12]:
    print(f'  {ln!r}')
hr('③ 文本行解析：parse_metric_lines / split_metric_line —— 行 → 结构化指标')
ocr_metrics = parse_metric_lines(lines)
print(f'OCR 通道产出 {len(ocr_metrics)} 条指标:')
for m in ocr_metrics:
    print(f'  {mrow(m)}')
hr('④ VLM 通道：VLMAdapter.analyze_image(qwen-vl-max) + EXAM_VLM_PROMPT')
vlm_adapter = VLMAdapter()
resp = cached_call('vlm_test2', lambda: vlm_adapter.analyze_image(_to_vlm_url(IMAGE), EXAM_VLM_PROMPT))
content = resp.get('choices', [{}])[0].get('message', {}).get('content', '')
usage = resp.get('usage') or {}
print(f'token 用量: {usage}')
print('\n模型原始输出（前 600 字，含 ```json 包裹）:')
print(content[:600])
hr('⑤ JSON 提取与归一：_extract_json_object → _metrics_from_vlm → normalize_metric')
data = _extract_json_object(content)
print('结构化后的 JSON（VLM 自报字段 + confidence）:')
print(json.dumps(data, ensure_ascii=False, indent=2))
vlm_metrics = _metrics_from_vlm(data, None)
print(f'\nVLM 通道产出 {len(vlm_metrics)} 条指标:')
for m in vlm_metrics:
    print(f'  {mrow(m)}')
hr('⑥ 合并裁决：merge_channel_metrics —— 同名同值合并 / 同名异值采信 VLM / 常识越界拒绝')
merged, rejected = merge_channel_metrics(ocr_metrics, vlm_metrics)
print(f'合并后入库 {len(merged)} 条（OCR 主干采信 + VLM 兜底补充）:')
for m in merged:
    print(f'  {mrow(m)}')
if rejected:
    print(f'\nVLM 审核拒绝入库 {len(rejected)} 条（留痕，不占指标位）:')
    for r in rejected:
        print(f"  ✗ {r['metric_name']} = {r['value_text']} {r['unit']}  [来源 {r['channel']}]  原因: {r['reason']}")
else:
    print('\n无拒绝条目')
hr('⑦ 解析置信度：_estimate_confidence（确定性规则，非模型自报）')
conf = _estimate_confidence(ocr.get('confidence'), data.get('confidence'), {m.metric_name for m in ocr_metrics}, {m.metric_name for m in vlm_metrics}, len(merged))
print(f'最终置信度 = {conf}（阈值 0.5；低于则 orchestrator 触发 HITL 补拍，补拍 ≤3 次）')
print(f'\n两通道指标名交集 = {sorted({m.metric_name for m in ocr_metrics} & {m.metric_name for m in vlm_metrics})}')
print(f'仅 OCR 有 = {sorted({m.metric_name for m in ocr_metrics} - {m.metric_name for m in vlm_metrics})}')
print(f'仅 VLM 有 = {sorted({m.metric_name for m in vlm_metrics} - {m.metric_name for m in ocr_metrics})}')
