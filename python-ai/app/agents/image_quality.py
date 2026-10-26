from __future__ import annotations
import logging
from typing import Any
logger = logging.getLogger(__name__)
POSITION_LABELS: dict[str, str] = {'front': '报告封面', 'exam_report': '体检报告首页（机构/体检日期）', 'lab_sheet': '化验单/检验指标表', 'other': '其他资料'}
_METRIC_BEARING_POSITIONS = {'exam_report', 'lab_sheet'}
_MIN_SIDE = 200
_MIN_PIXELS = 80000
_BLUR_VAR_MIN = 18.0
_DARK_MEAN = 45.0
_BRIGHT_MEAN = 220.0
_BORDER_RATIO = 0.08
_CROP_EDGE_BRIGHT = 245.0

def position_label(position: str) -> str:
    return POSITION_LABELS.get(position or '', position or '图片')

def assess_images(images: list[dict[str, Any]], *, coverage_images: list[dict[str, Any]] | None=None) -> list[dict[str, Any]]:
    issues: list[dict[str, Any]] = []
    coverage = coverage_images if coverage_images is not None else images
    if not coverage and (not images):
        return []
    positions = {img.get('position') or 'unknown' for img in coverage or []}
    if coverage and (not _METRIC_BEARING_POSITIONS & positions):
        issues.append({'code': 'MISSING_LAB_SHEET_SHOT', 'position': 'lab_sheet', 'severity': 'high', 'action': '缺少化验单/检验指标表，请补拍报告中的检验项目表格区域（项目/结果/单位/参考区间需清晰可读）'})
    for img in images or []:
        issues.extend(_assess_one(img))
    issues = _prioritize(issues)[:3]
    return issues

def _prioritize(issues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rank = {'high': 0, 'medium': 1, 'low': 2}
    return sorted(issues, key=lambda x: rank.get(x.get('severity', 'medium'), 9))

def _assess_one(img: dict[str, Any]) -> list[dict[str, Any]]:
    pos = img.get('position') or 'unknown'
    label = position_label(pos)
    url = img.get('presigned_url') or ''
    key = img.get('key') or ''
    data = _load_image_bytes(url, key)
    if not data:
        return [{'code': 'IMAGE_UNREADABLE', 'position': pos, 'severity': 'high', 'action': f'「{label}」无法读取，请重新上传该图位照片'}]
    try:
        from PIL import Image, ImageFilter, ImageStat
        import io
        pil = Image.open(io.BytesIO(data))
        try:
            from PIL import ImageOps
            pil = ImageOps.exif_transpose(pil)
        except Exception:
            pass
        w, h = pil.size
        gray = pil.convert('L')
        found: list[dict[str, Any]] = []
        if min(w, h) < _MIN_SIDE or w * h < _MIN_PIXELS:
            found.append({'code': 'IMAGE_TOO_SMALL', 'position': pos, 'severity': 'high', 'action': f'「{label}」分辨率过低（{w}×{h}），请靠近拍摄或提高清晰度后重拍'})
        edges = gray.filter(ImageFilter.FIND_EDGES)
        edge_var = float(ImageStat.Stat(edges).var[0])
        if edge_var < _BLUR_VAR_MIN:
            found.append({'code': 'IMAGE_BLURRY', 'position': pos, 'severity': 'high', 'action': f'「{label}」疑似模糊（对焦不足），请保持手机稳定并确保文字对焦清晰后重拍'})
        mean = float(ImageStat.Stat(gray).mean[0])
        if mean < _DARK_MEAN:
            found.append({'code': 'IMAGE_TOO_DARK', 'position': pos, 'severity': 'medium', 'action': f'「{label}」曝光不足，请在光线充足处重拍，避免阴影遮挡文字'})
        elif mean > _BRIGHT_MEAN:
            found.append({'code': 'IMAGE_GLARE', 'position': pos, 'severity': 'medium', 'action': f'「{label}」疑似过曝或反光，请调整拍摄角度避开反光后重拍'})
        if _looks_cropped(gray):
            found.append({'code': 'IMAGE_CROPPED', 'position': pos, 'severity': 'medium', 'action': f'「{label}」可能被裁切不完整，请将目标区域完整纳入画面后重拍'})
        if pos == 'lab_sheet' and min(w, h) >= _MIN_SIDE and (edge_var >= _BLUR_VAR_MIN):
            pass
        return found
    except Exception as e:
        logger.warning('[QC] 评估失败 key=%s: %s', key, e)
        return [{'code': 'IMAGE_QC_ERROR', 'position': pos, 'severity': 'medium', 'action': f'「{label}」质量检查失败，请换一张更清晰的照片重试'}]

def _looks_cropped(gray) -> bool:
    from PIL import ImageStat
    w, h = gray.size
    bw = max(2, int(w * _BORDER_RATIO))
    bh = max(2, int(h * _BORDER_RATIO))
    top = gray.crop((0, 0, w, bh))
    bottom = gray.crop((0, h - bh, w, h))
    left = gray.crop((0, 0, bw, h))
    right = gray.crop((w - bw, 0, w, h))
    center = gray.crop((bw, bh, w - bw, h - bh))
    if center.size[0] < 10 or center.size[1] < 10:
        return False
    border_mean = (float(ImageStat.Stat(top).mean[0]) + float(ImageStat.Stat(bottom).mean[0]) + float(ImageStat.Stat(left).mean[0]) + float(ImageStat.Stat(right).mean[0])) / 4.0
    center_mean = float(ImageStat.Stat(center).mean[0])
    return border_mean >= _CROP_EDGE_BRIGHT and border_mean - center_mean > 40

def _load_image_bytes(url: str, key: str) -> bytes | None:
    from app.agents.vision_agent import _fetch_image_bytes
    if url:
        data = _fetch_image_bytes(url)
        if data:
            return data
    if key:
        return _fetch_image_bytes(f'/uploads/{key}')
    return None

def actions_from_issues(issues: list[dict[str, Any]]) -> list[str]:
    return [i['action'] for i in issues if i.get('action')]

def guidance_from_issues(issues: list[dict[str, Any]]) -> str:
    if not issues:
        return '图片质量合格，可继续分析'
    labels = sorted({position_label(i.get('position', '')) for i in issues})
    return f"检测到 {len(issues)} 项图片问题（涉及：{'、'.join(labels)}）。请按下列具体动作补拍后继续，最多三项。"
