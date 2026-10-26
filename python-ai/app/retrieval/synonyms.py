from __future__ import annotations
import logging
import re
logger = logging.getLogger(__name__)
SYNONYM_MAP: dict[str, tuple[str, ...]] = {'血脂': ('总胆固醇', '甘油三酯', '低密度脂蛋白胆固醇', '高密度脂蛋白胆固醇'), '血脂高': ('总胆固醇', '甘油三酯', '低密度脂蛋白胆固醇'), '胆固醇': ('总胆固醇',), '总胆固醇': ('总胆固醇',), 'tc': ('总胆固醇',), '坏胆固醇': ('低密度脂蛋白胆固醇',), 'ldl': ('低密度脂蛋白胆固醇',), 'ldl-c': ('低密度脂蛋白胆固醇',), '低密度': ('低密度脂蛋白胆固醇',), '好胆固醇': ('高密度脂蛋白胆固醇',), 'hdl': ('高密度脂蛋白胆固醇',), 'hdl-c': ('高密度脂蛋白胆固醇',), '高密度': ('高密度脂蛋白胆固醇',), '甘油三酯': ('甘油三酯',), '三酸甘油酯': ('甘油三酯',), '中性脂肪': ('甘油三酯',), 'tg': ('甘油三酯',), '脂蛋白a': ('脂蛋白(a)',), '脂蛋白(a)': ('脂蛋白(a)',), 'lpa': ('脂蛋白(a)',), '载脂蛋白a1': ('载脂蛋白A1',), '载脂蛋白b': ('载脂蛋白B',), 'apoa1': ('载脂蛋白A1',), 'apob': ('载脂蛋白B',), '血稠': ('总胆固醇', '甘油三酯', '低密度脂蛋白胆固醇'), '血糖': ('空腹血糖', '糖化血红蛋白'), '血糖高': ('空腹血糖', '糖化血红蛋白'), '空腹血糖': ('空腹血糖',), 'fpg': ('空腹血糖',), '餐后血糖': ('口服葡萄糖耐量试验2小时血糖',), 'ogtt': ('口服葡萄糖耐量试验2小时血糖',), '糖耐量': ('口服葡萄糖耐量试验2小时血糖',), '糖化血红蛋白': ('糖化血红蛋白',), '糖化': ('糖化血红蛋白',), 'hba1c': ('糖化血红蛋白',), '糖尿病': ('空腹血糖', '糖化血红蛋白'), '转氨酶': ('丙氨酸氨基转移酶', '天门冬氨酸氨基转移酶'), '肝功能': ('丙氨酸氨基转移酶', '天门冬氨酸氨基转移酶', 'γ-谷氨酰基转移酶'), '谷丙转氨酶': ('丙氨酸氨基转移酶',), 'alt': ('丙氨酸氨基转移酶',), 'gpt': ('丙氨酸氨基转移酶',), '谷草转氨酶': ('天门冬氨酸氨基转移酶',), 'ast': ('天门冬氨酸氨基转移酶',), 'got': ('天门冬氨酸氨基转移酶',), '谷氨酰转肽酶': ('γ-谷氨酰基转移酶',), 'ggt': ('γ-谷氨酰基转移酶',), '碱性磷酸酶': ('碱性磷酸酶',), 'alp': ('碱性磷酸酶',), '脂肪肝': ('丙氨酸氨基转移酶', '天门冬氨酸氨基转移酶', 'γ-谷氨酰基转移酶'), '尿酸': ('血尿酸',), '血尿酸': ('血尿酸',), '痛风': ('血尿酸',), 'ua': ('血尿酸',), '肌酐': ('血清肌酐',), '肾功能': ('血清肌酐', '血清尿素'), 'crea': ('血清肌酐',), '尿素': ('血清尿素',), '尿素氮': ('血清尿素',), 'bun': ('血清尿素',), '血压': ('收缩压', '舒张压'), '高血压': ('收缩压', '舒张压'), '高压': ('收缩压',), '低压': ('舒张压',), 'sbp': ('收缩压',), 'dbp': ('舒张压',), '三高': ('收缩压', '舒张压', '空腹血糖', '总胆固醇'), '血红蛋白': ('血红蛋白',), '血色素': ('血红蛋白',), '贫血': ('血红蛋白', '红细胞比容'), 'hb': ('血红蛋白',), 'hgb': ('血红蛋白',), '白细胞': ('白细胞计数',), '白血球': ('白细胞计数',), 'wbc': ('白细胞计数',), '红细胞': ('红细胞计数',), '红血球': ('红细胞计数',), 'rbc': ('红细胞计数',), '血小板': ('血小板计数',), 'plt': ('血小板计数',), '中性粒细胞': ('中性粒细胞百分数',), 'neut': ('中性粒细胞百分数',), '红细胞比容': ('红细胞比容',), '血细胞比容': ('红细胞比容',), 'hct': ('红细胞比容',), 'bmi': ('体重指数',), '体重指数': ('体重指数',), '身体质量指数': ('体重指数',), '胖不胖': ('体重指数', '腰围'), '腰围': ('腰围',), 'waist': ('腰围',), '体重': ('体重',), '身高': ('身高',), '甲状腺': ('促甲状腺激素',), '促甲状腺激素': ('促甲状腺激素',), 'tsh': ('促甲状腺激素',)}
_ASCII_KEYS = {k for k in SYNONYM_MAP if k.isascii()}

def _already_present(query: str, term: str) -> bool:
    return term in query

def expand_terms(query: str, *, max_terms: int=6) -> str:
    q = (query or '').strip()
    if not q:
        return query
    lowered = q.lower()
    hits: list[str] = []
    for key, terms in SYNONYM_MAP.items():
        if key in _ASCII_KEYS:
            matched = key in lowered
        else:
            matched = key in q
        if not matched:
            continue
        for t in terms:
            if not _already_present(q, t) and t not in hits:
                hits.append(t)
    if not hits:
        return query
    added = hits[:max_terms]
    logger.info('[Synonyms] 术语归一: %s → 追加 %s', q[:30], added)
    return f"{q} {' '.join(added)}"

def canonical_terms(query: str) -> list[str]:
    q = (query or '').strip()
    if not q:
        return []
    lowered = q.lower()
    out: list[str] = []
    for key, terms in SYNONYM_MAP.items():
        matched = key in lowered if key in _ASCII_KEYS else key in q
        if matched:
            for t in terms:
                if t not in out:
                    out.append(t)
    return out

def coverage_of_metric_names(names: list[str]) -> dict:
    covered = {n for terms in SYNONYM_MAP.values() for n in terms}
    missing = [n for n in names if n not in covered]
    return {'total': len(names), 'covered': len(names) - len(missing), 'missing': missing}
