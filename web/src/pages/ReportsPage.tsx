
import { useCallback, useEffect, useState } from 'react';
import { colors, fonts, shadows } from '../components/styles';
import { apiFetch } from '../api/auth';

const API_BASE = '';

interface ReportSummary {
  id: string;
  task_id: string;
  version: number;
  knowledge_version: string;
  status: string;
  created_at: string;
  summary?: string;
}

interface TaskSummary {
  id: string;
  client_task_id: string;
  status: string;
  image_count: number;
  created_at: string;
}

const STATUS_META: Record<string, { label: string; color: string; bg: string }> = {
  published: { label: '已发布', color: '#059669', bg: '#ECFDF5' },
  refused: { label: '已拒答', color: '#D97706', bg: '#FFFBEB' },
  failed: { label: '失败', color: '#DC2626', bg: '#FEF2F2' },
  persist_failed: { label: '落库失败', color: '#DC2626', bg: '#FEF2F2' },
  cancelled: { label: '已取消', color: '#64748B', bg: '#F1F5F9' },
  intake: { label: '接收中', color: '#0E9F8F', bg: '#E4F6F4' },
  observing: { label: '解析中', color: '#0E9F8F', bg: '#E4F6F4' },
  retrieving: { label: '检索中', color: '#0E9F8F', bg: '#E4F6F4' },
  drafting: { label: '草拟中', color: '#0E9F8F', bg: '#E4F6F4' },
  validating: { label: '校验中', color: '#0E9F8F', bg: '#E4F6F4' },
  awaiting_images: { label: '待补图', color: '#D97706', bg: '#FFFBEB' },
  awaiting_memory_confirm: { label: '待确认', color: '#0E9F8F', bg: '#E4F6F4' },
  awaiting_publish_confirm: { label: '待发布', color: '#0E9F8F', bg: '#E4F6F4' },
};

function hasReport(status: string): boolean {
  return status === 'published' || status === 'refused';
}

interface ReportDetail extends ReportSummary {
  sections: Record<string, string>;
  citations: { claim_id: string; evidence_id: string; source_name: string; quote: string; source_url?: string }[];
  metadata?: Record<string, string>;
}

type ViewMode = 'list' | 'detail' | 'compare';

const SECTION_LABELS: Record<string, string> = {
  observation: '观察',
  facts: '事实',
  inferences: '推断',
  conflicts: '冲突',
  unknowns: '未知',
  related_to_you: '与你相关',
  memory_injection: '本次注入记忆',
  metric_interpretation: '指标解读',
  exercise_advice: '运动建议',
  lifestyle_advice: '生活方式建议',
  followup_advice: '随访建议',
};

const ISSUE_TYPES = [
  { value: 'wrong_citation', label: '引用错误' },
  { value: 'unsupported', label: '结论无证据支持' },
  { value: 'outdated', label: '信息过时' },
  { value: 'other', label: '其他' },
];

export default function ReportsPage() {
  const [mode, setMode] = useState<ViewMode>('list');
  const [items, setItems] = useState<TaskSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [detail, setDetail] = useState<ReportDetail | null>(null);
  const [versions, setVersions] = useState<ReportSummary[]>([]);
  const [leftId, setLeftId] = useState('');
  const [rightId, setRightId] = useState('');
  const [leftDetail, setLeftDetail] = useState<ReportDetail | null>(null);
  const [rightDetail, setRightDetail] = useState<ReportDetail | null>(null);

  const [feedbackType, setFeedbackType] = useState('wrong_citation');
  const [feedbackClaim, setFeedbackClaim] = useState('');
  const [feedbackDetail, setFeedbackDetail] = useState('');
  const [feedbackMsg, setFeedbackMsg] = useState('');
  const [feedbackSaving, setFeedbackSaving] = useState(false);

  const loadList = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const resp = await apiFetch(`${API_BASE}/api/v1/tasks`);
      const json = await resp.json();
      if (json.code === 0) {
        setItems(json.data?.items || []);
      } else {
        setError(json.error?.message || '加载失败');
      }
    } catch {
      setError('任务 API 不可达');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadList();
  }, [loadList]);

  const openTaskReport = async (taskId: string) => {
    setError('');
    setFeedbackMsg('');
    try {
      const verResp = await apiFetch(`${API_BASE}/api/v1/reports/task/${taskId}/versions`);
      const verJson = await verResp.json();
      const vers: ReportSummary[] = verJson.code === 0 ? (verJson.data?.items || []) : [];
      setVersions(vers);
      if (vers.length === 0) {
        setError('该任务尚未生成报告');
        return;
      }
      const latest = vers[0];
      const resp = await apiFetch(`${API_BASE}/api/v1/reports/${latest.id}`);
      const json = await resp.json();
      if (json.code !== 0) {
        setError(json.error?.message || '加载详情失败');
        return;
      }
      setDetail(json.data);
      setMode('detail');
    } catch {
      setError('加载报告失败');
    }
  };

  const startCompare = async (taskId: string, a?: string, b?: string) => {
    setError('');
    try {
      const verResp = await apiFetch(`${API_BASE}/api/v1/reports/task/${taskId}/versions`);
      const verJson = await verResp.json();
      const vers: ReportSummary[] = verJson.code === 0 ? (verJson.data?.items || []) : [];
      setVersions(vers);
      if (vers.length < 2) {
        setError('该任务至少需要两个版本才能对比');
        return;
      }
      const lid = a || vers[1]?.id || vers[0].id;
      const rid = b || vers[0].id;
      setLeftId(lid);
      setRightId(rid);
      const [l, r] = await Promise.all([
        apiFetch(`${API_BASE}/api/v1/reports/${lid}`).then(x => x.json()),
        apiFetch(`${API_BASE}/api/v1/reports/${rid}`).then(x => x.json()),
      ]);
      if (l.code === 0) setLeftDetail(l.data);
      if (r.code === 0) setRightDetail(r.data);
      setMode('compare');
    } catch {
      setError('加载版本对比失败');
    }
  };

  const reloadComparePair = async (lid: string, rid: string) => {
    setLeftId(lid);
    setRightId(rid);
    const [l, r] = await Promise.all([
      apiFetch(`${API_BASE}/api/v1/reports/${lid}`).then(x => x.json()),
      apiFetch(`${API_BASE}/api/v1/reports/${rid}`).then(x => x.json()),
    ]);
    if (l.code === 0) setLeftDetail(l.data);
    if (r.code === 0) setRightDetail(r.data);
  };

  const submitFeedback = async () => {
    if (!detail) return;
    setFeedbackSaving(true);
    setFeedbackMsg('');
    try {
      const resp = await apiFetch(`${API_BASE}/api/v1/feedback`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          report_id: detail.id,
          claim_id: feedbackClaim || 'general',
          issue_type: feedbackType,
          detail: feedbackDetail,
        }),
      });
      const json = await resp.json();
      if (json.code === 0) {
        setFeedbackMsg('已提交纠错反馈');
        setFeedbackDetail('');
        setFeedbackClaim('');
      } else {
        setFeedbackMsg(json.error?.message || '提交失败');
      }
    } catch {
      setFeedbackMsg('反馈 API 不可达');
    } finally {
      setFeedbackSaving(false);
    }
  };

  return (
    <div style={{ fontFamily: fonts.sans }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 20 }}>
        <h2 style={{ margin: 0, fontSize: 18, flex: 1 }}>健康咨询记录</h2>
        {mode !== 'list' && (
          <button onClick={() => { setMode('list'); loadList(); }} style={btnSecondary}>
            ← 返回列表
          </button>
        )}
        <button onClick={loadList} style={btnSecondary}>刷新</button>
      </div>

      {error && (
        <div style={{
          padding: '10px 14px', marginBottom: 16, borderRadius: 8,
          background: '#FEF2F2', color: colors.danger, fontSize: 13,
        }}>
          {error}
        </div>
      )}

      {mode === 'list' && (
        loading ? (
          <div style={{ color: colors.textSecondary }}>加载中…</div>
        ) : items.length === 0 ? (
          <div style={{
            padding: 40, textAlign: 'center', color: colors.textSecondary,
            background: colors.bg, borderRadius: 10,
          }}>
            暂无咨询记录。发起一次健康咨询后（无论成功或失败）都会出现在这里。
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {items.map(item => {
              const report = hasReport(item.status);
              return (
                <div
                  key={item.id}
                  style={{
                    background: colors.bgCard, border: `1px solid ${colors.border}`,
                    borderRadius: 10, padding: '14px 18px', boxShadow: shadows.card,
                    display: 'flex', gap: 12, alignItems: 'center',
                  }}
                >
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 6 }}>
                      <StatusPill status={item.status} />
                      <span style={{ fontSize: 12, color: colors.textSecondary }}>
                        {formatTime(item.created_at)}
                      </span>
                      <span style={{ fontSize: 12, color: '#94A3B8' }}>
                        · {item.image_count} 份材料
                      </span>
                    </div>
                    <div style={{ fontSize: 11, color: '#94A3B8' }}>
                      task {item.id.slice(0, 8)}…{item.client_task_id ? ` · ${item.client_task_id}` : ''}
                    </div>
                  </div>
                  {report ? (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      <button onClick={() => openTaskReport(item.id)} style={btnPrimary}>查看报告</button>
                      <button onClick={() => startCompare(item.id)} style={btnSecondary}>版本对比</button>
                    </div>
                  ) : (
                    <span style={{ fontSize: 12, color: '#94A3B8' }}>未生成报告</span>
                  )}
                </div>
              );
            })}
          </div>
        )
      )}

      {mode === 'detail' && detail && (
        <div>
          <div style={{
            background: colors.bgCard, border: `1px solid ${colors.border}`,
            borderRadius: 10, padding: 20, marginBottom: 16, boxShadow: shadows.card,
          }}>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginBottom: 12 }}>
              <h3 style={{ margin: 0, fontSize: 16 }}>报告 v{detail.version}</h3>
              <StatusPill status={detail.status} />
              <span style={{ fontSize: 12, color: colors.textSecondary, marginLeft: 'auto' }}>
                {formatTime(detail.created_at)}
              </span>
            </div>
            {Object.entries(detail.sections || {}).filter(([, v]) => v?.trim()).map(([k, v]) => (
              <div key={k} style={{ marginBottom: 14 }}>
                <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4, color: colors.primary }}>
                  {SECTION_LABELS[k] || k}
                </div>
                <p style={{ margin: 0, fontSize: 14, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{v}</p>
              </div>
            ))}
            {(detail.citations?.length ?? 0) > 0 && (
              <div style={{ marginTop: 16, borderTop: `1px solid ${colors.border}`, paddingTop: 12 }}>
                <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 8 }}>引用</div>
                {detail.citations.map((c, i) => (
                  <div key={i} style={{
                    fontSize: 12, background: colors.bg, borderRadius: 6,
                    padding: '8px 10px', marginBottom: 6,
                  }}>
                    <strong>{c.source_name || c.evidence_id || c.claim_id}</strong>
                    <div style={{ color: colors.textSecondary, marginTop: 4 }}>{c.quote}</div>
                    {c.source_url ? (
                      <a
                        href={c.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ display: 'inline-block', marginTop: 6, color: colors.primary, fontWeight: 600 }}
                      >
                        ↗ 打开来源核验
                      </a>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
            {versions.length >= 2 && (
              <button
                onClick={() => startCompare(detail.task_id, undefined, detail.id)}
                style={{ ...btnSecondary, marginTop: 12 }}
              >
                与其他版本对比
              </button>
            )}
          </div>

          {}
          <div style={{
            background: colors.bgCard, border: `1px solid ${colors.border}`,
            borderRadius: 10, padding: 20, boxShadow: shadows.card,
          }}>
            <h4 style={{ margin: '0 0 12px', fontSize: 15 }}>提交纠错反馈</h4>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              <label style={labelStyle}>
                问题类型
                <select
                  value={feedbackType}
                  onChange={e => setFeedbackType(e.target.value)}
                  style={inputStyle}
                >
                  {ISSUE_TYPES.map(t => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
              </label>
              <label style={labelStyle}>
                相关声明 / 证据 ID（可选）
                <input
                  value={feedbackClaim}
                  onChange={e => setFeedbackClaim(e.target.value)}
                  placeholder="claim_id 或 evidence_id"
                  style={inputStyle}
                />
              </label>
              <label style={labelStyle}>
                详细说明
                <textarea
                  value={feedbackDetail}
                  onChange={e => setFeedbackDetail(e.target.value)}
                  rows={3}
                  placeholder="请描述哪里引用错误或不准确"
                  style={{ ...inputStyle, resize: 'vertical' }}
                />
              </label>
              <button
                onClick={submitFeedback}
                disabled={feedbackSaving}
                style={btnPrimary}
              >
                {feedbackSaving ? '提交中…' : '提交反馈'}
              </button>
              {feedbackMsg && (
                <div style={{ fontSize: 13, color: feedbackMsg.includes('已提交') ? colors.success : colors.danger }}>
                  {feedbackMsg}
                </div>
              )}
            </div>
          </div>
        </div>
      )}

      {mode === 'compare' && (
        <div>
          <div style={{ display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
            <label style={labelStyle}>
              左侧版本
              <select
                value={leftId}
                onChange={e => reloadComparePair(e.target.value, rightId)}
                style={inputStyle}
              >
                {versions.map(v => (
                  <option key={v.id} value={v.id}>v{v.version} · {formatTime(v.created_at)}</option>
                ))}
              </select>
            </label>
            <label style={labelStyle}>
              右侧版本
              <select
                value={rightId}
                onChange={e => reloadComparePair(leftId, e.target.value)}
                style={inputStyle}
              >
                {versions.map(v => (
                  <option key={v.id} value={v.id}>v{v.version} · {formatTime(v.created_at)}</option>
                ))}
              </select>
            </label>
          </div>
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12,
          }}>
            <CompareColumn title={`v${leftDetail?.version ?? '?'}`} detail={leftDetail} />
            <CompareColumn title={`v${rightDetail?.version ?? '?'}`} detail={rightDetail} />
          </div>
        </div>
      )}
    </div>
  );
}

function CompareColumn({ title, detail }: { title: string; detail: ReportDetail | null }) {
  if (!detail) {
    return <div style={{ padding: 20, color: colors.textSecondary }}>无数据</div>;
  }
  return (
    <div style={{
      background: colors.bgCard, border: `1px solid ${colors.border}`,
      borderRadius: 10, padding: 16, boxShadow: shadows.card,
    }}>
      <h4 style={{ margin: '0 0 12px', fontSize: 14 }}>{title}</h4>
      {Object.entries(detail.sections || {}).filter(([, v]) => v?.trim()).map(([k, v]) => (
        <div key={k} style={{ marginBottom: 12 }}>
          <div style={{ fontWeight: 700, fontSize: 12, color: colors.primary, marginBottom: 4 }}>
            {SECTION_LABELS[k] || k}
          </div>
          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>{v}</p>
        </div>
      ))}
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const meta = STATUS_META[status] || { label: status || '未知', color: '#64748B', bg: '#F1F5F9' };
  return (
    <span style={{
      fontSize: 11, fontWeight: 600, padding: '2px 8px', borderRadius: 4,
      background: meta.bg, color: meta.color, whiteSpace: 'nowrap',
    }}>
      {meta.label}
    </span>
  );
}

function formatTime(iso: string) {
  if (!iso) return '';
  try {
    return new Date(iso).toLocaleString('zh-CN');
  } catch {
    return iso;
  }
}

const btnPrimary: React.CSSProperties = {
  padding: '8px 14px', border: 'none', borderRadius: 6, cursor: 'pointer',
  background: colors.primary, color: '#fff', fontWeight: 600, fontSize: 13,
};

const btnSecondary: React.CSSProperties = {
  padding: '8px 14px', border: `1px solid ${colors.border}`, borderRadius: 6,
  cursor: 'pointer', background: '#fff', color: colors.text, fontSize: 13,
};

const labelStyle: React.CSSProperties = {
  display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12,
  color: colors.textSecondary, fontWeight: 600,
};

const inputStyle: React.CSSProperties = {
  padding: '8px 10px', borderRadius: 6, border: `1px solid ${colors.border}`,
  fontSize: 13, fontWeight: 400, color: colors.text, fontFamily: fonts.sans,
};
