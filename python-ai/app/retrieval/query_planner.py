import logging
import re
from dataclasses import dataclass, field
from typing import Optional
logger = logging.getLogger(__name__)
_KNOWN_METRICS: dict[str, tuple[str, str]] = {'总胆固醇': ('TC', '血脂'), '甘油三酯': ('TG', '血脂'), '低密度脂蛋白': ('LDL_C', '血脂'), '低密度脂蛋白胆固醇': ('LDL_C', '血脂'), '高密度脂蛋白': ('HDL_C', '血脂'), '高密度脂蛋白胆固醇': ('HDL_C', '血脂'), '空腹血糖': ('GLU', '血糖'), '葡萄糖': ('GLU', '血糖'), '糖化血红蛋白': ('HBA1C', '血糖'), '餐后血糖': ('GLU_2H', '血糖'), '谷丙转氨酶': ('ALT', '肝功能'), '丙氨酸氨基转移酶': ('ALT', '肝功能'), '谷草转氨酶': ('AST', '肝功能'), '天门冬氨酸氨基转移酶': ('AST', '肝功能'), 'γ-谷氨酰转肽酶': ('GGT', '肝功能'), '谷氨酰转肽酶': ('GGT', '肝功能'), '尿酸': ('UA', '代谢'), '肌酐': ('CREA', '肾功能'), '尿素氮': ('BUN', '肾功能'), '体重指数': ('BMI', '体格'), '身高': ('HEIGHT', '体格'), '体重': ('WEIGHT', '体格'), '腰围': ('WAIST', '体格'), '体脂率': ('BODY_FAT', '体格'), '收缩压': ('SBP', '血压'), '舒张压': ('DBP', '血压'), '血红蛋白': ('HGB', '血常规'), '白细胞': ('WBC', '血常规'), '血小板': ('PLT', '血常规'), '促甲状腺激素': ('TSH', '甲状腺')}
_CATEGORY_TOPICS: dict[str, str] = {'血脂': '有氧运动 抗阻训练 血脂 干预 循证', '血糖': '运动 血糖控制 胰岛素敏感性 餐后 循证', '肝功能': '运动 脂肪肝 肝功能 生活方式干预 循证', '代谢': '尿酸 痛风 运动 饮食 生活方式 循证', '肾功能': '肾功能 运动 强度 注意事项 循证', '体格': '体重管理 体脂 运动处方 能量消耗 循证', '血压': '有氧运动 血压 降压 强度 循证', '血常规': '运动 贫血 血红蛋白 注意事项 循证', '甲状腺': '甲状腺 运动 代谢 注意事项 循证'}
_EXERCISE_KEYWORDS = ['运动', '健身', '锻炼', '训练', '跑步', '力量', '有氧', '抗阻', '拉伸', '减脂', '增肌', '体能', '心肺', '运动处方']
_LIFESTYLE_KEYWORDS = ['饮食', '睡眠', '作息', '减重', '减肥', '生活方式', '营养', '戒烟', '限酒']
SOURCE_GUIDELINE = 'guideline'
SOURCE_CASE = 'case'
SOURCE_METRIC = 'metric_catalog'
SOURCE_PAPER = 'paper'

@dataclass
class PlanItem:
    subject: str
    metric_code: str = ''
    category: str = 'unknown'
    channels: list[str] = field(default_factory=list)
    source_types: list[str] = field(default_factory=list)
    query: str = ''
    enriched_query: str = ''
    priority: int = 3

@dataclass
class QueryPlan:
    plans: list[PlanItem] = field(default_factory=list)
    total_queries: int = 0
    channels_used: set[str] = field(default_factory=set)
    source_types_used: set[str] = field(default_factory=set)

class QueryPlanner:

    def __init__(self, user_profile: Optional[dict]=None, max_queries_per_subject: int=3, max_total_queries: int=15):
        self.user_profile = user_profile or {}
        self.max_queries_per_subject = max_queries_per_subject
        self.max_total_queries = max_total_queries
        self.user_conditions = self._extract_fields('condition')
        self.user_medications = self._extract_fields('medication')
        self.user_focus = self._extract_fields('goal')

    def _extract_fields(self, kind: str) -> set[str]:
        items = self.user_profile.get(kind, [])
        if isinstance(items, list):
            return {str(i).lower() for i in items}
        if isinstance(items, str):
            return {items.lower()}
        return set()

    def plan(self, abnormal_metrics: list[dict], query: str='') -> QueryPlan:
        plans: list[PlanItem] = []
        for m in abnormal_metrics:
            name = (m.get('metric_name') or '').strip()
            if not name or name == '_raw_text_':
                continue
            code = (m.get('metric_code') or '').strip()
            category, resolved_code = self._classify(name, code)
            flag = (m.get('flag') or 'unknown').lower()
            channels = self._select_channels(category, flag)
            source_types = self._select_source_types(category, flag)
            q, enriched = self._rewrite_metric(name, resolved_code, category, m)
            priority = self._compute_priority(name, category, flag)
            plans.append(PlanItem(subject=name, metric_code=resolved_code, category=category, channels=channels, source_types=source_types, query=q, enriched_query=enriched, priority=priority))
        if query.strip():
            topics = self._classify_intent(query.strip())
            for cat in topics:
                channels = self._select_channels(cat, 'unknown', query.strip())
                source_types = self._select_source_types(cat, 'unknown')
                q, enriched = self._rewrite_topic(query.strip(), cat)
                plans.append(PlanItem(subject=query.strip(), category=cat, channels=channels, source_types=source_types, query=q, enriched_query=enriched, priority=1))
        plans.extend(self._safety_plans())
        plans = self._apply_budget(plans)
        all_channels: set[str] = set()
        all_sources: set[str] = set()
        for p in plans:
            all_channels.update(p.channels)
            all_sources.update(p.source_types)
        logger.info('[QueryPlanner] 计划生成完成: %d 项主题, 通道=%s, 知识库=%s', len(plans), sorted(all_channels), sorted(all_sources))
        for p in plans:
            logger.debug('  %-20s code=%-10s cat=%-10s ch=%s src=%s pri=%d', p.subject, p.metric_code, p.category, p.channels, p.source_types, p.priority)
        return QueryPlan(plans=plans, total_queries=len(plans), channels_used=all_channels, source_types_used=all_sources)

    def _classify(self, name: str, code: str) -> tuple[str, str]:
        if code:
            for _cn, (known_code, cat) in _KNOWN_METRICS.items():
                if known_code == code:
                    return (cat, code)
            return ('unknown', code)
        for known_name, (known_code, cat) in _KNOWN_METRICS.items():
            if known_name in name or name in known_name:
                return (cat, known_code)
        if len(name) <= 1 or name.isdigit() or re.match('^[A-Za-z0-9\\s\\.\\-]+$', name):
            return ('unknown', '')
        return ('unknown', '')

    def _classify_intent(self, query: str) -> list[str]:
        cats: list[str] = []
        if any((k in query for k in _EXERCISE_KEYWORDS)):
            cats.append('exercise')
        if any((k in query for k in _LIFESTYLE_KEYWORDS)):
            cats.append('lifestyle')
        for known_name, (_code, cat) in _KNOWN_METRICS.items():
            if known_name in query and cat not in cats:
                cats.append(cat)
        if not cats:
            cats.append('exercise')
        return cats[:2]
    _IMAGE_INTENT_KEYWORDS = ('报告', '版式', '图片', '拍照', '上传', '扫描', '同类', '相似')

    def _select_channels(self, category: str, flag: str, query: str='') -> list[str]:
        abnormal = flag in ('high', 'low', 'critical')
        if abnormal:
            channels = ['sql', 'dense', 'bm25']
        elif category in ('exercise', 'lifestyle'):
            channels = ['dense', 'bm25']
        elif category == 'unknown':
            channels = ['dense', 'bm25', 'sql']
        else:
            channels = ['dense', 'sql']
        if query and any((kw in query for kw in self._IMAGE_INTENT_KEYWORDS)):
            channels.append('image')
        return channels

    def _select_source_types(self, category: str, flag: str) -> list[str]:
        abnormal = flag in ('high', 'low', 'critical')
        if category in ('exercise', 'lifestyle'):
            return [SOURCE_GUIDELINE, SOURCE_PAPER, SOURCE_CASE]
        if abnormal:
            return [SOURCE_METRIC, SOURCE_GUIDELINE, SOURCE_PAPER, SOURCE_CASE]
        if category == 'unknown':
            return [SOURCE_GUIDELINE, SOURCE_PAPER, SOURCE_CASE]
        return [SOURCE_METRIC, SOURCE_GUIDELINE, SOURCE_PAPER]

    def _rewrite_metric(self, name: str, code: str, category: str, metric: dict) -> tuple[str, str]:
        code_part = f' {code}' if code else ''
        flag = (metric.get('flag') or '').lower()
        flag_cn = {'high': '偏高', 'low': '偏低', 'critical': '显著异常'}.get(flag, '')
        query = f'{name}{code_part}'.strip()
        topic = _CATEGORY_TOPICS.get(category, '')
        enriched = f'{name}{code_part} {flag_cn} 参考区间 临床意义 运动干预 生活方式 {topic}'.strip()
        name_lower = name.lower()
        if name_lower in self.user_conditions:
            enriched += ' 既往病史 运动禁忌 注意事项'
        elif name_lower in self.user_focus:
            enriched += ' 重点关注 随访建议'
        if self.user_conditions:
            enriched += ' 合并症 运动风险分层'
        return (query, enriched)

    def _rewrite_topic(self, query: str, category: str) -> tuple[str, str]:
        from app.retrieval.synonyms import expand_terms
        if category == 'exercise':
            enriched = f'{query} 有氧运动 抗阻训练 强度 频率 时长 循证建议'
        elif category == 'lifestyle':
            enriched = f'{query} 饮食 睡眠 生活方式干预 循证建议'
        else:
            topic = _CATEGORY_TOPICS.get(category, '')
            enriched = f'{query} {topic}'
        return (query, expand_terms(enriched.strip()))

    def _safety_plans(self) -> list[PlanItem]:
        plans: list[PlanItem] = []
        for cond in sorted(self.user_conditions):
            plans.append(PlanItem(subject=cond, category='exercise', channels=['dense', 'bm25'], source_types=[SOURCE_GUIDELINE, SOURCE_CASE], query=cond, enriched_query=f'{cond} 运动禁忌 运动风险分层 建议 注意事项 循证', priority=1))
        for med in sorted(self.user_medications):
            plans.append(PlanItem(subject=med, category='exercise', channels=['dense', 'bm25'], source_types=[SOURCE_GUIDELINE], query=med, enriched_query=f'{med} 运动 心率反应 注意事项 用药 影响 循证', priority=1))
        return plans

    def _compute_priority(self, name: str, category: str, flag: str) -> int:
        name_lower = name.lower()
        if name_lower in self.user_conditions or name_lower in self.user_medications or name_lower in self.user_focus:
            return 1
        if flag in ('high', 'low', 'critical'):
            return 1
        if category == 'unknown':
            return 2
        return 3

    def _apply_budget(self, plans: list[PlanItem]) -> list[PlanItem]:
        if not plans:
            return plans
        CHANNEL_RANK = {'sql': 1, 'bm25': 2, 'dense': 3, 'image': 4}
        for p in plans:
            if len(p.channels) > self.max_queries_per_subject:
                p.channels.sort(key=lambda ch: CHANNEL_RANK.get(ch, 99))
                p.channels = p.channels[:self.max_queries_per_subject]
        if len(plans) > self.max_total_queries:
            plans.sort(key=lambda p: (p.priority, p.category))
            trimmed = plans[:self.max_total_queries]
            logger.info('[QueryPlanner] 总量裁剪: %d → %d (budget=%d)', len(plans), len(trimmed), self.max_total_queries)
            return trimmed
        return plans

def plan_query_smart(abnormal_metrics: list[dict], user_profile: Optional[dict]=None, query: str='') -> QueryPlan:
    planner = QueryPlanner(user_profile=user_profile)
    return planner.plan(abnormal_metrics, query=query)
