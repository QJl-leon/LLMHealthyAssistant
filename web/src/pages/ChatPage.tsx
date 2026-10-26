
import { useState, useCallback, useRef, useEffect } from 'react';
import { createPortal } from 'react-dom';
import ReportView from '../components/ReportView';
import HITLResume from '../components/HITLResume';
import type { HITLAction } from '../components/HITLResume';
import type { EvidenceItem } from '../components/EvidenceCard';
import { isAbnormal, normalizeMetrics, normalizeTrends } from '../components/MetricPanel';
import type { MetricItem, MetricTrendItem } from '../components/MetricPanel';
import { colors, fonts, gradient, radius, shadows } from '../components/styles';
import { apiFetch, eventsURL } from '../api/auth';
import DragUpload from '../components/DragUpload';
import ProtectedImage from '../components/ProtectedImage';
import type { UploadAttachment } from '../components/DragUpload';

interface ReportPayload {
  sections: Record<string, string>;
  evidence: EvidenceItem[];
  metrics: MetricItem[];
  trends: MetricTrendItem[];
  reportDate: string;
  institution: string;
  refused: boolean;
  refuseReason: string;
}

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text?: string;
  attachments?: UploadAttachment[];
  report?: ReportPayload;
  refused?: boolean;
  chatEvidence?: ChatEvidenceItem[];
}

interface ChatEvidenceItem {
  evidenceId?: string;
  sourceName?: string;
  sourceLevel?: number;
  quote?: string;
  sourceUrl?: string;
}

interface TaskEvent {
  taskId?: string;
  seq?: number;
  stageChange?: { previous: string; to: string; message: string };
  evidenceFound?: {
    evidenceId: string;
    sourceName: string;
    sourceLevel: number;
    quote: string;
    knowledgeVersion: string;
    sourceUrl?: string;
    page?: number;
    sourceType?: string;
    title?: string;
    org?: string;
    year?: number;
    evidenceLevel?: string;
    caseCode?: string;
    ageBand?: string;
    sex?: string;
    chiefComplaint?: string;
    findings?: string;
    intervention?: string;
    outcome?: string;
    metricName?: string;
    refText?: string;
  };
  reportDelta?: { section: string; content: string };
  missingInfo?: { items: string[]; guidance: string };
  memoryProposal?: { candidateId: string; kind: string; content: string; source: string; confidence: number };
  metrics?: unknown;
  metricTrends?: unknown;
  result?: { reportVersion: string; status: string; reason: string };
  streamError?: { errorCode: string; message: string };
}

interface StageTiming {
  start: number;
  end?: number;
}

const STAGES = [
  { key: 'intake', label: '接收报告', icon: '📥' },
  { key: 'observing', label: '解析指标', icon: '🔍' },
  { key: 'retrieving', label: '检索证据', icon: '📚' },
  { key: 'drafting', label: '生成建议', icon: '✍️' },
  { key: 'validating', label: '校验引用', icon: '✅' },
  { key: 'published', label: '完成报告', icon: '🎉' },
];

function isPdf(a: UploadAttachment): boolean {
  if (a.type === 'application/pdf') return true;
  return !!a.name?.toLowerCase().endsWith('.pdf');
}

function inferSourceType(sourceName: string, quote: string): string {
  const name = sourceName || '';
  if (/指南|共识|系统评价|meta|队列|RCT|研究|期刊|学会|论文/i.test(name)) return 'guideline';
  if (/案例|病例|case/i.test(name)) return 'case';
  if (/指标|目录|参考区间|参考值/.test(name)) return 'metric_catalog';
  const text = quote || '';
  if (/指南|共识|证据等级/.test(text)) return 'guideline';
  if (/案例|病例/.test(text)) return 'case';
  if (/参考区间|参考值/.test(text)) return 'metric_catalog';
  return '';
}

function parseMetricsSection(content: string): unknown[] | null {
  const raw = (content || '').trim();
  if (!raw.startsWith('[') && !raw.startsWith('{')) return null;
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) return parsed;
    if (parsed && typeof parsed === 'object') {
      const obj = parsed as Record<string, unknown>;
      if (Array.isArray(obj.metrics)) return obj.metrics;
    }
  } catch {
    return null;
  }
  return null;
}

let idSeq = 0;
const nextId = () => `m${Date.now().toString(36)}-${idSeq++}`;

const STORAGE_KEY = 'lha_chat_messages';

interface HistoryTask {
  id: string;
  client_task_id: string;
  status: string;
  image_count: number;
  created_at: string;
}

const TASK_STATUS_LABELS: Record<string, string> = {
  published: '已发布', refused: '已拒答', failed: '失败', persist_failed: '落库失败',
  cancelled: '已取消', intake: '接收中', observing: '解析中', retrieving: '检索中',
  drafting: '草拟中', validating: '校验中', awaiting_images: '待补图',
  awaiting_memory_confirm: '待确认', awaiting_publish_confirm: '待发布',
};

function formatTime(iso: string): string {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}

const SUGGESTION_CHIPS = [
  { icon: '🥗', text: '减脂期三餐应该怎么安排？' },
  { icon: '🩸', text: '尿酸偏高，饮食上要注意什么？' },
  { icon: '🏃', text: '帮我安排一周的运动计划' },
  { icon: '😴', text: '最近睡不好，怎么改善睡眠？' },
];

export default function ChatPage() {
  const [messages, setMessages] = useState<ChatMessage[]>(() => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as ChatMessage[]) : [];
    } catch {
      return [];
    }
  });
  const [showHistory, setShowHistory] = useState(false);
  const [history, setHistory] = useState<HistoryTask[]>([]);
  const [inputText, setInputText] = useState('');
  const [attachments, setAttachments] = useState<UploadAttachment[]>([]);
  const [reportDate, setReportDate] = useState('');
  const [institution, setInstitution] = useState('');
  const [error, setError] = useState('');

  const [busy, setBusy] = useState(false);

  const [chatBusy, setChatBusy] = useState(false);
  const [activeStage, setActiveStage] = useState('');
  const [stageTimings, setStageTimings] = useState<Record<string, StageTiming>>({});
  const [activeSections, setActiveSections] = useState<Record<string, string>>({});
  const [activeEvidence, setActiveEvidence] = useState<EvidenceItem[]>([]);
  const [activeMetrics, setActiveMetrics] = useState<MetricItem[]>([]);
  const [activeTrends, setActiveTrends] = useState<MetricTrendItem[]>([]);
  const [activeHITL, setActiveHITL] = useState<HITLAction | null>(null);
  const [missingItems, setMissingItems] = useState<string[]>([]);
  const [missingGuidance, setMissingGuidance] = useState('');
  const [publishSummary, setPublishSummary] = useState<{
    reportVersion: string; abnormalMetricCount: number; evidenceCount: number; sections: string[];
  } | null>(null);

  const taskIdRef = useRef('');

  const esRef = useRef<EventSource | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const activeSectionsRef = useRef<Record<string, string>>({});
  const activeEvidenceRef = useRef<EvidenceItem[]>([]);
  const activeMetricsRef = useRef<MetricItem[]>([]);
  const activeTrendsRef = useRef<MetricTrendItem[]>([]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' });
  }, [messages, busy, activeStage, activeSections, activeEvidence, activeHITL]);

  useEffect(() => { activeSectionsRef.current = activeSections; }, [activeSections]);
  useEffect(() => { activeEvidenceRef.current = activeEvidence; }, [activeEvidence]);
  useEffect(() => { activeMetricsRef.current = activeMetrics; }, [activeMetrics]);
  useEffect(() => { activeTrendsRef.current = activeTrends; }, [activeTrends]);

  const handleUploaded = useCallback((newAtts: UploadAttachment[]) => {
    setAttachments(prev => [...prev, ...newAtts]);
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(messages));
    } catch {

    }
  }, [messages]);

  const loadHistory = useCallback(async () => {
    try {
      const resp = await apiFetch('/api/v1/tasks');
      const json = await resp.json();
      if (json.code === 0) setHistory(json.data?.items || []);
    } catch {

    }
  }, []);

  const openHistory = () => {
    setShowHistory(true);
    loadHistory();
  };

  const openHistoryTask = async (task: HistoryTask) => {
    if (task.status !== 'published' && task.status !== 'refused') {
      setError(`该任务未生成报告（状态：${task.status}）`);
      setShowHistory(false);
      return;
    }
    try {
      const verResp = await apiFetch(`/api/v1/reports/task/${task.id}/versions`);
      const verJson = await verResp.json();
      const vers = verJson.code === 0 ? (verJson.data?.items || []) : [];
      if (vers.length === 0) {
        setError('该任务尚未生成报告');
        setShowHistory(false);
        return;
      }
      const resp = await apiFetch(`/api/v1/reports/${vers[0].id}`);
      const json = await resp.json();
      if (json.code !== 0) {
        setError(json.error?.message || '加载报告失败');
        setShowHistory(false);
        return;
      }
      const r = json.data;
      const reportMsg: ChatMessage = {
        id: nextId(),
        role: 'assistant',
        report: {
          sections: r.sections || {},
          evidence: (r.citations || []).map((c: { evidence_id?: string; source_name?: string; quote?: string; source_url?: string }) => ({
            evidenceId: c.evidence_id,
            sourceName: c.source_name,
            quote: c.quote,
            sourceUrl: c.source_url,
          })),
          metrics: [],
          trends: [],
          reportDate: '',
          institution: '',
          refused: r.status === 'refused',
          refuseReason: r.status === 'refused' ? '证据不足，拒绝生成报告' : '',
        },
      };
      setMessages(prev => [...prev, { id: nextId(), role: 'user', text: '查看历史咨询' }, reportMsg]);
      setShowHistory(false);
    } catch {
      setError('加载历史报告失败');
      setShowHistory(false);
    }
  };

  const processEvent = useCallback((event: TaskEvent, es?: EventSource) => {
    if (event.stageChange) {
      const prev = event.stageChange.previous;
      const to = event.stageChange.to;
      const now = Date.now();
      setStageTimings(prevTimings => {
        const next = { ...prevTimings };
        if (prev && next[prev] && next[prev].end == null) {
          next[prev] = { ...next[prev], end: now };
        }
        if (to && !next[to]) {
          next[to] = { start: now };
        }
        return next;
      });
      setActiveStage(to);
      if (to === 'awaiting_images') {
        setActiveHITL('awaiting_images');
        es?.close();
      }
    }

    if (event.evidenceFound) {
      const ef = event.evidenceFound;
      const newEvidence: EvidenceItem = {
        evidenceId: ef.evidenceId,
        sourceType: ef.sourceType || inferSourceType(ef.sourceName || '', ef.quote || ''),
        sourceName: ef.sourceName,
        sourceLevel: ef.sourceLevel,
        quote: ef.quote,
        page: ef.page,
        sourceUrl: ef.sourceUrl || '',
        title: ef.title,
        org: ef.org,
        year: ef.year,
        evidenceLevel: ef.evidenceLevel,
        caseCode: ef.caseCode,
        ageBand: ef.ageBand,
        sex: ef.sex,
        chiefComplaint: ef.chiefComplaint,
        findings: ef.findings,
        intervention: ef.intervention,
        outcome: ef.outcome,
        metricName: ef.metricName,
        refText: ef.refText,
        knowledgeVersion: ef.knowledgeVersion,
      };
      setActiveEvidence(prev => [...prev, newEvidence]);

      activeEvidenceRef.current = [...activeEvidenceRef.current, newEvidence];
    }

    if (event.metrics) {
      const list = normalizeMetrics(event.metrics);
      if (list.length > 0) { setActiveMetrics(list); activeMetricsRef.current = list; }
    }
    if (event.metricTrends) {
      const list = normalizeTrends(event.metricTrends);
      if (list.length > 0) { setActiveTrends(list); activeTrendsRef.current = list; }
    }

    if (event.reportDelta) {
      const section = event.reportDelta.section;
      const content = event.reportDelta.content;
      setActiveSections(prev => ({ ...prev, [section]: content }));

      activeSectionsRef.current = { ...activeSectionsRef.current, [section]: content };
      if (section === 'metrics' || section === 'metric_overview' || section === 'metric_interpretation') {
        const parsed = parseMetricsSection(content);
        if (parsed) setActiveMetrics(normalizeMetrics(parsed));
      }
    }

    if (event.missingInfo) {
      setActiveHITL('awaiting_images');
      setMissingItems(event.missingInfo.items || []);
      setMissingGuidance(event.missingInfo.guidance || '');
      setActiveStage('awaiting_images');
      es?.close();
    }

    if (event.result) {
      const status = event.result.status;
      if (status === 'awaiting_images') {
        setActiveHITL('awaiting_images');
        es?.close();
      } else if (status === 'awaiting_publish_confirm') {
        setActiveHITL('awaiting_publish_confirm');
        setPublishSummary({
          reportVersion: event.result.reportVersion,
          abnormalMetricCount: 0,
          evidenceCount: 0,
          sections: [],
        });
        es?.close();
      } else if (status === 'published') {
        finalizeReport(false, '');
        es?.close();
      } else if (status === 'refused') {
        finalizeReport(true, event.result.reason || '证据不足，拒绝生成报告');
        es?.close();
      }
    }

    if (event.streamError) {
      setError(event.streamError.message);
      setBusy(false);

      setActiveStage('');
      es?.close();
    }
  }, []);

  const finalizeReport = useCallback((refused: boolean, reason: string) => {
    const payload: ReportPayload = {
      sections: activeSectionsRef.current,
      evidence: activeEvidenceRef.current,
      metrics: activeMetricsRef.current,
      trends: activeTrendsRef.current,
      reportDate,
      institution,
      refused,
      refuseReason: reason,
    };
    setMessages(prev => [...prev, { id: nextId(), role: 'assistant', report: payload }]);

    setBusy(false);
    setActiveStage('');
    setActiveSections({});
    setActiveEvidence([]);
    setActiveMetrics([]);
    setActiveTrends([]);
    setActiveHITL(null);
    setPublishSummary(null);
  }, [reportDate, institution]);

  const send = useCallback(async (overrideText?: string) => {
    if (busy || chatBusy) return;
    const text = (overrideText ?? inputText).trim();
    if (attachments.length === 0 && !text) {
      setError('请输入问题，或上传体检报告（图片/PDF）');
      return;
    }
    setError('');

    if (attachments.length === 0) {

      const history = messages
        .filter(m => (m.role === 'user' || m.role === 'assistant') && m.text)
        .slice(-8)
        .map(m => ({ role: m.role, content: m.text as string }));
      setMessages(prev => [...prev, { id: nextId(), role: 'user', text }]);
      setInputText('');
      setChatBusy(true);
      try {
        const resp = await apiFetch('/api/v1/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: text, history }),
        });
        const json = await resp.json();
        if (json.code === 0) {
          const d = json.data || {};
          const chatEvidence: ChatEvidenceItem[] = (d.evidence || []).map((e: {
            evidence_id?: string; source_name?: string; source_level?: number;
            quote?: string; source_url?: string;
          }) => ({
            evidenceId: e.evidence_id,
            sourceName: e.source_name,
            sourceLevel: e.source_level,
            quote: e.quote,
            sourceUrl: e.source_url,
          }));
          setMessages(prev => [...prev, {
            id: nextId(),
            role: 'assistant',
            text: d.answer || '抱歉，我暂时无法回答，请稍后再试。',
            refused: !!d.refused,
            chatEvidence: chatEvidence.filter(e => e.quote || e.sourceName),
          }]);
        } else {
          setMessages(prev => [...prev, { id: nextId(), role: 'assistant', text: '抱歉，我暂时无法回答，请稍后再试。' }]);
        }
      } catch {
        setMessages(prev => [...prev, { id: nextId(), role: 'assistant', text: '抱歉，我暂时无法回答，请稍后再试。' }]);
      } finally {
        setChatBusy(false);
      }
      return;
    }

    const userMsg: ChatMessage = {
      id: nextId(),
      role: 'user',
      text: inputText.trim() || '请帮我解读这份体检报告',
      attachments: [...attachments],
    };
    setMessages(prev => [...prev, userMsg]);
    setInputText('');
    setAttachments([]);

    setBusy(true);
    setActiveStage('intake');
    setStageTimings({ intake: { start: Date.now() } });
    setActiveSections({});
    setActiveEvidence([]);
    setActiveMetrics([]);
    setActiveTrends([]);
    setActiveHITL(null);
    setPublishSummary(null);

    const clientTaskId = `task-${Date.now().toString(36)}`;
    try {
      const resp = await apiFetch('/api/v1/tasks', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          client_task_id: clientTaskId,
          report_date: reportDate,
          institution,
          images: userMsg.attachments!.map(a => ({ key: a.key, position: a.position })),
        }),
      });
      const json = await resp.json();
      if (json.code !== 0) {
        setError(json.error?.message || '创建任务失败');
        setBusy(false);
        setActiveStage('');
        return;
      }
      const tid = json.data.task_id;
      taskIdRef.current = tid;

      const es = new EventSource(eventsURL(tid));
      esRef.current = es;
      es.onmessage = (e) => {
        try {
          processEvent(JSON.parse(e.data), es);
        } catch {

        }
      };
      es.onerror = () => { es.close(); esRef.current = null; };
    } catch {
      setError('网络错误，请重试');
      setBusy(false);
      setActiveStage('');
    }
  }, [busy, chatBusy, attachments, inputText, messages, reportDate, institution, processEvent]);

  const resetConversation = useCallback(() => {
    const running = busy || chatBusy || !!activeHITL;
    if (running && !window.confirm('当前有任务进行中，重置将中断页面上的进度展示（后端任务继续执行）。确定重置吗？')) {
      return;
    }

    esRef.current?.close();
    esRef.current = null;
    setMessages([]);
    try { localStorage.removeItem(STORAGE_KEY); } catch {  }
    setInputText('');
    setAttachments([]);
    setReportDate('');
    setInstitution('');
    setError('');

    setBusy(false);
    setChatBusy(false);
    setActiveStage('');
    setStageTimings({});
    setActiveSections({});
    setActiveEvidence([]);
    setActiveMetrics([]);
    setActiveTrends([]);
    activeSectionsRef.current = {};
    activeEvidenceRef.current = [];
    activeMetricsRef.current = [];
    activeTrendsRef.current = [];
    setActiveHITL(null);
    setMissingItems([]);
    setMissingGuidance('');
    setPublishSummary(null);
    taskIdRef.current = '';
  }, [busy, chatBusy, activeHITL]);

  const handleResume = useCallback(async (resumeData: {
    action: string;
    new_image_keys?: string[];
    new_images?: { key: string; position: string }[];
    decisions?: { candidate_id: string; accepted: boolean }[];
  }) => {
    const tid = taskIdRef.current;
    if (!tid) return;
    setError('');
    try {
      const resp = await apiFetch(`/api/v1/tasks/${tid}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(resumeData),
      });
      const json = await resp.json();
      if (json.code !== 0) {
        setError(json.error?.message || '恢复失败');
        return;
      }
      const newStatus = json.data?.status || '';
      setActiveHITL(null);
      setPublishSummary(null);
      setMissingItems([]);
      setMissingGuidance('');

      if (newStatus === 'published' || newStatus === 'draft' || newStatus === 'refused') {
        setBusy(false);
      } else {
        setBusy(true);
        const es = new EventSource(eventsURL(tid));
        esRef.current = es;
        es.onmessage = (e) => {
          try { processEvent(JSON.parse(e.data), es); } catch {  }
        };
        es.onerror = () => { es.close(); esRef.current = null; };
      }
    } catch {
      setError('恢复请求失败');
    }
  }, [processEvent]);

  const showWelcome = messages.length === 0 && !busy;

  return (
    <div style={{
      flex: 1, display: 'flex', flexDirection: 'column',
      maxWidth: 820, width: '100%', margin: '0 auto',
      height: 'calc(100vh - 60px)', position: 'relative',
    }}>
      {}
      {showHistory && (
        <div style={{
          position: 'absolute', top: 0, left: 0, bottom: 0, width: 280,
          background: '#fff', borderRight: `1px solid ${colors.border}`,
          zIndex: 40, display: 'flex', flexDirection: 'column',
          boxShadow: '4px 0 16px rgba(15,23,42,0.10)',
        }}>
          <div style={{
            padding: '12px 16px', display: 'flex', alignItems: 'center',
            justifyContent: 'space-between', borderBottom: `1px solid ${colors.border}`,
          }}>
            <span style={{ fontWeight: 700, fontSize: 14 }}>历史对话</span>
            <button onClick={() => setShowHistory(false)} style={{
              border: 'none', background: 'transparent', cursor: 'pointer',
              fontSize: 16, color: colors.textSecondary, lineHeight: 1,
            }}>✕</button>
          </div>
          <div style={{ flex: 1, overflowY: 'auto', padding: 8 }}>
            {history.length === 0 ? (
              <div style={{ padding: 24, textAlign: 'center', color: '#94A3B8', fontSize: 13 }}>
                暂无历史对话
              </div>
            ) : (
              history.map(t => {
                const has = t.status === 'published' || t.status === 'refused';
                return (
                  <button key={t.id} onClick={() => openHistoryTask(t)} style={{
                    width: '100%', textAlign: 'left', border: 'none', cursor: 'pointer',
                    background: 'transparent', borderRadius: 8, padding: '10px 12px',
                    display: 'block', fontFamily: fonts.sans,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                      <span style={{
                        fontSize: 11, fontWeight: 600, padding: '1px 6px', borderRadius: 4,
                        background: has ? '#ECFDF5' : '#F1F5F9',
                        color: has ? '#059669' : '#64748B',
                      }}>
                        {TASK_STATUS_LABELS[t.status] || t.status}
                      </span>
                      <span style={{ fontSize: 11, color: '#94A3B8' }}>{formatTime(t.created_at)}</span>
                    </div>
                    <div style={{ fontSize: 11, color: '#94A3B8', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {t.client_task_id || t.id.slice(0, 8)}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>
      )}

      {}
      <div style={{ display: 'flex', alignItems: 'center', padding: '8px 20px 0' }}>
        <button onClick={openHistory} style={{
          border: `1px solid ${colors.border}`, background: '#fff', cursor: 'pointer',
          borderRadius: 8, padding: '5px 12px', fontSize: 12, color: colors.textSecondary,
        }}>
          🕘 历史对话
        </button>
        <div style={{ flex: 1 }} />
        {(messages.length > 0 || busy || chatBusy || activeHITL) && (
          <button
            onClick={resetConversation}
            title="清除当前聊天记录并新建对话"
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              border: `1px solid ${colors.border}`, background: colors.bgCard,
              cursor: 'pointer', borderRadius: 8, padding: '5px 12px',
              fontSize: 12, fontWeight: 600, color: colors.primary,
            }}
          >
            ✨ 重置对话
          </button>
        )}
      </div>

      {}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 20px 16px' }}>
        {showWelcome ? (
          <Welcome
            onUploaded={handleUploaded}
            onAsk={(text) => { send(text); }}
            disabled={busy || chatBusy}
          />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {messages.map(m => <MessageBubble key={m.id} msg={m} />)}

            {}
            {chatBusy && (
              <div style={{ display: 'flex', gap: 10 }}>
                <Avatar />
                <TypingBubble />
              </div>
            )}

            {}
            {busy && (
              <div style={{ display: 'flex', gap: 10 }}>
                <Avatar />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <StageProgress stage={activeStage} timings={stageTimings} />
                </div>
              </div>
            )}

            {}
            {activeHITL === 'awaiting_images' && (
              <div style={{ display: 'flex', gap: 10 }}>
                <Avatar />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <HITLResume
                    action="awaiting_images"
                    taskId={taskIdRef.current}
                    missingInfo={{
                      items: missingItems.length > 0 ? missingItems : ['请补充体检报告首页或化验单'],
                      guidance: missingGuidance || '请根据建议补充体检报告图片',
                    }}
                    onResume={handleResume}
                  />
                </div>
              </div>
            )}
            {activeHITL === 'awaiting_publish_confirm' && (
              <div style={{ display: 'flex', gap: 10 }}>
                <Avatar />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <HITLResume
                    action="awaiting_publish_confirm"
                    taskId={taskIdRef.current}
                    publishSummary={publishSummary || {
                      reportVersion: '',
                      abnormalMetricCount: activeMetrics.filter(isAbnormal).length,
                      evidenceCount: activeEvidence.length,
                      sections: Object.keys(activeSections),
                    }}
                    onResume={handleResume}
                  />
                </div>
              </div>
            )}

            <div ref={scrollRef} />
          </div>
        )}
      </div>

      {}
      {error && (
        <div style={{
          maxWidth: 820, width: '100%', margin: '0 auto', padding: '0 20px 8px',
        }}>
          <div style={{
            padding: '10px 14px', borderRadius: 10, fontSize: 13,
            background: '#FEF2F2', color: colors.danger, border: '1px solid #FEE2E2',
          }}>
            ⚠️ {error}
          </div>
        </div>
      )}

      {}
      <div style={{
        padding: '8px 20px 20px',
        borderTop: '1px solid transparent',
      }}>
        <div style={{
          maxWidth: 780, margin: '0 auto',
          background: colors.bgCard, borderRadius: 16,
          border: `1px solid ${colors.border}`,
          boxShadow: '0 8px 24px rgba(15,23,42,0.06)',
          padding: 12,
        }}>
          {}
          {attachments.length > 0 && (
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 10 }}>
              {attachments.map((a, i) => (
                <div key={i} style={{
                  position: 'relative', width: 64, height: 64, borderRadius: 8,
                  overflow: 'hidden', border: `1px solid ${colors.border}`,
                }}>
                  {a.url && !isPdf(a) ? (
                    <ProtectedImage imageKey={a.key} style={{ width: 64, height: 64, objectFit: 'cover', display: 'block' }} />
                  ) : (
                    <div style={{
                      width: 64, height: 64, display: 'flex', alignItems: 'center',
                      justifyContent: 'center', fontSize: 22, background: colors.bg,
                    }}>📄</div>
                  )}
                  <button
                    onClick={() => setAttachments(prev => prev.filter((_, j) => j !== i))}
                    style={{
                      position: 'absolute', top: 2, right: 2, width: 18, height: 18,
                      borderRadius: '50%', background: 'rgba(0,0,0,0.55)', color: '#fff',
                      border: 'none', fontSize: 12, cursor: 'pointer', lineHeight: 1,
                    }}
                  >×</button>
                </div>
              ))}
            </div>
          )}

          {}
          <textarea
            value={inputText}
            onChange={e => setInputText(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                send();
              }
            }}
            placeholder="描述你的情况，或直接上传体检报告让我解读…"
            rows={inputText.includes('\n') || inputText.length > 40 ? 2 : 1}
            style={{
              width: '100%', border: 'none', outline: 'none', resize: 'none',
              fontSize: 15, lineHeight: 1.6, color: colors.text,
              fontFamily: fonts.sans, background: 'transparent', padding: '2px 4px',
            }}
          />

          {}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 }}>
            <DragUpload variant="compact" onUploaded={handleUploaded} disabled={busy || chatBusy} />

            {}
            {attachments.length > 0 && (
              <>
                <label style={{
                  display: 'flex', alignItems: 'center', gap: 4, fontSize: 12,
                  color: colors.textSecondary,
                }}>
                  <span>📅</span>
                  <input
                    type="date"
                    value={reportDate}
                    onChange={e => setReportDate(e.target.value)}
                    style={{
                      width: 118, padding: '4px 6px', fontSize: 12,
                      border: `1px solid ${colors.border}`, borderRadius: 6,
                      color: colors.text, fontFamily: fonts.sans, background: colors.bg,
                    }}
                  />
                </label>

                <input
                  value={institution}
                  onChange={e => setInstitution(e.target.value)}
                  placeholder="体检机构（可选）"
                  style={{
                    flex: 1, minWidth: 0, padding: '6px 10px', fontSize: 12,
                    border: `1px solid ${colors.border}`, borderRadius: 6,
                    color: colors.text, fontFamily: fonts.sans, background: colors.bg,
                  }}
                />
              </>
            )}
            {attachments.length === 0 && <div style={{ flex: 1 }} />}

            <button
              onClick={() => send()}
              disabled={busy || chatBusy || (attachments.length === 0 && !inputText.trim())}
              style={{
                padding: '8px 20px', fontSize: 14, fontWeight: 700, borderRadius: 10,
                border: 'none',
                cursor: busy || chatBusy || (attachments.length === 0 && !inputText.trim())
                  ? 'not-allowed' : 'pointer',
                background: busy || chatBusy || (attachments.length === 0 && !inputText.trim())
                  ? '#DCE9E7'
                  : gradient.primary,
                color: busy || chatBusy || (attachments.length === 0 && !inputText.trim()) ? '#94A3B8' : '#fff',
                boxShadow: busy || chatBusy || (attachments.length === 0 && !inputText.trim())
                  ? 'none' : '0 2px 10px rgba(14,159,143,0.30)',
                whiteSpace: 'nowrap',
              }}
            >
              {busy ? '分析中…' : chatBusy ? '回答中…' : '发送'}
            </button>
          </div>
        </div>

        <div style={{
          maxWidth: 780, margin: '8px auto 0', textAlign: 'center',
          fontSize: 11, color: '#94A3B8',
        }}>
          上传体检报告后即可解读指标，每条建议均附可核验的证据来源
        </div>
      </div>
    </div>
  );
}

function Avatar() {
  return (
    <span style={{
      width: 34, height: 34, borderRadius: 12, flexShrink: 0,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: 16, background: gradient.primary,
      boxShadow: '0 2px 6px rgba(14,159,143,0.28)',
    }}>
      🩺
    </span>
  );
}

function TypingBubble() {
  return (
    <div style={{
      display: 'inline-flex', alignItems: 'center', gap: 5,
      padding: '14px 18px', borderRadius: radius.bubble, borderTopLeftRadius: 4,
      background: colors.bgCard, border: `1px solid ${colors.border}`,
      boxShadow: shadows.bubble,
    }}>
      <style>{`
        @keyframes lhaTypingDot {
          0%, 60%, 100% { transform: translateY(0); opacity: 0.35; }
          30% { transform: translateY(-4px); opacity: 1; }
        }
      `}</style>
      {[0, 1, 2].map(i => (
        <span key={i} style={{
          width: 6, height: 6, borderRadius: '50%', background: colors.primary,
          display: 'inline-block',
          animation: 'lhaTypingDot 1.2s ease-in-out infinite',
          animationDelay: `${i * 0.18}s`,
        }} />
      ))}
    </div>
  );
}

function Welcome({
  onUploaded, onAsk, disabled,
}: {
  onUploaded: (a: UploadAttachment[]) => void;
  onAsk: (text: string) => void;
  disabled: boolean;
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, paddingTop: 8 }}>
      {}
      <div style={{ display: 'flex', gap: 10 }}>
        <Avatar />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            background: colors.assistantBubble, borderRadius: `${radius.bubble}px`,
            borderTopLeftRadius: 4, padding: '14px 16px',
            border: `1px solid ${colors.border}`, boxShadow: shadows.bubble,
            fontSize: 14, lineHeight: 1.75,
          }}>
            <div style={{ fontWeight: 700, marginBottom: 6 }}>
              你好，我是你的健康顾问 🩺
            </div>
            <div style={{ color: colors.textSecondary }}>
              上传体检报告，我会帮你解读各项指标，并给出可循证的运动与生活方式建议。
              你也可以直接问我健康、运动、饮食相关的问题，比如：
            </div>
          </div>

          {}
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 10 }}>
            {SUGGESTION_CHIPS.map(chip => (
              <button
                key={chip.text}
                onClick={() => onAsk(chip.text)}
                disabled={disabled}
                style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6,
                  padding: '8px 14px', fontSize: 13,
                  borderRadius: radius.pill, cursor: disabled ? 'not-allowed' : 'pointer',
                  background: colors.bgCard, color: colors.text,
                  border: `1px solid ${colors.border}`,
                  opacity: disabled ? 0.55 : 1,
                  fontFamily: fonts.sans, transition: 'all 0.15s',
                }}
              >
                <span>{chip.icon}</span>
                <span>{chip.text}</span>
              </button>
            ))}
          </div>
        </div>
      </div>

      {}
      <div style={{ display: 'flex', gap: 10 }}>
        <Avatar />
        <div style={{ flex: 1, minWidth: 0 }}>
          <DragUpload variant="compact" onUploaded={onUploaded} disabled={disabled} />
        </div>
      </div>
    </div>
  );
}

function formatDuration(ms: number): string {
  if (ms < 0) ms = 0;
  const sec = ms / 1000;
  if (sec < 60) return `${sec.toFixed(1)}s`;
  const min = Math.floor(sec / 60);
  const remain = Math.round(sec % 60);
  return `${min}m ${remain}s`;
}

function StageProgress({ stage, timings }: { stage: string; timings: Record<string, StageTiming> }) {

  const [, setTick] = useState(0);
  useEffect(() => {
    const timer = setInterval(() => setTick(t => t + 1), 1000);
    return () => clearInterval(timer);
  }, []);

  const now = Date.now();

  return (
    <div style={{
      padding: '16px 20px', borderRadius: 14, borderTopLeftRadius: 4,
      background: colors.bgCard, border: `1px solid ${colors.border}`,
      display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      <div style={{ fontSize: 13, fontWeight: 700, color: colors.text }}>
        🤖 正在为你生成健康报告
      </div>
      {STAGES.map((s) => {
        const timing = timings[s.key];
        const isActive = stage === s.key;
        const isDone = timing?.end != null;
        let elapsed = '';
        if (timing) {
          if (timing.end != null) {
            elapsed = formatDuration(timing.end - timing.start);
          } else if (isActive) {
            elapsed = formatDuration(now - timing.start);
          }
        }

        return (
          <div key={s.key} style={{
            display: 'flex', alignItems: 'center', gap: 10,
            opacity: isDone || isActive ? 1 : 0.45,
            transition: 'opacity 0.2s',
          }}>
            <span style={{ width: 22, fontSize: 15, textAlign: 'center', flexShrink: 0 }}>
              {isDone ? '✅' : isActive ? '⏳' : '○'}
            </span>
            <span style={{
              flex: 1, fontSize: 13,
              color: isActive ? colors.primary : isDone ? colors.text : colors.textSecondary,
              fontWeight: isActive || isDone ? 600 : 400,
            }}>
              {s.icon} {s.label}
            </span>
            {elapsed && (
              <span style={{
                fontSize: 12, color: colors.textSecondary, flexShrink: 0,
                fontVariantNumeric: 'tabular-nums',
              }}>
                {isActive ? `${elapsed}` : elapsed}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

function MessageBubble({ msg }: { msg: ChatMessage }) {
  if (msg.role === 'user') {
    return (
      <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 10 }}>
        <div style={{ maxWidth: '78%' }}>
          <div style={{
            padding: '12px 16px', borderRadius: radius.bubble, borderTopRightRadius: 4,
            background: gradient.primary,
            color: '#fff', fontSize: 14, lineHeight: 1.6,
            boxShadow: '0 2px 8px rgba(14,159,143,0.24)',
            whiteSpace: 'pre-wrap',
          }}>
            {msg.text}
          </div>
          {msg.attachments && msg.attachments.length > 0 && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6, justifyContent: 'flex-end' }}>
              {msg.attachments.map((a, i) => (
                <div key={i} style={{
                  width: 56, height: 56, borderRadius: 8, overflow: 'hidden',
                  border: '1px solid rgba(0,0,0,0.06)',
                }}>
                  {a.url && !isPdf(a) ? (
                    <ProtectedImage imageKey={a.key} style={{ width: 56, height: 56, objectFit: 'cover', display: 'block' }} />
                  ) : (
                    <div style={{
                      width: 56, height: 56, display: 'flex', alignItems: 'center',
                      justifyContent: 'center', fontSize: 20, background: colors.bg,
                    }}>📄</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  if (msg.report) {
    return (
      <div style={{ display: 'flex', gap: 10 }}>
        <Avatar />
        <div style={{ flex: 1, minWidth: 0 }}>
          <ReportView
            sections={msg.report.sections}
            evidence={msg.report.evidence}
            metrics={msg.report.metrics}
            trends={msg.report.trends}
            reportMeta={{ reportDate: msg.report.reportDate, institution: msg.report.institution }}
            refused={msg.report.refused}
            refuseReason={msg.report.refuseReason}
          />
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', gap: 10 }}>
      <Avatar />
      <div style={{ flex: 1, minWidth: 0, maxWidth: '86%' }}>
        <div style={{
          padding: '12px 16px', borderRadius: radius.bubble, borderTopLeftRadius: 4,
          background: msg.refused ? colors.warningBg : colors.bgCard,
          border: `1px solid ${msg.refused ? '#FDE68A' : colors.border}`,
          fontSize: 14, lineHeight: 1.7, color: msg.refused ? colors.warning : colors.text,
          whiteSpace: 'pre-wrap',
        }}>
          {msg.refused && <span style={{ marginRight: 6 }}>🚫</span>}
          <CitedText text={msg.text || ''} evidence={msg.chatEvidence} />
        </div>
      </div>
    </div>
  );
}

const CITATION_POPUP_WIDTH = 340;

function CitationChip({ index, evidence }: { index: number; evidence: ChatEvidenceItem }) {
  const [open, setOpen] = useState(false);
  const [pinned, setPinned] = useState(false);
  const [pos, setPos] = useState<{ top: number; left: number; above: boolean } | null>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  const measure = () => {
    const r = btnRef.current?.getBoundingClientRect();
    if (!r) return;
    const above = r.top > 320;
    setPos({
      top: above ? r.top : r.bottom,
      left: Math.max(12, Math.min(r.left, window.innerWidth - CITATION_POPUP_WIDTH - 12)),
      above,
    });
  };

  const visible = open || pinned;

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onMouseEnter={() => { measure(); setOpen(true); }}
        onMouseLeave={() => setOpen(false)}
        onClick={() => { measure(); setPinned(p => !p); }}
        style={{
          display: 'inline-block', padding: '0 4px', margin: '0 1px',
          border: 'none', borderRadius: 4, cursor: 'pointer',
          background: '#C8EDE9', color: '#0B7F73',
          fontSize: 11, fontWeight: 700, lineHeight: '16px',
          verticalAlign: 'baseline', fontFamily: fonts.sans,
        }}
      >
        [{index}]
      </button>

      {visible && pos && createPortal(
        <div
          onMouseEnter={() => setOpen(true)}
          onMouseLeave={() => setOpen(false)}
          style={{
            position: 'fixed',
            top: pos.top, left: pos.left,
            ...(pos.above
              ? { transform: 'translateY(calc(-100% - 4px))' }
              : { marginTop: 4 }),
            width: CITATION_POPUP_WIDTH, maxWidth: '90vw',
            padding: '12px 14px', zIndex: 1000,
            background: colors.bgCard, borderRadius: radius.md,
            border: `1px solid ${colors.border}`,
            boxShadow: '0 12px 32px rgba(15,93,87,0.16)',
            fontSize: 12, lineHeight: 1.65, fontFamily: fonts.sans,
            color: colors.textSecondary, textAlign: 'left',
            whiteSpace: 'normal',
          }}
        >
          <div style={{
            display: 'flex', alignItems: 'center', gap: 6, marginBottom: 6,
          }}>
            <span style={{
              padding: '1px 6px', borderRadius: 4, flexShrink: 0,
              background: '#C8EDE9', color: '#0B7F73', fontWeight: 700, fontSize: 11,
            }}>[{index}]</span>
            <span style={{
              fontWeight: 700, fontSize: 13, color: colors.text,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {evidence.sourceName || '未知来源'}
            </span>
          </div>

          {evidence.quote && (
            <div style={{ marginBottom: 8, maxHeight: 150, overflowY: 'auto' }}>
              「{(evidence.quote || '').slice(0, 400)}{(evidence.quote || '').length > 400 ? '…' : ''}」
            </div>
          )}

          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {evidence.sourceUrl ? (
              <a
                href={evidence.sourceUrl} target="_blank" rel="noreferrer"
                onClick={e => e.stopPropagation()}
                style={{ color: colors.primary, fontWeight: 600, textDecoration: 'none' }}
              >查看原文 ↗</a>
            ) : <span style={{ color: colors.textSecondary }}>暂无原文链接</span>}
            <span style={{ fontSize: 11, color: colors.textSecondary, marginLeft: 'auto' }}>
              {pinned ? '点击角标关闭' : '点击角标可固定'}
            </span>
          </div>
        </div>,
        document.body,
      )}
    </>
  );
}

function CitedText({ text, evidence }: { text: string; evidence?: ChatEvidenceItem[] }) {
  if (!text) return null;
  const parts = text.split(/(\[\d+\])/g);
  return (
    <>
      {parts.map((part, i) => {
        const m = part.match(/^\[(\d+)\]$/);
        if (!m) return <span key={i}>{part}</span>;
        const idx = parseInt(m[1], 10);
        const ev = evidence && idx >= 1 && idx <= evidence.length ? evidence[idx - 1] : null;
        if (!ev) return <span key={i}>{part}</span>;
        return <CitationChip key={i} index={idx} evidence={ev} />;
      })}
    </>
  );
}
