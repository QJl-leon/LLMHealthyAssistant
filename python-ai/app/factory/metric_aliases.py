METRIC_ALIASES: dict[str, str] = {'谷丙转氨酶': 'ALT', '丙氨酸转氨酶': 'ALT', '谷草转氨酶': 'AST', '天冬氨酸氨基转移酶': 'AST', '谷氨酰转肽酶': 'GGT', '谷氨酰转移酶': 'GGT', 'γ-谷氨酰转肽酶': 'GGT', 'γ-GT': 'GGT', 'γGT': 'GGT', 'r-GT': 'GGT', '血色素': 'HGB', '红细胞压积': 'HCT', '红细胞比积': 'HCT', '血细胞比容': 'HCT', '中性粒细胞百分比': 'NEUT_PCT', '中性粒细胞比例': 'NEUT_PCT', '三酰甘油': 'TG', '甘油三脂': 'TG', '葡萄糖': 'GLU_FAST', '糖化血红素': 'HBA1C', '高压': 'SBP', '低压': 'DBP', '尿素氮': 'UREA', '血尿素氮': 'UREA', 'BUN': 'UREA', '体质指数': 'BMI', '体质量指数': 'BMI', '促甲状腺素': 'TSH'}

def resolve_metric_alias(name: str) -> str | None:
    if not name:
        return None
    n = str(name).strip()
    if not n:
        return None
    if n in METRIC_ALIASES:
        return METRIC_ALIASES[n]
    for alias in sorted(METRIC_ALIASES, key=len, reverse=True):
        if alias in n:
            return METRIC_ALIASES[alias]
    return None
