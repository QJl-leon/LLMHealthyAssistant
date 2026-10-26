import logging
import re
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field
from uuid import uuid4
logger = logging.getLogger(__name__)
DECAY_DAYS = 90
DECAY_THRESHOLD = 0.3
DECAY_FACTOR = 0.5
_INJECTION_PATTERNS: tuple[re.Pattern, ...] = tuple((re.compile(p, re.IGNORECASE) for p in ('请记住', '记住[，,]?\\s*用户', '忽略(之前|以上|先前|所有)(的)?(指令|指示|提示|规则)', '从现在开始', '系统提示', 'ignore\\s+(all\\s+)?(previous|prior)\\s+(instructions?|prompts?)', 'remember\\s+(that\\s+)?(the\\s+)?user', 'always\\s+remember', 'from\\s+now\\s+on', 'system\\s+prompt', 'forget\\s+(everything|all|previous)')))
_MAX_CONTENT_CHARS = 100

def is_injection_attempt(content: str) -> bool:
    text = (content or '').strip()
    if not text:
        return False
    if len(text) > _MAX_CONTENT_CHARS:
        return True
    return any((p.search(text) for p in _INJECTION_PATTERNS))

@dataclass
class ProfileEntry:
    id: str = field(default_factory=lambda: str(uuid4()))
    kind: str = ''
    content: str = ''
    metric_codes: list[str] = field(default_factory=list)
    source: str = 'user_stated'
    confidence: float = 1.0
    version: int = 1
    created_at: datetime = field(default_factory=datetime.utcnow)
    superseded_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    pending_confirmation: bool = False

@dataclass
class UserProfileSnapshot:
    basic: list[ProfileEntry] = field(default_factory=list)
    conditions: list[ProfileEntry] = field(default_factory=list)
    medications: list[ProfileEntry] = field(default_factory=list)
    allergies: list[ProfileEntry] = field(default_factory=list)
    goals: list[ProfileEntry] = field(default_factory=list)
    exercises: list[ProfileEntry] = field(default_factory=list)
    episodes: list[dict] = field(default_factory=list)

    def to_injection_items(self) -> list[dict]:
        items: list[dict] = []
        groups = (('basic', self.basic), ('condition', self.conditions), ('medication', self.medications), ('allergy', self.allergies), ('goal', self.goals), ('exercise', self.exercises))
        for kind, entries in groups:
            for e in entries:
                items.append({'layer': 'profile', 'kind': kind, 'content': e.content, 'source': e.source})
        for ep in self.episodes:
            title = ep.get('product_name') or '历史体检分析'
            items.append({'layer': 'episodic', 'kind': 'past_exam', 'content': f"{title}：{(ep.get('summary') or '')[:80]}", 'source': 'episodic', 'task_id': ep.get('task_id', '')})
        return items

    def to_injection_text(self, max_tokens: int=500) -> str:
        parts = []
        budget_chars = int(max_tokens / 1.5)

        def _add(text: str):
            nonlocal budget_chars
            if budget_chars <= 20 or not text:
                return
            chunk = text[:budget_chars]
            parts.append(chunk)
            budget_chars -= len(chunk)
        if self.conditions:
            _add('既往病史: ' + '、'.join((e.content for e in self.conditions)))
        if self.medications:
            _add('长期用药: ' + '、'.join((e.content for e in self.medications)))
        if self.allergies:
            _add('过敏史: ' + '、'.join((e.content for e in self.allergies)))
        if self.goals:
            _add('健康目标: ' + '、'.join((e.content for e in self.goals)))
        if self.exercises:
            _add('运动基础: ' + '、'.join((e.content for e in self.exercises)))
        if self.basic:
            _add('基本信息: ' + '、'.join((e.content for e in self.basic)))
        if self.episodes:
            lines = []
            for ep in self.episodes[:3]:
                name = ep.get('product_name') or '历史体检分析'
                summary = (ep.get('summary') or '').strip()
                lines.append(f'- {name}: {summary[:60]}')
            _add('历史体检分析:\n' + '\n'.join(lines))
        return '\n'.join(parts)

class MemoryCurator:

    def __init__(self, repo=None):
        if repo is None:
            import app.memory.repository as repo
        self._repo = repo

    def get_profile(self, user_id: str) -> UserProfileSnapshot:
        entries = self._repo.get_active_entries(user_id)
        snapshot = UserProfileSnapshot()
        for e in entries:
            if e.kind == 'basic':
                snapshot.basic.append(e)
            elif e.kind == 'condition':
                snapshot.conditions.append(e)
            elif e.kind == 'medication':
                snapshot.medications.append(e)
            elif e.kind == 'allergy':
                snapshot.allergies.append(e)
            elif e.kind == 'goal':
                snapshot.goals.append(e)
            elif e.kind == 'exercise':
                snapshot.exercises.append(e)
        logger.info('MemoryCurator·读: user=%s %d 条有效档案', user_id, len(entries))
        return snapshot

    def build_injection(self, user_id: str, *, report_label: str='', metric_codes: list[str] | None=None, max_tokens: int=500) -> tuple[UserProfileSnapshot, str, list[dict]]:
        try:
            self._repo.init_memory_tables()
        except Exception:
            pass
        snapshot = self.get_profile(user_id)
        try:
            snapshot.episodes = self._repo.search_episodic(user_id, product_name=report_label or '', metric_codes=metric_codes or [], limit=5)
        except Exception as e:
            logger.warning('MemoryCurator·情景检索失败: %s', e)
            snapshot.episodes = []
        text = snapshot.to_injection_text(max_tokens)
        items = snapshot.to_injection_items()
        logger.info('MemoryCurator·注入: chars=%d items=%d episodes=%d budget=%d', len(text), len(items), len(snapshot.episodes), max_tokens)
        return (snapshot, text, items)

    def inject_context(self, user_id: str, max_tokens: int=500) -> str:
        _, text, _ = self.build_injection(user_id, max_tokens=max_tokens)
        return text

    def save_episode(self, **kwargs) -> dict | None:
        try:
            self._repo.init_memory_tables()
            return self._repo.save_episodic(**kwargs)
        except Exception as e:
            logger.error('MemoryCurator·情景写入失败: %s', e)
            return None

    def propose_candidate(self, user_id: str, kind: str, content: str, source: str='inferred', confidence: float=0.5, trigger_task_id: str='', metric_codes: list[str] | None=None) -> Optional[ProfileEntry]:
        if source in ('document', 'webpage', 'report'):
            logger.warning('MemoryCurator·拒绝: 来源=%s 不在白名单中（防投毒）', source)
            raise ValueError(f'来源 {source} 不在白名单中——记忆库不得写入知识库内容')
        if is_injection_attempt(content):
            logger.warning('MemoryCurator·拒绝: 候选内容含注入式指令措辞（防投毒）: %r', content[:80])
            raise ValueError('候选内容含注入式指令措辞——拒绝写入记忆')
        if confidence < 0.3:
            logger.info('MemoryCurator·跳过低置信候选: conf=%.2f', confidence)
            return None
        entry = ProfileEntry(kind=kind, content=content, metric_codes=[str(c) for c in metric_codes or [] if c], source=source, confidence=confidence)
        logger.info('MemoryCurator·候选: user=%s %s=%s conf=%.2f task=%s', user_id, kind, content, confidence, trigger_task_id)
        return entry

    def commit(self, user_id: str, entry: ProfileEntry, confirmed: bool=True) -> bool:
        if not confirmed:
            logger.info('MemoryCurator·用户拒绝: %s=%s', entry.kind, entry.content)
            return False
        if is_injection_attempt(entry.content):
            logger.warning('MemoryCurator·拒绝入库: 内容含注入式指令措辞: %r', entry.content[:80])
            raise ValueError('候选内容含注入式指令措辞——拒绝写入记忆')
        if self._repo.entry_exists(user_id, entry.kind, entry.content):
            logger.info('MemoryCurator·跳过重复: user=%s %s=%s', user_id, entry.kind, entry.content)
            return False
        self._repo.insert_entry(entry, user_id)
        self._log_audit('write', user_id, entry.id, f'{entry.kind}={entry.content}')
        logger.info('MemoryCurator·入库: user=%s %s=%s v=%d', user_id, entry.kind, entry.content, entry.version)
        return True

    def update(self, user_id: str, entry_id: str, new_content: str) -> Optional[ProfileEntry]:
        old_entry = next((e for e in self._repo.get_active_entries(user_id) if e.id == entry_id), None)
        if old_entry is None:
            logger.warning('MemoryCurator·更新失败: entry=%s 未找到', entry_id)
            return None
        new_entry = ProfileEntry(kind=old_entry.kind, content=new_content, metric_codes=list(old_entry.metric_codes or []), source=old_entry.source, confidence=old_entry.confidence, version=old_entry.version + 1)
        self._repo.supersede_and_insert(user_id, entry_id, new_entry)
        self._log_audit('update', user_id, entry_id, f'v{old_entry.version}→v{new_entry.version}: {new_content}')
        logger.info('MemoryCurator·更新: %s v%d→v%d', entry_id, old_entry.version, new_entry.version)
        return new_entry

    def decay_check(self, user_id: str) -> list[ProfileEntry]:
        return self._repo.get_pending_confirmation_entries(user_id)

    def run_decay(self, user_id: Optional[str]=None, decay_days: int=DECAY_DAYS, decay_factor: float=DECAY_FACTOR, decay_threshold: float=DECAY_THRESHOLD) -> dict:
        try:
            self._repo.init_memory_tables()
        except Exception:
            pass
        items = self._repo.decay_inferred_entries(user_id=user_id, decay_days=decay_days, decay_factor=decay_factor, decay_threshold=decay_threshold)
        for it in items:
            self._log_audit('decay', it['user_id'], it['id'], f"{it['kind']}: {it['old_confidence']:.2f}→{it['new_confidence']:.2f}" + ('（转待确认）' if it.get('pending_confirmation') else ''))
        pending = sum((1 for it in items if it.get('pending_confirmation')))
        logger.info('MemoryCurator·衰减: user=%s decayed=%d pending=%d', user_id or 'ALL', len(items), pending)
        return {'decayed': len(items), 'pending': pending, 'items': items}

    def confirm_entry(self, user_id: str, entry_id: str) -> bool:
        ok = self._repo.confirm_entry(user_id, entry_id)
        if ok:
            self._log_audit('confirm', user_id, entry_id, '待确认条目经用户确认复位')
            logger.info('MemoryCurator·确认: user=%s entry=%s', user_id, entry_id)
        else:
            logger.warning('MemoryCurator·确认失败: entry=%s 未找到', entry_id)
        return ok

    def delete(self, user_id: str, entry_id: str):
        ok = self._repo.soft_delete_entry(entry_id, user_id)
        if ok:
            self._log_audit('delete', user_id, entry_id, f'entry_id={entry_id}')
            logger.info('MemoryCurator·删除: user=%s entry=%s', user_id, entry_id)
        else:
            logger.warning('MemoryCurator·删除失败: entry=%s 未找到', entry_id)

    def delete_all(self, user_id: str):
        count = self._repo.soft_delete_all(user_id)
        self._log_audit('delete_all', user_id, '', f'{count} 条')
        logger.info('MemoryCurator·全量删除: user=%s %d 条', user_id, count)

    def _log_audit(self, action: str, user_id: str, target_id: str, detail: str):
        try:
            self._repo.write_audit(user_id, action, target_id, detail)
        except Exception as e:
            logger.error('MemoryCurator·审计日志写入失败: %s', e)

    def get_audit_log(self, user_id: Optional[str]=None) -> list[dict]:
        return self._repo.get_audit_log(user_id=user_id)
