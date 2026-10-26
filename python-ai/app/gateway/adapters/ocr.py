from app.observability.runtime import timed
import os
import json
import base64
import hashlib
import hmac
import logging
import re
import time
from datetime import datetime
from httpx import Client
logger = logging.getLogger(__name__)
OCR_PROMPT = '请识别这张体检报告 / 化验单图片中的检验指标。\n\n要求:\n1. 逐行提取指标：项目名称、结果、单位、参考区间（保持原文，不要翻译）\n2. 定性结果（如 阴性 / 阳性 / ±）原样输出在 result 字段\n3. 只输出你确实看到的内容，不要补全、不要推测缺失数值\n4. 表头行（检验项目 / 结果 / 单位 / 参考范围）、体检结论 / 小结、科室与医生签名不要输出\n5. 如能看到体检机构与报告日期，一并提取\n\n请以 JSON 格式返回:\n{\n  "metric_lines": ["空腹血糖  5.4  mmol/L  3.9-6.1", ...],\n  "metrics": [{"metric_name": "空腹血糖", "value_text": "5.4", "unit": "mmol/L",\n               "ref_text": "3.9-6.1", "category": ""}],\n  "report_date": "",\n  "institution": "",\n  "confidence": 0.85\n}'
_HEADER_LINE_RE = re.compile('(项目|名称).*(结果|测定值|参考|单位)')
_SECTION_END_RE = re.compile('(体检结论|总检结论|体检小结|总评|医师建议|报告说明)')
_RESULT_RE = re.compile('(\\d|[<>≤≥]|阴性|阳性|弱阳性|未检出|正常)')

class OCRAdapter:

    def __init__(self):
        self.engine = os.getenv('OCR_ENGINE', 'dashscope')
        self.secret_id = os.getenv('TENCENT_SECRET_ID', '')
        self.secret_key = os.getenv('TENCENT_SECRET_KEY', '')
        self.go_base_url = os.getenv('GO_BASE_URL', 'http://localhost:8080')

    @timed('model.ocr')
    def extract_text(self, image_url: str) -> dict:
        if self.engine == 'tencent':
            return self._extract_tencent(image_url)
        elif self.engine == 'dashscope':
            return self._extract_vlm(image_url)
        elif self.engine == 'aliyun':
            return self._extract_aliyun(image_url)
        else:
            return {'engine': self.engine, 'text': '', 'confidence': None, 'metric_lines': [], 'metrics': []}

    def _extract_tencent(self, image_url: str) -> dict:
        try:
            image_bytes = self._fetch_image(image_url)
            if not image_bytes:
                return {'engine': 'tencent', 'text': '', 'confidence': None, 'metric_lines': [], 'metrics': [], 'error': '图片拉取失败'}
            image_base64_str = base64.b64encode(image_bytes).decode('utf-8')
            logger.info('[OCR] 图片拉取成功 size=%d B base64=%d chars', len(image_bytes), len(image_base64_str))
            detections = self._call_tencent_ocr(image_base64_str)
            logger.info('[OCR] 腾讯云返回 %d 个文字块', len(detections))
            all_text = '\n'.join([d.get('DetectedText', '') for d in detections])
            metric_lines = self._llm_parse_metric_lines(all_text)
            return {'engine': 'tencent', 'text': all_text, 'metric_lines': metric_lines, 'metrics': [], 'raw_detections': detections, 'confidence': self._avg_confidence(detections)}
        except Exception as e:
            logger.error('[OCR] 腾讯云调用失败: %s', e)
            return {'engine': 'tencent', 'text': '', 'confidence': None, 'metric_lines': [], 'metrics': [], 'error': str(e)}

    def _fetch_image(self, image_url: str) -> bytes | None:
        if image_url.startswith('/uploads/'):
            from app.security.uploads import read_upload
            return read_upload(image_url)
        if image_url.startswith('http://') or image_url.startswith('https://'):
            try:
                client = Client(timeout=15)
                resp = client.get(image_url)
                resp.raise_for_status()
                return resp.content
            except Exception as e:
                logger.warning('[OCR] HTTP 拉取图片失败: %s', e)
        logger.error('[OCR] 无法定位图片: %s', image_url)
        return None

    def _call_tencent_ocr(self, image_base64_str: str) -> list[dict]:
        service = 'ocr'
        host = 'ocr.tencentcloudapi.com'
        action = 'GeneralFastOCR'
        version = '2018-11-19'
        region = os.getenv('TENCENT_REGION', 'ap-guangzhou')
        algorithm = 'TC3-HMAC-SHA256'
        payload = json.dumps({'ImageBase64': image_base64_str})
        timestamp = int(time.time())
        date = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')
        http_method = 'POST'
        canonical_uri = '/'
        canonical_querystring = ''
        content_type = 'application/json; charset=utf-8'
        canonical_headers = f'content-type:{content_type}\nhost:{host}\nx-tc-action:{action.lower()}\n'
        signed_headers = 'content-type;host;x-tc-action'
        hashed_payload = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        canonical_request = f'{http_method}\n{canonical_uri}\n{canonical_querystring}\n{canonical_headers}\n{signed_headers}\n{hashed_payload}'
        credential_scope = f'{date}/{service}/tc3_request'
        hashed_canonical_request = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
        string_to_sign = f'{algorithm}\n{timestamp}\n{credential_scope}\n{hashed_canonical_request}'

        def _hmac(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()
        secret_date = _hmac(('TC3' + self.secret_key).encode('utf-8'), date)
        secret_service = _hmac(secret_date, service)
        secret_signing = _hmac(secret_service, 'tc3_request')
        signature = hmac.new(secret_signing, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
        authorization = f'{algorithm} Credential={self.secret_id}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}'
        headers = {'Authorization': authorization, 'Content-Type': content_type, 'Host': host, 'X-TC-Action': action, 'X-TC-Version': version, 'X-TC-Timestamp': str(timestamp), 'X-TC-Region': region}
        client = Client(timeout=60)
        resp = client.post(f'https://{host}/', content=payload, headers=headers)
        resp.raise_for_status()
        body = resp.json()
        if 'Response' not in body:
            logger.error('[OCR] 腾讯云返回异常: %s', body)
            return []
        if 'Error' in body['Response']:
            err = body['Response']['Error']
            logger.error('[OCR] 腾讯云业务错误: %s - %s', err.get('Code'), err.get('Message'))
            return []
        return body['Response'].get('TextDetections', [])
    _PARSE_PROMPT = '你是体检报告结构化解析助手。请从以下 OCR 识别结果中，整理出所有体检指标行。\n\n要求:\n1. 每行一条指标，按「项目名称  结果  单位  参考区间」的顺序、用两个以上空格分隔，保持报告原文\n2. 只保留检验指标行；忽略表头（检验项目 / 结果 / 单位 / 参考范围）、体检结论 / 小结、\n   科室与医生签名、页眉页脚、报告编号等非指标文字\n3. 修复 OCR 识别错误：把被误断的项目名连起来（如"低密度 脂蛋白胆固醇"→"低密度脂蛋白胆固醇"）\n4. 结果原文照抄（含 ↑ ↓ ± < > 等标记），不要换算、不要补全缺失数值\n5. 去重：同一项目只输出一次\n\n请严格以 JSON 格式返回:\n{"metric_lines": ["空腹血糖  5.4  mmol/L  3.9-6.1", "..."]}\n\nOCR 原文:\n'

    def _llm_parse_metric_lines(self, raw_text: str) -> list[str]:
        if not raw_text or len(raw_text.strip()) < 10:
            return []
        try:
            from app.gateway.adapters.llm import LLMAdapter
            llm = LLMAdapter()
            resp = llm.chat(messages=[{'role': 'user', 'content': self._PARSE_PROMPT + raw_text}], temperature=0.1, max_tokens=1024)
            content = resp.get('choices', [{}])[0].get('message', {}).get('content', '')
            logger.info('[OCR] LLM 整理返回 %d chars', len(content))
            result = self._parse_json(content)
            lines = result.get('metric_lines') or result.get('lines') or []
            if lines:
                lines = [str(i).strip() for i in lines if str(i).strip() and 4 <= len(str(i).strip()) <= 120]
                if lines:
                    logger.info('[OCR] LLM 整理出 %d 行指标: %s', len(lines), lines[:5])
                    return lines
        except Exception as e:
            logger.warning('[OCR] LLM 整理失败，回退正则: %s', e)
        return self._parse_metric_lines_regex(raw_text)

    def _parse_metric_lines_regex(self, raw_text: str) -> list[str]:
        if not raw_text:
            return []
        lines = [re.sub('\\s{2,}', '  ', l.strip()) for l in raw_text.split('\n')]
        lines = [l for l in lines if l]
        start = 0
        for i, line in enumerate(lines):
            if _HEADER_LINE_RE.search(line):
                start = i + 1
                break
        region = lines[start:]
        candidates: list[str] = []
        for line in region:
            if _SECTION_END_RE.search(line) and (not _RESULT_RE.search(line)):
                break
            if _HEADER_LINE_RE.search(line) or _SECTION_END_RE.search(line):
                continue
            if not _RESULT_RE.search(line):
                continue
            if not 4 <= len(line) <= 120:
                continue
            candidates.append(line)
        logger.info('[OCR] 正则定位出 %d 行候选指标: %s', len(candidates), candidates[:5])
        return candidates

    def _avg_confidence(self, detections: list[dict]) -> float:
        if not detections:
            return 0.0
        confs = [d.get('Confidence', 0) for d in detections]
        return sum(confs) / len(confs) / 100.0

    def _extract_vlm(self, image_url: str) -> dict:
        try:
            from app.gateway.adapters.vlm import VLMAdapter
            vlm = VLMAdapter()
            resp = vlm.analyze_image(image_url, OCR_PROMPT)
            content = resp.get('choices', [{}])[0].get('message', {}).get('content', '')
            logger.info('[OCR] VLM 返回 %d chars', len(content))
            result = self._parse_json(content)
            metric_lines = result.get('metric_lines') or []
            all_text = str(result.get('text') or '')
            if not all_text:
                all_text = '\n'.join((str(x) for x in metric_lines)) if metric_lines else str(result.get('raw', ''))
            return {'engine': 'dashscope', 'text': all_text, 'metric_lines': metric_lines, 'metrics': result.get('metrics', []), 'report_date': result.get('report_date', ''), 'institution': result.get('institution', ''), 'confidence': result.get('confidence')}
        except Exception as e:
            logger.error('[OCR] VLM 调用失败: %s', e)
            return {'engine': 'dashscope', 'text': '', 'confidence': None, 'metric_lines': [], 'metrics': [], 'error': str(e)}

    def _extract_aliyun(self, image_url: str) -> dict:
        return {'engine': 'aliyun', 'text': '', 'confidence': None, 'metric_lines': [], 'metrics': []}

    def _parse_json(self, content: str) -> dict:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            pass
        match = re.search('```(?:json)?\\s*\\n?(.*?)\\n?```', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        match = re.search('\\{.*\\}', content, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
        logger.warning('[OCR] 无法从 VLM 输出中解析 JSON，前 100 字符: %s', content[:100])
        return {'metric_lines': [], 'raw': content}
