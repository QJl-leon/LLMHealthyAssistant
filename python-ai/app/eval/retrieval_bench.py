from __future__ import annotations
import json
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime
REPORT_DIR = os.path.join(os.path.dirname(__file__), 'reports')
HEALTH_GUIDELINES: list[dict] = [{'id': 'g1', 'doc_type': 'guideline', 'evidence_level': 'A', 'title': '中国血脂管理指南（2023）', 'org': '中国血脂管理指南修订联合委员会', 'year': 2023, 'topic': '血脂,运动', 'content': '推荐以中等强度有氧运动为主，每周累计 150 分钟以上，可降低甘油三酯、升高高密度脂蛋白胆固醇；低密度脂蛋白胆固醇升高者应同步进行饮食干预并咨询医生。'}, {'id': 'g2', 'doc_type': 'guideline', 'evidence_level': 'A', 'title': '中国2型糖尿病防治指南（2020）', 'org': '中华医学会糖尿病学分会', 'year': 2020, 'topic': '血糖,运动', 'content': '规律有氧运动结合抗阻训练可改善胰岛素敏感性；餐后步行有助于降低餐后血糖峰值，每周至少 150 分钟中等强度运动。'}, {'id': 'g3', 'doc_type': 'guideline', 'evidence_level': 'A', 'title': '中国高血压防治指南（2018）', 'org': '中国高血压防治指南修订委员会', 'year': 2018, 'topic': '血压,运动', 'content': '有氧运动可使收缩压平均下降 5-8mmHg，建议每周 5-7 天、每次 30 分钟中等强度运动；血压未控制达标者应避免高强度运动。'}, {'id': 'g4', 'doc_type': 'guideline', 'evidence_level': 'A', 'title': '中国高尿酸血症与痛风诊疗指南（2019）', 'org': '中华医学会内分泌学分会', 'year': 2019, 'topic': '尿酸,运动,饮食', 'content': '急性发作期应避免运动；缓解期推荐低强度有氧运动，避免剧烈运动诱发痛风，同时限制高嘌呤饮食并保证饮水。'}, {'id': 'g5', 'doc_type': 'guideline', 'evidence_level': 'A', 'title': '非酒精性脂肪性肝病防治指南（2018）', 'org': '中华医学会肝病学分会', 'year': 2018, 'topic': '肝功能,运动', 'content': '每周 150 分钟中等强度有氧运动可降低肝脏脂肪含量，改善谷丙转氨酶水平，配合饮食控制效果更佳。'}, {'id': 'g6', 'doc_type': 'consensus', 'evidence_level': 'B', 'title': '中国成人超重与肥胖症防治专家共识（2021）', 'org': '中国营养学会', 'year': 2021, 'topic': '体格,运动', 'content': '运动处方应包括有氧与抗阻结合，每周至少 150 分钟中等强度运动，配合能量摄入控制以实现体重管理。'}, {'id': 'g7', 'doc_type': 'consensus', 'evidence_level': 'B', 'title': '中国慢性肾脏病患者运动康复专家共识（2021）', 'org': '中国康复医学会', 'year': 2021, 'topic': '肾功能,运动', 'content': '慢性肾病患者应在评估后行中低强度有氧运动，避免高强度运动和脱水，运动中出现不适需立即停止。'}, {'id': 'g8', 'doc_type': 'consensus', 'evidence_level': 'B', 'title': '他汀类药物安全性管理专家共识（2022）', 'org': '中国药学会', 'year': 2022, 'topic': '血脂,用药', 'content': '服用他汀期间进行运动应关注肌痛与肌酸激酶升高，出现肌肉症状需及时就医评估，必要时调整运动强度。'}, {'id': 'g9', 'doc_type': 'guideline', 'evidence_level': 'A', 'title': '中国居民膳食指南（2022）', 'org': '中国营养学会', 'year': 2022, 'topic': '饮食,生活方式', 'content': '食物多样、合理搭配；少盐少油、控糖限酒；规律进餐、足量饮水，保持吃动平衡以维持健康体重。'}, {'id': 'g10', 'doc_type': 'cohort', 'evidence_level': 'B', 'title': '睡眠时长与代谢指标队列研究（2020）', 'org': '中华流行病学杂志', 'year': 2020, 'topic': '睡眠,代谢', 'content': '睡眠不足与胰岛素抵抗、体重增加相关，建议成人保证 7-8 小时睡眠，规律作息有助于代谢指标改善。'}]
HEALTH_CASES: list[dict] = [{'id': 'c1', 'case_code': 'CASE-0001', 'age_band': '45-54', 'sex': 'M', 'chief_complaint': '体检发现血脂异常', 'findings': '低密度脂蛋白胆固醇 4.2 mmol/L 偏高', 'metrics': {'LDL_C': 4.2, 'TG': 2.1}, 'diagnosis': '高脂血症', 'intervention': '中等强度有氧运动每周 150 分钟 + 饮食控制', 'outcome': '3 个月后低密度脂蛋白胆固醇降至 3.2 mmol/L', 'evidence_level': 'C'}, {'id': 'c2', 'case_code': 'CASE-0002', 'age_band': '50-59', 'sex': 'F', 'chief_complaint': '血糖偏高', 'findings': '空腹血糖 6.8 mmol/L，糖化血红蛋白 6.5%', 'metrics': {'GLU': 6.8, 'HBA1C': 6.5}, 'diagnosis': '糖调节受损', 'intervention': '餐后快走 30 分钟每周 5 次 + 抗阻训练 2 次', 'outcome': '6 个月后空腹血糖降至 5.9 mmol/L', 'evidence_level': 'C'}, {'id': 'c3', 'case_code': 'CASE-0003', 'age_band': '35-44', 'sex': 'M', 'chief_complaint': '血压升高', 'findings': '血压 150/95 mmHg', 'metrics': {'SBP': 150, 'DBP': 95}, 'diagnosis': '1 级高血压', 'intervention': '有氧运动 + 减重，限制钠盐摄入', 'outcome': '血压降至 132/84 mmHg', 'evidence_level': 'C'}, {'id': 'c4', 'case_code': 'CASE-0004', 'age_band': '40-49', 'sex': 'M', 'chief_complaint': '尿酸升高', 'findings': '血尿酸 520 umol/L', 'metrics': {'UA': 520}, 'diagnosis': '高尿酸血症', 'intervention': '低强度有氧运动，避免剧烈运动，多饮水', 'outcome': '尿酸降至 420 umol/L', 'evidence_level': 'C'}, {'id': 'c5', 'case_code': 'CASE-0005', 'age_band': '55-64', 'sex': 'F', 'chief_complaint': '体检发现脂肪肝', 'findings': '谷丙转氨酶 68 U/L 升高', 'metrics': {'ALT': 68}, 'diagnosis': '非酒精性脂肪肝', 'intervention': '每周 150 分钟中等强度有氧运动 + 饮食干预', 'outcome': '6 个月后谷丙转氨酶恢复正常', 'evidence_level': 'C'}, {'id': 'c6', 'case_code': 'CASE-0006', 'age_band': '60-69', 'sex': 'M', 'chief_complaint': '服用他汀后运动出现肌肉酸痛', 'findings': '肌酸激酶轻度升高，低密度脂蛋白胆固醇 3.6 mmol/L', 'metrics': {'LDL_C': 3.6}, 'diagnosis': '他汀相关肌肉症状待评估', 'intervention': '调整运动强度，监测肌酸激酶，必要时就医', 'outcome': '症状缓解，继续规律低强度运动', 'evidence_level': 'C'}, {'id': 'c7', 'case_code': 'CASE-0007', 'age_band': '30-39', 'sex': 'F', 'chief_complaint': '体重超标', 'findings': '体重指数 28.5 kg/m2', 'metrics': {'BMI': 28.5}, 'diagnosis': '超重', 'intervention': '有氧与抗阻联合运动处方，每周 150 分钟', 'outcome': '体重指数降至 25.0 kg/m2', 'evidence_level': 'C'}, {'id': 'c8', 'case_code': 'CASE-0008', 'age_band': '45-54', 'sex': 'M', 'chief_complaint': '慢性肾病运动咨询', 'findings': '肌酐 105 umol/L，估算肾小球滤过率偏低', 'metrics': {'CREA': 105}, 'diagnosis': '慢性肾脏病 3 期', 'intervention': '中低强度有氧运动，评估后进行，避免脱水', 'outcome': '体能改善，肾功能稳定', 'evidence_level': 'C'}]
HEALTH_METRICS: list[dict] = [{'metric_code': 'LDL_C', 'name_cn': '低密度脂蛋白胆固醇', 'name_en': 'LDL-C', 'category': '血脂', 'unit': 'mmol/L', 'ref_low': None, 'ref_high': 3.4, 'ref_text': '<3.4 mmol/L', 'direction': 'high', 'advice_hint': '偏高提示动脉粥样硬化风险，建议生活方式干预并咨询医生'}, {'metric_code': 'TG', 'name_cn': '甘油三酯', 'name_en': 'TG', 'category': '血脂', 'unit': 'mmol/L', 'ref_low': None, 'ref_high': 1.7, 'ref_text': '<1.7 mmol/L', 'direction': 'high', 'advice_hint': '偏高与饮食和运动不足相关，建议控制体重与限酒'}, {'metric_code': 'HDL_C', 'name_cn': '高密度脂蛋白胆固醇', 'name_en': 'HDL-C', 'category': '血脂', 'unit': 'mmol/L', 'ref_low': 1.0, 'ref_high': None, 'ref_text': '>1.0 mmol/L', 'direction': 'low', 'advice_hint': '偏低提示保护性不足，规律有氧运动有助于升高'}, {'metric_code': 'TC', 'name_cn': '总胆固醇', 'name_en': 'TC', 'category': '血脂', 'unit': 'mmol/L', 'ref_low': None, 'ref_high': 5.2, 'ref_text': '<5.2 mmol/L', 'direction': 'high', 'advice_hint': '偏高建议饮食与运动干预'}, {'metric_code': 'GLU', 'name_cn': '空腹血糖', 'name_en': 'GLU', 'category': '血糖', 'unit': 'mmol/L', 'ref_low': 3.9, 'ref_high': 6.1, 'ref_text': '3.9~6.1 mmol/L', 'direction': 'both', 'advice_hint': '偏高提示糖代谢异常，建议运动与饮食干预并复查'}, {'metric_code': 'HBA1C', 'name_cn': '糖化血红蛋白', 'name_en': 'HbA1c', 'category': '血糖', 'unit': '%', 'ref_low': None, 'ref_high': 6.0, 'ref_text': '<6.0 %', 'direction': 'high', 'advice_hint': '反映近 3 个月平均血糖水平'}, {'metric_code': 'ALT', 'name_cn': '谷丙转氨酶', 'name_en': 'ALT', 'category': '肝功能', 'unit': 'U/L', 'ref_low': None, 'ref_high': 40, 'ref_text': '<40 U/L', 'direction': 'high', 'advice_hint': '偏高提示肝细胞损伤，需结合脂肪肝评估'}, {'metric_code': 'AST', 'name_cn': '谷草转氨酶', 'name_en': 'AST', 'category': '肝功能', 'unit': 'U/L', 'ref_low': None, 'ref_high': 40, 'ref_text': '<40 U/L', 'direction': 'high', 'advice_hint': '偏高需结合谷丙转氨酶综合判断'}, {'metric_code': 'UA', 'name_cn': '尿酸', 'name_en': 'UA', 'category': '代谢', 'unit': 'umol/L', 'ref_low': None, 'ref_high': 420, 'ref_text': '<420 umol/L', 'direction': 'high', 'advice_hint': '偏高注意低嘌呤饮食，急性期避免运动'}, {'metric_code': 'CREA', 'name_cn': '肌酐', 'name_en': 'CREA', 'category': '肾功能', 'unit': 'umol/L', 'ref_low': None, 'ref_high': 104, 'ref_text': '<104 umol/L', 'direction': 'high', 'advice_hint': '偏高提示肾功能下降，运动需评估'}, {'metric_code': 'BMI', 'name_cn': '体重指数', 'name_en': 'BMI', 'category': '体格', 'unit': 'kg/m2', 'ref_low': 18.5, 'ref_high': 23.9, 'ref_text': '18.5~23.9 kg/m2', 'direction': 'both', 'advice_hint': '偏高提示超重，建议有氧与抗阻联合运动'}, {'metric_code': 'SBP', 'name_cn': '收缩压', 'name_en': 'SBP', 'category': '血压', 'unit': 'mmHg', 'ref_low': None, 'ref_high': 130, 'ref_text': '<130 mmHg', 'direction': 'high', 'advice_hint': '偏高建议规律有氧运动并限盐'}, {'metric_code': 'DBP', 'name_cn': '舒张压', 'name_en': 'DBP', 'category': '血压', 'unit': 'mmHg', 'ref_low': None, 'ref_high': 85, 'ref_text': '<85 mmHg', 'direction': 'high', 'advice_hint': '偏高建议规律有氧运动并限盐'}, {'metric_code': 'TSH', 'name_cn': '促甲状腺激素', 'name_en': 'TSH', 'category': '甲状腺', 'unit': 'mIU/L', 'ref_low': 0.27, 'ref_high': 4.2, 'ref_text': '0.27~4.2 mIU/L', 'direction': 'both', 'advice_hint': '异常提示甲状腺功能异常，运动安排需评估'}]
_HEALTH_NOISE = ['体检报告首页信息：姓名、性别、年龄、体检编号、体检日期、体检机构', '本报告仅反映本次检查结果，如有异常请结合临床由医生综合判断', '检验结果受采样时间、饮食、运动等因素影响，建议定期复查', '参考区间依据本机构检验方法设定，不同机构可能存在差异'] * 3

def guideline_text(row: dict) -> str:
    meta = ' '.join((x for x in [str(row.get('org') or ''), str(row.get('year') or ''), f"证据等级{row.get('evidence_level')}" if row.get('evidence_level') else '', str(row.get('topic') or '')] if x))
    return f"{row.get('title') or ''}（{meta}）{row.get('content') or ''}".strip()

def case_text(row: dict) -> str:
    parts = [f"病历案例 {row.get('case_code') or ''}", f"{row.get('sex') or ''} {row.get('age_band') or ''}".strip(), f"主诉 {row.get('chief_complaint')}" if row.get('chief_complaint') else '', f"检查发现 {row.get('findings')}" if row.get('findings') else '', f"诊断 {row.get('diagnosis')}" if row.get('diagnosis') else '', f"干预 {row.get('intervention')}" if row.get('intervention') else '', f"结局 {row.get('outcome')}" if row.get('outcome') else '']
    return ' | '.join((p for p in parts if p.strip()))

def metric_text(row: dict) -> str:
    ref = row.get('ref_text') or ''
    if not ref:
        lo, hi = (row.get('ref_low'), row.get('ref_high'))
        unit = row.get('unit') or ''
        if lo is not None and hi is not None:
            ref = f'{lo}~{hi} {unit}'.strip()
        elif hi is not None:
            ref = f'<{hi} {unit}'.strip()
        elif lo is not None:
            ref = f'>{lo} {unit}'.strip()
    parts = [f"体检指标 {row.get('name_cn') or ''}", f"编码 {row.get('metric_code') or ''}", f"类别 {row.get('category') or ''}", f"单位 {row.get('unit') or ''}", f'参考区间 {ref}']
    if row.get('advice_hint'):
        parts.append(f"异常提示 {row['advice_hint']}")
    return ' | '.join((p for p in parts if p.split(' ', 1)[-1].strip()))

def _build_self_corpus() -> list[tuple[str, str]]:
    docs: list[tuple[str, str]] = []
    for g in HEALTH_GUIDELINES:
        docs.append((g['id'], guideline_text(g)))
    for c in HEALTH_CASES:
        docs.append((c['id'], case_text(c)))
    for m in HEALTH_METRICS:
        docs.append((f"m_{m['metric_code']}", metric_text(m)))
    for i, t in enumerate(_HEALTH_NOISE):
        docs.append((f'noise_{i}', t))
    return docs
RETRIEVAL_EVAL_SET = [{'query': '血脂异常 有氧运动 干预 循证', 'topics': ['血脂异常'], 'banks': ['case'], 'expected_channels': ['bm25', 'dense']}, {'query': '低密度脂蛋白胆固醇 参考区间', 'topics': ['低密度脂蛋白胆固醇'], 'banks': ['metric_catalog', 'case'], 'expected_channels': ['bm25', 'sql']}, {'query': '血糖控制 运动 胰岛素敏感性', 'topics': ['胰岛素敏感性'], 'banks': ['guideline'], 'expected_channels': ['bm25', 'dense']}, {'query': '高血压 运动 降压 强度', 'topics': ['高血压'], 'banks': ['guideline', 'case'], 'expected_channels': ['bm25', 'dense']}, {'query': '脂肪肝 运动 谷丙转氨酶 干预', 'topics': ['谷丙转氨酶'], 'banks': ['guideline', 'case', 'metric_catalog'], 'expected_channels': ['bm25', 'dense']}, {'query': '尿酸 痛风 运动 饮食', 'topics': ['尿酸'], 'banks': ['guideline', 'case', 'metric_catalog'], 'expected_channels': ['bm25', 'dense']}, {'query': '他汀 运动 肌痛 注意事项', 'topics': ['他汀'], 'banks': ['guideline', 'case'], 'expected_channels': ['bm25', 'dense']}, {'query': '体重管理 运动处方 体脂', 'topics': ['运动处方'], 'banks': ['guideline', 'case'], 'expected_channels': ['bm25', 'dense']}]
_TOKEN_SPLIT = re.compile('[\\s，。、；：|（）()0-9a-zA-Z%]+')
_CJK_RUN = re.compile('[\\u4e00-\\u9fff]+')
_ASCII_RUN = re.compile('[A-Za-z0-9.\\-]+')

def _tokenize(text: str) -> list[str]:
    tokens: list[str] = []
    for part in _TOKEN_SPLIT.split(text):
        part = part.strip()
        if not part:
            continue
        for run in _CJK_RUN.findall(part):
            if len(run) == 1:
                tokens.append(run)
            else:
                tokens.extend((run[i:i + 2] for i in range(len(run) - 1)))
        tokens.extend((w.lower() for w in _ASCII_RUN.findall(part)))
    return tokens

class _BM25:

    def __init__(self, docs: list[str]):
        self.n = len(docs)
        self.df: Counter[str] = Counter()
        self.lens: list[int] = []
        for d in docs:
            self.df.update(set(_tokenize(d)))
            self.lens.append(len(_tokenize(d)))
        self.avg = sum(self.lens) / max(self.n, 1)

    def score(self, q: str, d: str) -> float:
        qts = set(_tokenize(q))
        if not qts:
            return 0.0
        dl = len(_tokenize(d))
        tf = Counter(_tokenize(d))
        s = 0.0
        for t in qts:
            f = tf.get(t, 0)
            if f == 0:
                continue
            idf = math.log((self.n - self.df[t] + 0.5) / (self.df[t] + 0.5) + 1)
            s += idf * (f * 1.5) / (f + 1.5 * (1 - 0.75 + 0.75 * dl / max(self.avg, 1)))
        return s

def _ndcg(ranked: list[str], relevant: set[str], k: int) -> float:
    dcg = sum((1.0 / math.log2(i + 2) for i, d in enumerate(ranked[:k]) if d in relevant))
    idcg = sum((1.0 / math.log2(i + 2) for i in range(min(k, len(relevant)))))
    return dcg / idcg if idcg else 0.0

def compute_metrics(ranked: list[str], relevant: set[str], ks=(1, 3, 5)) -> dict:
    m: dict = {}
    for k in ks:
        top = ranked[:k]
        rel = sum((1 for d in top if d in relevant))
        m[f'recall@{k}'] = rel / max(len(relevant), 1)
        m[f'precision@{k}'] = rel / max(len(top), 1)
        m[f'ndcg@{k}'] = _ndcg(ranked, relevant, k)
    m['mrr'] = next((1.0 / (i + 1) for i, d in enumerate(ranked) if d in relevant), 0.0)
    m['hit@1'] = 1.0 if ranked and ranked[0] in relevant else 0.0
    return m

def _load_db_corpus() -> list[tuple[str, str]]:
    try:
        from app.factory.repository import list_guidelines, list_cases, list_metric_catalog
    except Exception:
        return []
    docs: list[tuple[str, str]] = []
    try:
        for g in list_guidelines():
            docs.append((str(g.id), guideline_text(g.model_dump())))
        for c in list_cases():
            docs.append((str(c.id), case_text(c.model_dump())))
        for m in list_metric_catalog():
            docs.append((f'm_{m.metric_code}', metric_text(m.model_dump())))
    except Exception:
        return []
    return docs

def _health_db_ready() -> bool:
    return bool(_load_db_corpus())

def _search_self(query: str, corpus: list[tuple[str, str]]) -> list[str]:
    bm25 = _BM25([t for _, t in corpus])
    scored = sorted(((bm25.score(query, t), i, d) for i, (d, t) in enumerate(corpus)), key=lambda x: x[0], reverse=True)
    return [d for _, _, d in scored[:10]]

def _relevant_docs(corpus: list[tuple[str, str]], topics: list[str]) -> set[str]:
    return {d for d, t in corpus if any((topic in t for topic in topics))}

def run_retrieval_bench(mode: str='auto') -> dict:
    corpus: list[tuple[str, str]]
    if mode == 'auto':
        mode = 'real' if _health_db_ready() else 'self'
    if mode == 'real':
        corpus = _load_db_corpus()
        if not corpus:
            raise RuntimeError('健康知识库为空（health_guidelines / medical_cases / metric_catalog 无数据）——请先执行 ingest + version publish，再跑 real 模式；或使用 --mode self 跑自包含语料。')
    else:
        corpus = _build_self_corpus()
    per_query = []
    agg: Counter[str] = Counter()
    agg_count = 0
    empty_recall = 0
    channel_cov_ok = 0
    for case in RETRIEVAL_EVAL_SET:
        query = case['query']
        topics = case['topics']
        ranked = _search_self(query, corpus)
        relevant = _relevant_docs(corpus, topics)
        if not ranked:
            empty_recall += 1
        metrics = compute_metrics(ranked, relevant, ks=(1, 3, 5, 10))
        for key, val in metrics.items():
            agg[key] += val
        agg_count += 1
        q_lower = query.lower()
        expected = set(case['expected_channels'])
        numeric = any((k in q_lower for k in ('参考区间', '数值', '区间', '标准')))
        enabled = {'bm25'}
        if numeric:
            enabled.add('sql')
        else:
            enabled.add('dense')
        channel_cov_ok += 1 if expected <= enabled else 0
        per_query.append({'query': query, 'topics': topics, 'banks': case['banks'], 'ranked_top': ranked[:5], 'relevant_count': len(relevant), 'relevant_ids': sorted(relevant)[:10], **{k: round(v, 3) for k, v in metrics.items()}})
    n = max(agg_count, 1)
    aggregated = {k: round(v / n, 4) for k, v in agg.items()}
    aggregated['empty_recall_rate'] = round(empty_recall / n, 3)
    aggregated['planned_channel_coverage'] = round(channel_cov_ok / n, 3)
    return {'benchmark': 'retrieval_quality', 'mode': mode, 'execution_method': 'in-memory BM25 over loaded corpus; channel coverage describes planned channels only', 'corpus_source': 'PG 健康知识库（metric_catalog/health_guidelines/medical_cases）' if mode == 'real' else '自包含健康语料', 'num_docs': len(corpus), 'num_queries': n, 'aggregated': aggregated, 'per_query': per_query, 'timestamp': datetime.now().isoformat(timespec='seconds')}

def main():
    argv = sys.argv[1:]
    mode = 'auto'
    if '--mode' in argv:
        mode = argv[argv.index('--mode') + 1]
    try:
        report = run_retrieval_bench(mode)
    except RuntimeError as e:
        print(f'[ERROR] {e}', file=sys.stderr)
        sys.exit(1)
    if '--json' in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"\n=== 检索质量评测（亮点8）mode={report['mode']} ===\n")
        print(f"语料: {report['num_docs']} 条（{report['corpus_source']}）")
        print(f"查询数: {report['num_queries']}")
        for k, v in report['aggregated'].items():
            print(f'  {k}: {v}')
    os.makedirs(REPORT_DIR, exist_ok=True)
    path = os.path.join(REPORT_DIR, f'retrieval_bench_{datetime.now():%Y%m%d}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f'\n报告已落库: {path}')
if __name__ == '__main__':
    main()
