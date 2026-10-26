import logging
logger = logging.getLogger(__name__)
from app.server.research.v1 import research_pb2, research_pb2_grpc
_task_store: dict[str, dict] = {}

def _persist_task_payload(task_id: str, payload: dict) -> None:
    try:
        import os
        import psycopg2
        import json as _json
        db = os.getenv('DATABASE_URL', 'postgresql://lha:lha_dev@localhost:5432/lha')
        conn = psycopg2.connect(db)
        cur = conn.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS task_payloads (\n                 task_id TEXT PRIMARY KEY,\n                 payload JSONB NOT NULL,\n                 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()\n               )')
        cur.execute('INSERT INTO task_payloads (task_id, payload)\n               VALUES (%s, %s)\n               ON CONFLICT (task_id) DO UPDATE SET payload = EXCLUDED.payload,\n                                                  updated_at = now()', (task_id, _json.dumps(payload, ensure_ascii=False)))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        logger.warning('persist task_payload failed: %s', e)

def _load_task_payload(task_id: str) -> dict:
    try:
        import os
        import psycopg2
        import json as _json
        db = os.getenv('DATABASE_URL', 'postgresql://lha:lha_dev@localhost:5432/lha')
        conn = psycopg2.connect(db)
        cur = conn.cursor()
        cur.execute('SELECT payload FROM task_payloads WHERE task_id = %s', (task_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row and row[0]:
            return dict(row[0]) if isinstance(row[0], dict) else _json.loads(row[0])
    except Exception as e:
        logger.debug('load task_payload failed: %s', e)
    return {}

def _format_observation_text(obs: dict) -> str:
    otype = obs.get('type', '')
    if otype == 'ocr':
        return str(obs.get('text', '')).strip()
    if otype == 'vlm_analysis':
        parts = []
        for label, key in (('报告日期', 'report_date'), ('体检机构', 'institution')):
            v = obs.get(key)
            if v and str(v) not in ('', 'unknown'):
                parts.append(f'{label}: {v}')
        parts.append(f"识别指标: {obs.get('metrics', 0)} 项")
        issues = obs.get('quality_issues') or []
        if issues:
            parts.append('质量问题: ' + ', '.join((str(i) for i in issues)))
        return ' | '.join(parts)
    if otype == 'vlm_error':
        return f"[VLM 失败] {obs.get('error', '')}"
    return ''
_REPORT_SECTIONS = ['summary', 'observation', 'facts', 'inferences', 'conflicts', 'unknowns', 'related_to_you', 'metric_reading', 'metric_trend', 'exercise_advice', 'lifestyle_advice', 'followup_advice', 'memory_injection']

def _to_metric_items(metrics: list) -> list:
    items = []
    for m in metrics or []:
        if not isinstance(m, dict):
            continue
        items.append(research_pb2.MetricItem(metric_code=str(m.get('metric_code') or ''), metric_name=str(m.get('metric_name') or ''), category=str(m.get('category') or ''), value_num=float(m.get('value_num') or 0.0), value_text=str(m.get('value_text') or ''), unit=str(m.get('unit') or ''), ref_low=float(m.get('ref_low') or 0.0), ref_high=float(m.get('ref_high') or 0.0), ref_text=str(m.get('ref_text') or ''), flag=str(m.get('flag') or 'unknown'), measured_at=str(m.get('measured_at') or '') if m.get('measured_at') else ''))
    return items

def _to_metric_trend_items(trends: list) -> list:
    items = []
    for t in trends or []:
        if not isinstance(t, dict):
            continue
        points = [research_pb2.MetricPoint(date=str(p.get('date') or ''), value=float(p.get('value') or 0.0), flag=str(p.get('flag') or '')) for p in t.get('points') or [] if isinstance(p, dict)]
        items.append(research_pb2.MetricTrendItem(metric_code=str(t.get('metric_code') or ''), metric_name=str(t.get('metric_name') or ''), unit=str(t.get('unit') or ''), points=points, first_value=float(t.get('first_value') or 0.0), last_value=float(t.get('last_value') or 0.0), delta=float(t.get('delta') or 0.0), direction=str(t.get('direction') or '')))
    return items

def _build_report_deltas(draft: dict, metrics: list, trends: list) -> list:
    sections = draft.get('sections') if isinstance(draft, dict) else {}
    if not isinstance(sections, dict):
        sections = {}
    metric_items = _to_metric_items(metrics)
    trend_items = _to_metric_trend_items(trends)
    deltas = []
    for key in _REPORT_SECTIONS:
        content = sections.get(key, '')
        if not content:
            continue
        delta = research_pb2.ReportDelta(section=key, content=str(content))
        if key == 'metric_reading':
            delta.metrics.extend(metric_items)
        elif key == 'metric_trend':
            delta.metric_trends.extend(trend_items)
        deltas.append(delta)
    if metric_items and (not any((d.metrics for d in deltas))):
        deltas.append(research_pb2.ReportDelta(section='metric_reading', metrics=metric_items))
    if trend_items and (not any((d.metric_trends for d in deltas))):
        deltas.append(research_pb2.ReportDelta(section='metric_trend', metric_trends=trend_items))
    return deltas

class ResearchServicer(research_pb2_grpc.ResearchServiceServicer):

    def SubmitTask(self, request, context):
        logger.info('SubmitTask task_id=%s client_task_id=%s images=%d', request.task_id, request.client_task_id, len(request.images))
        payload = {'tenant_id': request.tenant_id, 'user_id': request.user_id, 'client_task_id': request.client_task_id, 'report_date': request.report_date, 'institution': request.institution, 'images': [{'key': img.key, 'position': img.position, 'presigned_url': img.presigned_url} for img in request.images]}
        _task_store[request.task_id] = payload
        _persist_task_payload(request.task_id, payload)
        return research_pb2.SubmitTaskResponse(task_id=request.task_id, status='intake')

    def StreamTask(self, request, context):
        logger.info('StreamTask task_id=%s trace_id=%s', request.task_id, request.trace_id)
        seq = 0
        emitted_obs_ids: set = set()
        task_data = _task_store.get(request.task_id, {})
        from app.context import ctx as _call_ctx
        _call_ctx.set_context(task_id=request.task_id, user_id=task_data.get('user_id', ''), trace_id=request.trace_id or request.task_id)
        from app.agents.orchestrator import orchestrator
        config = {'configurable': {'thread_id': request.task_id}, 'recursion_limit': 100}
        try:
            snap = orchestrator.get_state(config)
            has_checkpoint = bool(snap and getattr(snap, 'values', None))
        except Exception as e:
            logger.debug('[StreamTask] get_state 失败: %s', e)
            has_checkpoint = False
        if has_checkpoint:
            snap_vals = getattr(snap, 'values', None) or {}
            next_nodes = getattr(snap, 'next', None) or ()
            logger.info('[StreamTask] 命中 checkpoint task=%s status=%s next=%s', request.task_id, snap_vals.get('status'), next_nodes)
            if not task_data:
                task_data = _load_task_payload(request.task_id)
                if task_data:
                    _task_store[request.task_id] = task_data
            interrupt_data = _get_pending_interrupt(orchestrator, config)
            if interrupt_data:
                logger.info('[StreamTask] 恢复 pending interrupt: %s', interrupt_data.get('hital_action', 'unknown'))
                for ev in snap_vals.get('evidence', []):
                    yield research_pb2.TaskEvent(task_id=request.task_id, trace_id=request.trace_id, seq=seq, evidence_found=research_pb2.EvidenceFound(evidence_id=ev.get('evidence_id', ''), source_name=ev.get('source_name', ev.get('doc_id', '')), source_level=ev.get('source_level', 1), quote=ev.get('quote', '')[:200], page=int(ev.get('page') or 0), knowledge_version=ev.get('knowledge_version', ''), source_url=ev.get('source_url', '')))
                    seq += 1
                draft = snap_vals.get('report_draft', {})
                for delta in _build_report_deltas(draft, snap_vals.get('parsed_metrics'), snap_vals.get('metric_trends')):
                    yield research_pb2.TaskEvent(task_id=request.task_id, trace_id=request.trace_id, seq=seq, report_delta=delta)
                    seq += 1
                yield from self._yield_hital_events(request.task_id, request.trace_id, seq, interrupt_data)
                return
            final_status = snap_vals.get('status', '')
            if final_status in ('published', 'refused', 'draft'):
                logger.info('[StreamTask] 已完成状态回放: %s', final_status)
                for ev in snap_vals.get('evidence', []):
                    yield research_pb2.TaskEvent(task_id=request.task_id, trace_id=request.trace_id, seq=seq, evidence_found=research_pb2.EvidenceFound(evidence_id=ev.get('evidence_id', ''), source_name=ev.get('source_name', ev.get('doc_id', '')), source_level=ev.get('source_level', 1), quote=ev.get('quote', '')[:200], page=int(ev.get('page') or 0), knowledge_version=ev.get('knowledge_version', ''), source_url=ev.get('source_url', '')))
                    seq += 1
                draft = snap_vals.get('report_draft', {})
                for delta in _build_report_deltas(draft, snap_vals.get('parsed_metrics'), snap_vals.get('metric_trends')):
                    yield research_pb2.TaskEvent(task_id=request.task_id, trace_id=request.trace_id, seq=seq, report_delta=delta)
                    seq += 1
                rv = snap_vals.get('report_version', '')
                reason = snap_vals.get('refuse_reason', '')
                yield research_pb2.TaskEvent(task_id=request.task_id, trace_id=request.trace_id, seq=seq, result=research_pb2.TaskResult(report_version=rv or final_status, status=final_status, reason=reason, metrics=_to_metric_items(snap_vals.get('parsed_metrics')), metric_trends=_to_metric_trend_items(snap_vals.get('metric_trends'))))
                return
            logger.warning('[StreamTask] checkpoint 存在但无 pending interrupt 且未完成，task=%s', request.task_id)
            yield research_pb2.TaskEvent(task_id=request.task_id, trace_id=request.trace_id, seq=seq, error=research_pb2.Error(error_code='STATE_RECOVERY_FAILED', message='任务状态异常，请取消后重新发起', retryable=False))
            return
        if not task_data:
            task_data = _load_task_payload(request.task_id)
            if task_data:
                _task_store[request.task_id] = task_data
        if not task_data.get('images'):
            logger.warning('[StreamTask] 无任务输入且无 checkpoint，拒绝空跑 task=%s', request.task_id)
            yield research_pb2.TaskEvent(task_id=request.task_id, trace_id=request.trace_id, seq=seq, error=research_pb2.Error(error_code='NO_IMAGE', message='缺少体检报告图片输入，请先提交任务', retryable=False))
            return
        initial_state = {'trace_id': request.trace_id or request.task_id, 'task_id': request.task_id, 'tenant_id': task_data.get('tenant_id', 'dev-tenant'), 'user_id': task_data.get('user_id', 'dev-user'), 'images': task_data.get('images', []), 'report_date': task_data.get('report_date', ''), 'institution': task_data.get('institution', ''), 'image_observations': [], 'parsed_metrics': [], 'abnormal_metrics': [], 'vision_confidence': 0.0, 'user_profile': {}, 'memory_writes_pending': [], 'query_plan': {}, 'retrieval_results': [], 'evidence': [], 'metric_trends': [], 'trend_summary': '', 'validated_claims': [], 'report_draft': {}, 'report_version': '', 'missing_information': [], 'retry_count': 0, 'citation_retry_count': 0, 'quality_failed': False, 'rerun_mode': 'full', 'pending_new_images': [], 'hital_action': '', 'errors': [], 'status': 'intake'}
        prev_status = 'intake'
        last_chunk = initial_state
        try:
            for chunk in orchestrator.stream(initial_state, config, stream_mode='values'):
                last_chunk = chunk
                status = chunk.get('status', prev_status)
                if status != prev_status and status in ('observing', 'retrieving', 'drafting', 'validating', 'awaiting_images', 'awaiting_memory_confirm', 'published'):
                    messages = {'observing': f"体检报告识别中...（{len(chunk.get('image_observations', []))} 条观察）", 'retrieving': f"检索证据中...（{len(chunk.get('parsed_metrics', []))} 项指标 / {len(chunk.get('abnormal_metrics', []))} 项异常）", 'drafting': '健康报告生成中...', 'validating': '引用校验中...', 'awaiting_images': '材料或证据不足，请补充体检报告材料', 'awaiting_memory_confirm': '健康档案候选待确认', 'published': '报告已发布'}
                    msg = messages.get(status, f'阶段: {prev_status} → {status}')
                    yield research_pb2.TaskEvent(task_id=request.task_id, trace_id=request.trace_id, seq=seq, stage_change=research_pb2.StageChange(previous=prev_status, to=status, message=msg))
                    seq += 1
                if status == 'observing' and status != prev_status:
                    for obs in chunk.get('image_observations', []):
                        oid = obs.get('observation_id', '')
                        if oid and oid in emitted_obs_ids:
                            continue
                        if oid:
                            emitted_obs_ids.add(oid)
                        text = _format_observation_text(obs)
                        if not text:
                            continue
                        yield research_pb2.TaskEvent(task_id=request.task_id, trace_id=request.trace_id, seq=seq, observation=research_pb2.Observation(image_key=obs.get('image_key', ''), region=obs.get('region', ''), text=text, confidence=float(obs.get('confidence', 0.0) or 0.0)))
                        seq += 1
                prev_status = status
        except Exception as e:
            if _is_graph_interrupt(e):
                interrupt_data = _extract_interrupt_value(e)
                logger.info('[StreamTask] 图中断(异常), hital_action=%s', interrupt_data.get('hital_action', 'unknown'))
                yield from self._yield_hital_events(request.task_id, request.trace_id, seq, interrupt_data)
                return
            logger.error('[StreamTask] 图执行异常: %s', e, exc_info=True)
            yield research_pb2.TaskEvent(task_id=request.task_id, trace_id=request.trace_id, seq=seq, error=research_pb2.Error(error_code='INTERNAL_ERROR', message=str(e)[:200]))
            return
        for ev in last_chunk.get('evidence', []):
            yield research_pb2.TaskEvent(task_id=request.task_id, trace_id=request.trace_id, seq=seq, evidence_found=research_pb2.EvidenceFound(evidence_id=ev.get('evidence_id', ''), source_name=ev.get('source_name', ev.get('doc_id', '')), source_level=ev.get('source_level', 1), quote=ev.get('quote', '')[:200], page=int(ev.get('page') or 0), knowledge_version=ev.get('knowledge_version', ''), source_url=ev.get('source_url', '')))
            seq += 1
        report = last_chunk.get('report_draft', {})
        for delta in _build_report_deltas(report, last_chunk.get('parsed_metrics'), last_chunk.get('metric_trends')):
            yield research_pb2.TaskEvent(task_id=request.task_id, trace_id=request.trace_id, seq=seq, report_delta=delta)
            seq += 1
        final_status_early = last_chunk.get('status', '')
        is_partial = bool((last_chunk.get('report_draft') or {}).get('partial'))
        if final_status_early in ('published', 'refused') or is_partial:
            try:
                from app.gateway.go_client import build_report_payload_from_state, persist_report
                payload = build_report_payload_from_state(last_chunk)
                persist_report(request.task_id, sections=payload['sections'], citations=payload['citations'], knowledge_version=payload['knowledge_version'], status=final_status_early or 'published', metadata=payload['metadata'], metrics=payload.get('metrics'), metric_trends=payload.get('metric_trends'))
            except Exception as pe:
                logger.error('[StreamTask] 终态落库失败: %s', pe, exc_info=True)
        interrupt_data = _get_pending_interrupt(orchestrator, config)
        if interrupt_data:
            logger.info('[StreamTask] 图中断(checkpoint), hital_action=%s', interrupt_data.get('hital_action', 'unknown'))
            yield from self._yield_hital_events(request.task_id, request.trace_id, seq, interrupt_data)
            return
        pending_memories = last_chunk.get('memory_writes_pending', [])
        for mem in pending_memories:
            yield research_pb2.TaskEvent(task_id=request.task_id, trace_id=request.trace_id, seq=seq, memory_proposal=research_pb2.MemoryProposal(candidate_id=mem.get('candidate_id', ''), kind=mem.get('kind', ''), content=mem.get('content', mem.get('detail', mem.get('label', ''))), source=mem.get('source', 'inferred'), confidence=mem.get('confidence', 0.5)))
            seq += 1
        rv = last_chunk.get('report_version', '')
        final_status = last_chunk.get('status', 'published')
        refuse_reason = last_chunk.get('refuse_reason', '') or ''
        if final_status == 'refused' and (not refuse_reason):
            for err in last_chunk.get('errors') or []:
                if isinstance(err, dict) and err.get('error_code') in ('NO_EVIDENCE', 'CITATION_MISMATCH'):
                    refuse_reason = err.get('message', '')
                    break
        yield research_pb2.TaskEvent(task_id=request.task_id, trace_id=request.trace_id, seq=seq, result=research_pb2.TaskResult(report_version=rv or ('refused' if final_status == 'refused' else 'unknown'), status=final_status, reason=refuse_reason if final_status == 'refused' else '', metrics=_to_metric_items(last_chunk.get('parsed_metrics')), metric_trends=_to_metric_trend_items(last_chunk.get('metric_trends'))))

    def _yield_hital_events(self, task_id, trace_id, seq, interrupt_data):
        action = interrupt_data.get('hital_action', '')
        if action == 'awaiting_images':
            missing = interrupt_data.get('missing_items', ['请补充体检报告材料'])
            yield research_pb2.TaskEvent(task_id=task_id, trace_id=trace_id, seq=seq, missing_info=research_pb2.MissingInfo(items=missing[:3], guidance=interrupt_data.get('guidance', '请根据建议补充体检报告材料')))
            yield research_pb2.TaskEvent(task_id=task_id, trace_id=trace_id, seq=seq + 1, stage_change=research_pb2.StageChange(previous='retrieving', to='awaiting_images', message='材料或证据不足，请补充体检报告材料'))
            yield research_pb2.TaskEvent(task_id=task_id, trace_id=trace_id, seq=seq + 2, result=research_pb2.TaskResult(report_version='', status='awaiting_images', reason='需要用户补充体检报告材料后继续'))
        elif action == 'awaiting_memory_confirm':
            proposals = interrupt_data.get('proposals', [])
            for i, p in enumerate(proposals):
                yield research_pb2.TaskEvent(task_id=task_id, trace_id=trace_id, seq=seq + i, memory_proposal=research_pb2.MemoryProposal(candidate_id=p.get('candidate_id', ''), kind=p.get('kind', ''), content=p.get('content', p.get('detail', '')), source=p.get('source', ''), confidence=p.get('confidence', 0.5)))
            yield research_pb2.TaskEvent(task_id=task_id, trace_id=trace_id, seq=seq + len(proposals), result=research_pb2.TaskResult(report_version='', status='awaiting_memory_confirm', reason='请确认或拒绝以上健康档案候选'))
        elif action == 'awaiting_publish_confirm':
            summary = interrupt_data.get('summary', {})
            yield research_pb2.TaskEvent(task_id=task_id, trace_id=trace_id, seq=seq, result=research_pb2.TaskResult(report_version=interrupt_data.get('report_version', ''), status='awaiting_publish_confirm', reason=f"指标{summary.get('metrics_count', '?')}项（异常{summary.get('abnormal_count', '?')}项）, 证据{summary.get('evidence_count', '?')}条, 请确认发布"))

    def ResumeTask(self, request, context):
        logger.info('ResumeTask task_id=%s action=%s', request.task_id, request.action)
        from app.context import ctx as _call_ctx
        _resume_task_data = _task_store.get(request.task_id) or _load_task_payload(request.task_id)
        _call_ctx.set_context(task_id=request.task_id, user_id=_resume_task_data.get('user_id', ''), trace_id=request.trace_id or request.task_id)
        from app.agents.orchestrator import orchestrator
        from langgraph.types import Command
        config = {'configurable': {'thread_id': request.task_id}, 'recursion_limit': 100}
        resume_value = {}
        if request.action == 'add_images':
            new_images = [{'key': img.key, 'position': img.position, 'presigned_url': img.presigned_url} for img in request.new_images]
            resume_value = {'new_images': new_images, 'action': 'add_images'}
            logger.info('[ResumeTask] 补图 %d 张, 恢复编排', len(new_images))
        elif request.action == 'confirm_memory':
            logger.info('[ResumeTask] confirm_memory 已废弃（记忆自动入库），task=%s', request.task_id)
            return research_pb2.ResumeTaskResponse(task_id=request.task_id, status='memory_auto_saved')
        elif request.action == 'confirm_publish':
            resume_value = {'confirmed': True, 'action': 'confirm_publish'}
            logger.info('[ResumeTask] 用户确认发布, 恢复编排')
        elif request.action == 'cancel_publish':
            resume_value = {'confirmed': False, 'action': 'cancel_publish'}
            logger.info('[ResumeTask] 用户取消发布')
        else:
            logger.warning('[ResumeTask] 未知 action=%s', request.action)
            return research_pb2.ResumeTaskResponse(task_id=request.task_id, status='error_unknown_action')
        try:
            last_chunk = None
            for chunk in orchestrator.stream(Command(resume=resume_value), config, stream_mode='values'):
                last_chunk = chunk
            status = last_chunk.get('status', 'unknown') if last_chunk else 'unknown'
            logger.info('[ResumeTask] 恢复完成, 最终状态=%s', status)
            if isinstance(last_chunk, dict) and status in ('published', 'refused'):
                persist_ok = False
                try:
                    from app.gateway.go_client import build_report_payload_from_state, persist_report
                    payload = build_report_payload_from_state(last_chunk)
                    data = persist_report(request.task_id, sections=payload['sections'], citations=payload['citations'], knowledge_version=payload['knowledge_version'], status=status, metadata=payload['metadata'], metrics=payload.get('metrics'), metric_trends=payload.get('metric_trends'))
                    persist_ok = data is not None
                except Exception as pe:
                    logger.error('[ResumeTask] 报告落库失败: %s', pe, exc_info=True)
                if not persist_ok and status == 'published':
                    try:
                        from app.gateway.go_client import _go_base
                        import httpx
                        headers = {}
                        import os
                        tok = os.getenv('INTERNAL_API_TOKEN', '')
                        if tok:
                            headers['X-Internal-Token'] = tok
                        httpx.post(f'{_go_base()}/internal/tasks/{request.task_id}/status', json={'status': 'persist_failed'}, headers=headers, timeout=5.0)
                    except Exception:
                        logger.error('[ResumeTask] 落库失败补偿标记也失败')
            return research_pb2.ResumeTaskResponse(task_id=request.task_id, status=status)
        except Exception as e:
            if _is_graph_interrupt(e):
                interrupt_data = _extract_interrupt_value(e)
                hital_action = interrupt_data.get('hital_action', 'unknown')
                logger.info('[ResumeTask] 恢复后再次中断: %s', hital_action)
                return research_pb2.ResumeTaskResponse(task_id=request.task_id, status=hital_action)
            logger.error('[ResumeTask] 恢复执行异常: %s', e, exc_info=True)
            return research_pb2.ResumeTaskResponse(task_id=request.task_id, status='error')

    def CancelTask(self, request, context):
        logger.info('CancelTask task_id=%s reason=%s', request.task_id, request.reason)
        return research_pb2.CancelTaskResponse(task_id=request.task_id, status='cancelled')

    def GetTaskCost(self, request, context):
        from app.context import cost as _cost
        logger.info('GetTaskCost task_id=%s', request.task_id)
        try:
            _cost.init_cost_tables()
            agg = _cost.get_task_cost(request.task_id)
        except Exception as e:
            logger.warning('[GetTaskCost] 查询失败: %s', e)
            return research_pb2.GetTaskCostResponse(task_id=request.task_id)
        return research_pb2.GetTaskCostResponse(task_id=request.task_id, total_tokens=int(agg['total_tokens']), call_count=int(agg['call_count']), items=[research_pb2.CostItem(call_type=str(i['call_type']), model=str(i['model']), calls=int(i['calls']), tokens=int(i['tokens']), prompt_tokens=int(i.get('prompt_tokens') or 0), completion_tokens=int(i.get('completion_tokens') or 0), avg_latency_ms=int(i.get('avg_latency_ms') or 0)) for i in agg['items']])

    def Chat(self, request, context):
        logger.info('Chat user_id=%s query=%s history=%d', request.user_id, request.query[:40], len(request.history))
        history = [{'role': str(h.role), 'content': str(h.content)} for h in request.history if str(h.role) in ('user', 'assistant') and str(h.content).strip()]
        try:
            from app.agents.chat_agent import answer_health_question
            result = answer_health_question(query=request.query, user_id=request.user_id, tenant_id='dev-tenant', trace_id=request.trace_id or request.user_id, history=history)
        except Exception as e:
            logger.warning('[Chat] 对话失败: %s', e)
            return research_pb2.ChatResponse(refused=True, answer='抱歉，我暂时无法回答，请稍后再试。')
        evidence_pb = []
        for ev in (result.get('evidence') or [])[:10]:
            evidence_pb.append(research_pb2.EvidenceFound(evidence_id=str(ev.get('evidence_id', '')), source_name=str(ev.get('source_name', '')), source_level=int(ev.get('source_level', 1)), quote=str(ev.get('quote', ''))[:200], knowledge_version=str(ev.get('knowledge_version', '')), source_url=str(ev.get('source_url', ''))))
        return research_pb2.ChatResponse(refused=bool(result.get('refused')), answer=str(result.get('answer', '')), evidence=evidence_pb)

def _get_pending_interrupt(graph, config: dict) -> dict | None:
    try:
        state = graph.get_state(config)
        if state is None:
            return None
        tasks = getattr(state, 'tasks', None) or []
        interrupts_list = getattr(state, 'interrupts', None) or []
        for task in tasks:
            task_interrupts = getattr(task, 'interrupts', None) or []
            for interrupt_item in task_interrupts:
                val = getattr(interrupt_item, 'value', None)
                if isinstance(val, dict) and 'hital_action' in val:
                    return val
        for interrupt_item in interrupts_list:
            val = getattr(interrupt_item, 'value', None)
            if isinstance(val, dict) and 'hital_action' in val:
                return val
        if hasattr(state, 'values') and isinstance(state.values, dict):
            hital = state.values.get('hital_action', '')
            if hital.startswith('awaiting'):
                return {'hital_action': hital, 'state_values': state.values}
    except Exception as e:
        logger.debug('[StreamTask] get_pending_interrupt: %s', e)
    return None

def _is_graph_interrupt(exc: Exception) -> bool:
    exc_name = type(exc).__name__
    if exc_name in ('GraphInterrupt', 'NodeInterrupt', 'Interrupt'):
        return True
    for cls in type(exc).__mro__:
        if cls.__name__ in ('GraphInterrupt', 'NodeInterrupt', 'Interrupt'):
            return True
    return False

def _extract_interrupt_value(exc: Exception) -> dict:
    if hasattr(exc, 'args') and exc.args:
        val = exc.args[0]
        if isinstance(val, dict):
            return val
        if hasattr(val, '__dict__'):
            return {k: v for k, v in val.__dict__.items() if not k.startswith('_')}
    return {'hital_action': 'unknown', 'raw': str(exc)[:500]}

def serve(port: int=50057):
    import grpc as _grpc
    from concurrent import futures as _futures
    from app.server.research.v1 import research_pb2_grpc as _rpc
    from app.observability.runtime import start, ObservedExecutor, ObservationInterceptor
    start()
    server = _grpc.server(ObservedExecutor(max_workers=10), interceptors=[ObservationInterceptor()])
    _rpc.add_ResearchServiceServicer_to_server(ResearchServicer(), server)
    from app.server.memory_server import MemoryServicer
    _rpc.add_MemoryServiceServicer_to_server(MemoryServicer(), server)
    server.add_insecure_port(f'localhost:{port}')
    server.start()
    logger.info('🚀 Python gRPC Server 启动 port=%d（ResearchService + MemoryService）', port)
    return server
