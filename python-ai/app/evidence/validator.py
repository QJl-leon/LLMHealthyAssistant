import os
import re
import difflib
import logging
from typing import Optional
from dataclasses import dataclass
import psycopg2
from app.factory.repository import find_metric_by_name, get_metric_by_code, list_metric_catalog, list_metric_history, list_metrics_by_report
logger = logging.getLogger(__name__)
DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://lha:lha_dev@localhost:5432/lha')
VALUE_ABS_TOL = float(os.getenv('METRIC_VALUE_ABS_TOL', '1e-6'))
VALUE_REL_TOL = float(os.getenv('METRIC_VALUE_REL_TOL', '0.005'))

@dataclass
class ValidationResult:
    claim_id: str
    passed: bool
    failures: list[str]

    @property
    def is_real(self) -> bool:
        return self.passed

def validate_existence(claim_id: str, evidence_ids: list[str], registered_ids: Optional[set[str]]=None) -> ValidationResult:
    failures = []
    for eid in evidence_ids:
        if not eid:
            failures.append('空 evidence_id')
            continue
        if registered_ids is not None:
            if eid not in registered_ids:
                failures.append(f'evidence_id {eid} 不在本轮证据集中（伪造引用）')
            continue
        exists = _exists_in_db(eid)
        if exists is True:
            continue
        if exists is None:
            failures.append(f'证据库不可用，无法核验 evidence_id {eid}（保守拒答）')
        else:
            failures.append(f'evidence_id {eid} 不存在')
    return ValidationResult(claim_id=claim_id, passed=len(failures) == 0, failures=failures)

def _exists_in_db(evidence_id: str) -> Optional[bool]:
    try:
        conn = psycopg2.connect(DATABASE_URL)
    except psycopg2.Error as e:
        logger.warning('[Validator] 证据库不可用，无法核验 %s: %s（保守判失败）', evidence_id, e)
        return None
    try:
        with conn.cursor() as cur:
            cur.execute('SELECT 1 FROM parsed_documents WHERE id = %s LIMIT 1', (evidence_id,))
            return cur.fetchone() is not None
    except psycopg2.OperationalError as e:
        logger.warning('[Validator] 证据库连接中断 evidence_id=%s: %s（保守判失败）', evidence_id, e)
        return None
    except psycopg2.Error as e:
        logger.warning('[Validator] 证据查询失败 evidence_id=%s: %s', evidence_id, e)
        return False
    finally:
        conn.close()
HEALTH_TERMS: tuple[str, ...] = ('总胆固醇', '甘油三酯', '低密度脂蛋白', '高密度脂蛋白', '载脂蛋白', '空腹血糖', '餐后血糖', '糖化血红蛋白', '胰岛素', '收缩压', '舒张压', '血压', '心率', '静息心率', '谷丙转氨酶', '谷草转氨酶', '转氨酶', '肝功能', '肾功能', '尿酸', '肌酐', '尿素氮', 'eGFR', '血红蛋白', '白细胞', '血小板', '红细胞', '促甲状腺激素', '甲状腺', '骨密度', '维生素D', '维生素 D', '体质指数', 'BMI', '腰围', '体重', '体脂率', '肺结节', '有氧运动', '抗阻训练', '力量训练', '柔韧', '步数', '配速', '每周运动', '膳食纤维', '钠盐', '食盐', '脂肪供能', '饮酒', '吸烟', '睡眠', '久坐', '复查', '随访', '参考区间', '上限', '下限', '偏高', '偏低', '达标')
_CJK_RE = re.compile('[\\u4e00-\\u9fff]')

def _extract_keywords(text: str) -> list[str]:
    text = (text or '').strip()
    if not text:
        return []
    keywords: list[str] = []
    lowered = text.lower()
    for term in HEALTH_TERMS:
        if term.lower() in lowered:
            keywords.append(term)
    for m in re.finditer('\\d+(?:\\.\\d+)?(?:\\s*/\\s*\\d+(?:\\.\\d+)?)?', text):
        keywords.append(m.group(0).replace(' ', ''))
    for seg in re.split('[\\s,，。;；:：、()（）\\[\\]【】<>≤≥=~～]+', text):
        if len(seg) < 2 or not _CJK_RE.search(seg):
            continue
        for n in (2, 3, 4):
            keywords.extend((seg[i:i + n] for i in range(0, len(seg) - n + 1)))
    return list(dict.fromkeys((k for k in keywords if k)))[:40]

def validate_support(claim_id: str, claim_text: str, quote: str) -> ValidationResult:
    failures = []
    claim_keywords = _extract_keywords(claim_text)
    quote_lower = (quote or '').lower()
    match_count = sum((1 for kw in claim_keywords if kw.lower() in quote_lower))
    if match_count == 0 and len(claim_text or '') > 3:
        failures.append(f'''引用内容不支持结论："{(claim_text or '')[:50]}"''')
    return ValidationResult(claim_id=claim_id, passed=len(failures) == 0, failures=failures)

def _values_match(claimed: float, actual: float, abs_tol: float=VALUE_ABS_TOL, rel_tol: float=VALUE_REL_TOL) -> bool:
    try:
        c = float(claimed)
        a = float(actual)
    except (TypeError, ValueError):
        return False
    return abs(c - a) <= max(abs_tol, abs(a) * rel_tol)

def _fetch_user_metrics(user_id: str, metric_code: str, report_id: Optional[str]):
    try:
        if report_id:
            rows = [m for m in list_metrics_by_report(report_id) if m.metric_code == metric_code and m.user_id == user_id]
            return (rows, '')
        rows = list_metric_history(user_id, metric_code, limit=10)
        return (rows, '')
    except psycopg2.Error as e:
        logger.warning('[Validator] 体检数据不可用 user=%s metric=%s: %s（保守判失败）', user_id, metric_code, e)
        return ([], str(e))

def _fetch_metric_catalog(metric_code: str):
    try:
        return (get_metric_by_code(metric_code), '')
    except psycopg2.Error as e:
        logger.warning('[Validator] 指标目录不可用 metric=%s: %s（保守判失败）', metric_code, e)
        return (None, str(e))

def _catalog_ref_text(catalog) -> str:
    ref = (getattr(catalog, 'ref_text', '') or '').strip()
    if ref:
        return ref
    lo = getattr(catalog, 'ref_low', None)
    hi = getattr(catalog, 'ref_high', None)
    unit = (getattr(catalog, 'unit', '') or '').strip()
    if lo is not None and hi is not None:
        return f'{lo}~{hi} {unit}'.strip()
    if hi is not None:
        return f'<{hi} {unit}'.strip()
    if lo is not None:
        return f'>{lo} {unit}'.strip()
    return ''

def _normalize_ref(text: str) -> str:
    s = (text or '').strip().lower()
    for src, dst in (('～', '~'), ('—', '-'), ('－', '-'), ('≤', '<'), ('≥', '>')):
        s = s.replace(src, dst)
    return re.sub('\\s+', '', s)

def validate_metric_value(claim_id: str, metric_code: str, claimed_value: Optional[float], user_id: str, report_id: Optional[str]=None, *, claimed_ref_low: Optional[float]=None, claimed_ref_high: Optional[float]=None, claimed_ref_text: str='', abs_tol: float=VALUE_ABS_TOL, rel_tol: float=VALUE_REL_TOL) -> ValidationResult:
    failures: list[str] = []
    if not metric_code:
        return ValidationResult(claim_id, False, ['缺少 metric_code，无法核验指标数值'])
    has_claim = claimed_value is not None or claimed_ref_low is not None or claimed_ref_high is not None or bool((claimed_ref_text or '').strip())
    if not has_claim:
        logger.warning('[Validator] claim=%s 未声明任何数值 / 参考区间，数字校验不适用', claim_id)
        return ValidationResult(claim_id, True, [])
    if claimed_value is not None:
        if not user_id:
            failures.append(f'缺少 user_id，无法核验 {metric_code} 的数值（保守拒答）')
        else:
            metrics, err = _fetch_user_metrics(user_id, metric_code, report_id)
            if err:
                failures.append(f'体检数据源不可用，无法核验 {metric_code} 的数值（保守拒答）')
            elif not metrics:
                failures.append(f'用户体检记录中没有 {metric_code}，无法核验声称值 {claimed_value}（保守拒答）')
            else:
                numeric = [m for m in metrics if m.value_num is not None]
                if not numeric:
                    logger.warning('[Validator] %s 无数值结果，跳过数值核验（声称 %s）', metric_code, claimed_value)
                elif not any((_values_match(claimed_value, m.value_num, abs_tol, rel_tol) for m in numeric)):
                    sample = numeric[0]
                    unit = sample.unit or ''
                    failures.append(f"{metric_code} 数值不匹配：结论声称 {claimed_value}{unit}，体检记录为 {sample.value_num}{unit}（{sample.measured_at or '时间未知'}）")
    needs_ref = claimed_ref_low is not None or claimed_ref_high is not None or bool((claimed_ref_text or '').strip())
    if needs_ref:
        catalog, err = _fetch_metric_catalog(metric_code)
        if err:
            failures.append(f'指标目录不可用，无法核验 {metric_code} 的参考区间（保守拒答）')
        elif catalog is None:
            failures.append(f'指标目录中没有 {metric_code}，无法核验参考区间（保守拒答）')
        else:
            if claimed_ref_low is not None and (catalog.ref_low is None or not _values_match(claimed_ref_low, catalog.ref_low, abs_tol, rel_tol)):
                failures.append(f'{metric_code} 参考下限不匹配：结论声称 {claimed_ref_low}，目录为 {catalog.ref_low}')
            if claimed_ref_high is not None and (catalog.ref_high is None or not _values_match(claimed_ref_high, catalog.ref_high, abs_tol, rel_tol)):
                failures.append(f'{metric_code} 参考上限不匹配：结论声称 {claimed_ref_high}，目录为 {catalog.ref_high}')
            if (claimed_ref_text or '').strip():
                expected = _catalog_ref_text(catalog)
                if _normalize_ref(claimed_ref_text) != _normalize_ref(expected):
                    failures.append(f"{metric_code} 参考区间与目录不一致：结论为 '{claimed_ref_text}'，目录为 '{expected}'")
    return ValidationResult(claim_id=claim_id, passed=len(failures) == 0, failures=failures)

def _lookup_metric_name_db(name: str) -> tuple[Optional[bool], list[str]]:
    try:
        if find_metric_by_name(name) is not None:
            return (True, [])
        rows = list_metric_catalog()
    except psycopg2.Error as e:
        logger.warning("[Validator] 指标目录不可用，无法核验项目名 '%s': %s（保守判失败）", name, e)
        return (None, [])
    candidates: list[str] = []
    for row in rows:
        for cand in (row.name_cn, row.name_en, row.metric_code):
            if cand:
                candidates.append(cand)
    similar = difflib.get_close_matches(name, candidates, n=3, cutoff=0.3)
    if not similar:
        similar = [c for c in candidates if name in c or c in name][:3]
    return (False, similar)

def validate_metric_name(claim_id: str, name: str, name_lookup=None) -> ValidationResult:
    failures: list[str] = []
    candidate = (name or '').strip()
    if not candidate:
        return ValidationResult(claim_id, False, ['空的体检项目名'])
    lookup = name_lookup or _lookup_metric_name_db
    exists, similar = lookup(candidate)
    if exists is None:
        failures.append(f"指标目录不可用，无法核验体检项目名 '{candidate}'（保守拒答）")
    elif not exists:
        if similar:
            failures.append(f"体检项目名 '{candidate}' 不存在，最接近的候选: {similar}")
        else:
            failures.append(f"体检项目名 '{candidate}' 在指标目录中不存在")
    return ValidationResult(claim_id=claim_id, passed=len(failures) == 0, failures=failures)

def refuse_if_no_evidence(claims: list[dict], evidence_list: list) -> tuple[bool, str]:
    if not evidence_list:
        return (True, '未找到支持任何结论的证据，拒绝生成报告')
    if not claims:
        return (True, '报告为空，拒绝生成')
    registered = {str(e.get('evidence_id') or e.get('id') or '') for e in evidence_list if isinstance(e, dict)}
    registered.discard('')
    fact_claims = [c for c in claims if c.get('type') == 'fact' or c.get('evidence_ids')]
    supported = 0
    for claim in claims:
        eids = [str(x) for x in claim.get('evidence_ids') or [] if x]
        if not eids:
            continue
        if all((eid in registered for eid in eids)):
            supported += 1
        else:
            return (True, f"结论 {claim.get('claim_id', '?')} 引用了不存在的证据，拒绝生成")
    if fact_claims and supported == 0:
        return (True, '结论缺少可核验证据绑定，拒绝生成报告')
    return (False, '')

def validate_advice_has_evidence(advice_claims: list[dict], evidence: list) -> ValidationResult:
    registered = {str(e.get('evidence_id') or e.get('id') or '') for e in evidence if isinstance(e, dict)}
    registered.discard('')
    failures: list[str] = []
    first_failed_id = ''
    for idx, claim in enumerate(advice_claims or []):
        if not isinstance(claim, dict):
            continue
        cid = str(claim.get('claim_id') or f'advice_{idx + 1}')
        eids = [str(x) for x in claim.get('evidence_ids') or [] if x]
        claim_failed = False
        if not eids:
            failures.append(f'建议 {cid} 未绑定任何 evidence_id（无证据不给建议）')
            claim_failed = True
        elif registered and (not any((eid in registered for eid in eids))):
            failures.append(f"建议 {cid} 引用的证据不在本轮证据集中（{', '.join(eids)}）")
            claim_failed = True
        if claim_failed and (not first_failed_id):
            first_failed_id = cid
    return ValidationResult(claim_id=first_failed_id, passed=len(failures) == 0, failures=failures)

def validate_claims_against_evidence(claims: list[dict], evidence_list: list) -> list[dict]:
    registered = {str(e.get('evidence_id') or e.get('id') or '') for e in evidence_list if isinstance(e, dict)}
    registered.discard('')
    errors: list[dict] = []
    for claim in claims:
        cid = str(claim.get('claim_id') or '')
        eids = [str(x) for x in claim.get('evidence_ids') or [] if x]
        if claim.get('type') == 'fact' and (not eids):
            errors.append({'error_code': 'CITATION_MISMATCH', 'message': f'事实结论 {cid} 无 evidence_ids', 'claim_id': cid})
            continue
        result = validate_existence(cid, eids, registered_ids=registered)
        if not result.passed:
            errors.append({'error_code': 'CITATION_MISMATCH', 'message': '; '.join(result.failures), 'claim_id': cid})
    return errors
