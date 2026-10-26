import logging
from app.memory.curator import MemoryCurator, ProfileEntry, is_injection_attempt
from app.server.research.v1 import research_pb2, research_pb2_grpc
logger = logging.getLogger(__name__)
_VALID_KINDS = {'basic', 'condition', 'medication', 'allergy', 'goal', 'exercise'}

def _to_proto(entry: ProfileEntry) -> research_pb2.MemoryItem:
    return research_pb2.MemoryItem(id=entry.id, kind=entry.kind, content=entry.content, metric_codes=list(entry.metric_codes or []), source=entry.source, confidence=float(entry.confidence), version=int(entry.version), pending_confirmation=bool(entry.pending_confirmation), created_at=entry.created_at.isoformat() if entry.created_at else '')

class MemoryServicer(research_pb2_grpc.MemoryServiceServicer):

    def __init__(self):
        self._curator = MemoryCurator()

    def ListMemory(self, request, context):
        entries = self._curator._repo.get_active_entries(request.user_id)
        return research_pb2.ListMemoryResponse(items=[_to_proto(e) for e in entries])

    def CreateMemory(self, request, context):
        kind = (request.kind or '').strip()
        if kind not in _VALID_KINDS:
            context.abort(3, f'INVALID_KIND: {kind}')
        content = (request.content or '').strip()
        if not content:
            context.abort(3, 'EMPTY_CONTENT')
        source = (request.source or 'user_stated').strip()
        try:
            entry = self._curator.propose_candidate(request.user_id, kind, content, source=source, confidence=1.0 if source == 'user_stated' else 0.5, metric_codes=list(request.metric_codes or []))
        except ValueError as e:
            context.abort(3, str(e))
        if entry is None:
            context.abort(3, 'LOW_CONFIDENCE')
        self._curator.commit(request.user_id, entry, confirmed=True)
        return _to_proto(entry)

    def UpdateMemory(self, request, context):
        new_content = (request.new_content or '').strip()
        if not new_content:
            context.abort(3, 'EMPTY_CONTENT')
        if is_injection_attempt(new_content):
            context.abort(3, '注入式指令措辞——拒绝写入记忆')
        new_entry = self._curator.update(request.user_id, request.entry_id, new_content)
        if new_entry is None:
            context.abort(5, 'MEMORY_NOT_FOUND')
        return _to_proto(new_entry)

    def DeleteMemory(self, request, context):
        before = len(self._curator._repo.get_active_entries(request.user_id))
        self._curator.delete(request.user_id, request.entry_id)
        after = len(self._curator._repo.get_active_entries(request.user_id))
        return research_pb2.DeleteMemoryResponse(ok=after < before, deleted_count=max(0, before - after))

    def DeleteAllMemory(self, request, context):
        before = len(self._curator._repo.get_active_entries(request.user_id))
        self._curator.delete_all(request.user_id)
        return research_pb2.DeleteMemoryResponse(ok=True, deleted_count=before)

    def ConfirmMemory(self, request, context):
        ok = self._curator.confirm_entry(request.user_id, request.entry_id)
        if not ok:
            context.abort(5, 'MEMORY_NOT_FOUND')
        entry = next((e for e in self._curator._repo.get_active_entries(request.user_id) if e.id == request.entry_id), None)
        return _to_proto(entry) if entry else research_pb2.MemoryItem(id=request.entry_id)

    def ListMemoryAudit(self, request, context):
        rows = self._curator.get_audit_log(user_id=request.user_id)
        limit = int(request.limit or 100)
        items = [research_pb2.MemoryAuditItem(id=str(r.get('id', '')), user_id=str(r.get('user_id', '')), action=str(r.get('action', '')), target_id=str(r.get('target_id', '')), detail=str(r.get('detail', '')), created_at=str(r.get('created_at', ''))) for r in rows[:limit]]
        return research_pb2.ListMemoryAuditResponse(items=items)
