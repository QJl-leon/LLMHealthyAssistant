
import { useEffect, useState } from 'react';
import { colors, fonts, shadows } from './styles';
import { MetricOverview, MetricTrend } from './MetricPanel';
import type { MetricItem, MetricTrendItem } from './MetricPanel';
import type { EvidenceItem } from './EvidenceCard';

interface Props {
  sections: Record<string, string>;
  evidence: EvidenceItem[];
  metrics?: MetricItem[];
  trends?: MetricTrendItem[];
  reportMeta?: {
    reportDate?: string;
    institution?: string;
  };
  refused?: boolean;
  refuseReason?: string;
}

interface SectionCard {
  label: string;
  icon: string;
  content: string;
  color: string;
  bgColor: string;
}

const LEVEL_TAG: Record<number, { label: string; color: string; bg: string }> = {
  1: { label: '权威机构', color: '#059669', bg: '#ECFDF5' },
  2: { label: '专业期刊', color: '#2563EB', bg: '#EFF6FF' },
  3: { label: '开放研究', color: '#D97706', bg: '#FFFBEB' },
  4: { label: '用户资料', color: '#64748B', bg: '#F1F5F9' },
};

const SOURCE_TYPE_LABELS: Record<string, string> = {
  guideline: '健康指南库',
  case: '病历案例库',
  metric_catalog: '体检指标目录',
};

function renderCitedText(
  text: string,
  onCite: (index: number) => void,
) {
  const parts = text.split(/(\[\d+\])/g);
  return parts.map((part, i) => {
    const m = part.match(/^\[(\d+)\]$/);
    if (m) {
      const idx = parseInt(m[1], 10);
      return (
        <button
          key={i}
          type="button"
          onClick={() => onCite(idx)}
          title={`查看证据 #${idx}`}
          style={{
            display: 'inline',
            padding: '0 3px',
            margin: '0 1px',
            border: 'none',
            borderRadius: 3,
            background: '#C8EDE9',
            color: '#0B7F73',
            fontSize: 11,
            fontWeight: 700,
            cursor: 'pointer',
            verticalAlign: 'super',
            lineHeight: 1,
          }}
        >
          {part}
        </button>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

function extractCitations(text: string): number[] {
  const found = text.match(/\[(\d+)\]/g) || [];
  return Array.from(new Set(found.map(x => parseInt(x.slice(1, -1), 10))));
}

function splitAdvice(content: string): string[] {
  return content
    .split(/\r?\n+/)
    .map(line => line.replace(/^\s*(?:[-*•·]|\d+[.、)])\s*/, '').trim())
    .filter(Boolean);
}

function AdviceList({ content, onCite }: { content: string; onCite: (index: number) => void }) {
  const items = splitAdvice(content);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      {items.map((item, i) => {
        const cites = extractCitations(item);
        return (
          <div
            key={i}
            style={{
              display: 'flex', gap: 10, alignItems: 'flex-start',
              padding: '10px 12px', background: colors.bgCard, borderRadius: 8,
              border: `1px solid ${colors.border}`,
            }}
          >
            <span style={{
              width: 20, height: 20, borderRadius: '50%', flexShrink: 0,
              background: colors.primaryLight, color: colors.primary,
              fontSize: 11, fontWeight: 700, display: 'flex',
              alignItems: 'center', justifyContent: 'center',
            }}>
              {i + 1}
            </span>
            <span style={{ flex: 1, fontSize: 14, lineHeight: 1.7, color: colors.text }}>
              {renderCitedText(item, onCite)}
            </span>
            <span style={{
              flexShrink: 0, display: 'flex', gap: 4, alignItems: 'center',
              paddingTop: 2,
            }}>
              {cites.length > 0 ? cites.map(n => (
                <button
                  key={n}
                  type="button"
                  onClick={() => onCite(n)}
                  title={`跳转到证据 #${n}`}
                  style={{
                    padding: '1px 6px', border: 'none', borderRadius: 4,
                    background: '#C8EDE9', color: '#0B7F73', fontSize: 11,
                    fontWeight: 700, cursor: 'pointer',
                  }}
                >
                  [{n}]
                </button>
              )) : (
                <span style={{ fontSize: 11, color: '#94A3B8' }}>无引用</span>
              )}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function ReportView({
  sections, evidence, metrics, trends, reportMeta, refused, refuseReason,
}: Props) {
  const [activeTab, setActiveTab] = useState<'report' | 'evidence'>('report');
  const [highlightIdx, setHighlightIdx] = useState<number | null>(null);

  useEffect(() => {
    if (activeTab !== 'evidence' || highlightIdx === null) return;
    const el = document.getElementById(`evidence-${highlightIdx + 1}`);
    el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [activeTab, highlightIdx]);

  const jumpToEvidence = (oneBased: number) => {
    setHighlightIdx(oneBased - 1);
    setActiveTab('evidence');
  };

  const metricReading = (sections.metric_reading || sections.metric_interpretation || sections['📈 指标解读'] || '').trim();

  const summary = (sections.summary || sections['👨‍⚕️ 医生解读'] || '').trim();

  const adviceCards: SectionCard[] = [
    { label: '运动建议', icon: '🏃',
      content: sections.exercise_advice || sections['🏃 运动建议'] || '',
      color: '#059669', bgColor: '#ECFDF5' },
    { label: '饮食建议', icon: '🥗',
      content: sections.lifestyle_advice || sections['🌙 生活方式建议'] || sections['🥗 饮食建议'] || '',
      color: '#7C3AED', bgColor: '#F5F3FF' },
    { label: '随访建议', icon: '📅',
      content: sections.followup_advice || sections['📅 随访建议'] || '',
      color: '#D97706', bgColor: '#FFFBEB' },
  ].filter(s => s.content && s.content.trim());

  const abnormalChips = (metrics || []).filter(
    m => m.flag === 'high' || m.flag === 'low' || m.flag === 'critical',
  );
  const hasReportContent = summary.length > 0 || metricReading.length > 0
    || adviceCards.length > 0
    || (metrics?.length ?? 0) > 0 || (trends?.length ?? 0) > 0;

  return (
    <div style={{ fontFamily: fonts.sans }}>
      {refused && (
        <div style={{
          background: '#FEF2F2', border: '1px solid #FECACA', borderRadius: 10,
          padding: '16px 20px', marginBottom: 20, color: '#991B1B',
        }}>
          <div style={{ fontWeight: 700, marginBottom: 6 }}>⛔ 证据不足，已拒答</div>
          <div style={{ fontSize: 14, lineHeight: 1.6 }}>
            {refuseReason || sections.unknowns || '未找到可核验证据，拒绝生成健康建议报告。'}
          </div>
        </div>
      )}

      {}
      <div style={{
        background: refused
          ? 'linear-gradient(135deg, #7F1D1D 0%, #B91C1C 100%)'
          : 'linear-gradient(135deg, #134E4A 0%, #0E9F8F 100%)',
        borderRadius: 12, padding: '28px 32px', marginBottom: 24, color: '#fff',
        boxShadow: shadows.elevated,
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
          <div>
            <div style={{ fontSize: 12, opacity: 0.7, fontWeight: 600, letterSpacing: 1, marginBottom: 6, textTransform: 'uppercase' }}>
              体检报告解读
            </div>
            <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, letterSpacing: -0.3 }}>
              {refused ? '咨询拒答' : '健康建议报告'}
            </h2>

            {abnormalChips.length > 0 && (
              <div style={{ marginTop: 16, display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                {abnormalChips.slice(0, 10).map((m, i) => (
                  <span key={i} style={{
                    padding: '2px 10px', borderRadius: 12, fontSize: 12,
                    background: 'rgba(255,255,255,0.2)', backdropFilter: 'blur(4px)',
                    border: '1px solid rgba(255,255,255,0.3)',
                  }}>
                    {m.metricName || m.metricCode} {m.value}{m.unit}
                  </span>
                ))}
                {abnormalChips.length > 10 && (
                  <span style={{ padding: '2px 10px', fontSize: 12, opacity: 0.7 }}>
                    +{abnormalChips.length - 10} 项
                  </span>
                )}
              </div>
            )}
          </div>

          <div style={{ textAlign: 'right', fontSize: 13, opacity: 0.85, lineHeight: 1.8 }}>
            {reportMeta?.reportDate && <div>🗓 体检日期: {reportMeta.reportDate}</div>}
            {reportMeta?.institution && <div>🏥 体检机构: {reportMeta.institution}</div>}
            {abnormalChips.length > 0 && <div>⚠️ {abnormalChips.length} 项指标异常</div>}
          </div>
        </div>
      </div>

      {}
      <div style={{ display: 'flex', gap: 0, marginBottom: 20, borderBottom: `2px solid ${colors.border}` }}>
        {(['report', 'evidence'] as const).map(tab => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            style={{
              padding: '10px 24px', border: 'none', background: 'none',
              fontSize: 14, fontWeight: 600, cursor: 'pointer',
              color: activeTab === tab ? colors.primary : colors.textSecondary,
              borderBottom: activeTab === tab ? `2px solid ${colors.primary}` : '2px solid transparent',
              marginBottom: -2, transition: 'all 0.2s',
            }}
          >
            {tab === 'report' ? '📊 分析报告' : `📚 证据来源 (${evidence.length})`}
          </button>
        ))}
      </div>

      {activeTab === 'report' && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {summary && (
            <div style={{
              background: '#F0FDF4', borderRadius: 12, padding: '20px 24px',
              border: '1px solid #BBF7D0', borderLeft: '4px solid #059669',
              boxShadow: shadows.card,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 10 }}>
                <span style={{ fontSize: 20 }}>👨‍⚕️</span>
                <span style={{ fontSize: 15, fontWeight: 700, color: '#065F46' }}>医生解读</span>
              </div>
              <p style={{
                margin: 0, fontSize: 15, lineHeight: 1.85, color: '#134E4A',
                whiteSpace: 'pre-wrap', fontWeight: 500,
              }}>
                {renderCitedText(summary, jumpToEvidence)}
              </p>
            </div>
          )}

          <MetricOverview metrics={metrics || []} />
          {!refused && <MetricTrend trends={trends || []} />}

          {}
          {metricReading && (
            <div style={{
              background: '#EEF2FF', borderRadius: 10, padding: '20px 24px',
              border: `1px solid ${colors.border}`, boxShadow: shadows.card,
            }}>
              <h4 style={{
                margin: '0 0 10px 0', fontSize: 15, fontWeight: 700,
                color: colors.text, display: 'flex', alignItems: 'center', gap: 6,
              }}>
                <span>📈</span> 指标解读
              </h4>
              <p style={{
                margin: 0, fontSize: 14, lineHeight: 1.8, color: colors.text,
                whiteSpace: 'pre-wrap',
              }}>
                {renderCitedText(metricReading, jumpToEvidence)}
              </p>
            </div>
          )}

          {adviceCards.map((section) => (
            <div
              key={section.label}
              style={{
                background: section.bgColor, borderRadius: 10, padding: '20px 24px',
                border: `1px solid ${colors.border}`, boxShadow: shadows.card,
              }}
            >
              <h4 style={{
                margin: '0 0 12px 0', fontSize: 15, fontWeight: 700,
                color: section.color, display: 'flex', alignItems: 'center', gap: 6,
              }}>
                <span>{section.icon}</span> {section.label}
                <span style={{ fontSize: 11, fontWeight: 400, color: colors.textSecondary, marginLeft: 4 }}>
                  每条建议附引用编号，点击可核验
                </span>
              </h4>
              <AdviceList content={section.content} onCite={jumpToEvidence} />
            </div>
          ))}

          {!hasReportContent && (
            <div style={{
              padding: 32, textAlign: 'center', color: colors.textSecondary,
              background: colors.bg, borderRadius: 10,
            }}>
              ℹ️ 暂无报告内容
            </div>
          )}
        </div>
      )}

      {activeTab === 'evidence' && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
          {evidence.map((ev, i) => {
            const lvl = LEVEL_TAG[ev.sourceLevel || 3] || LEVEL_TAG[3];
            const highlighted = highlightIdx === i;
            const typeLabel = SOURCE_TYPE_LABELS[ev.sourceType || ''] || '';
            const heading = ev.title || ev.caseCode || ev.metricName || ev.sourceName || '证据';
            return (
              <div
                key={ev.evidenceId || i}
                id={`evidence-${i + 1}`}
                style={{
                  background: colors.bgCard, borderRadius: 10, padding: '16px 20px',
                  border: highlighted ? `2px solid ${colors.primary}` : `1px solid ${colors.border}`,
                  boxShadow: highlighted ? shadows.elevated : shadows.card,
                  transition: 'box-shadow 0.2s',
                }}
                onMouseEnter={e => (e.currentTarget.style.boxShadow = shadows.elevated)}
                onMouseLeave={e => (e.currentTarget.style.boxShadow = highlighted ? shadows.elevated : shadows.card)}
              >
                <div style={{
                  display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
                  marginBottom: 10,
                }}>
                  <span style={{
                    fontWeight: 700, fontSize: 15, color: colors.text,
                    wordBreak: 'break-word',
                  }}>
                    <span style={{
                      display: 'inline-block', minWidth: 22, marginRight: 6,
                      padding: '0 6px', borderRadius: 4, fontSize: 11,
                      background: '#C8EDE9', color: '#0B7F73', fontWeight: 700,
                    }}>
                      [{i + 1}]
                    </span>
                    {heading}
                  </span>
                  <span style={{
                    padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
                    background: lvl.bg, color: lvl.color, whiteSpace: 'nowrap',
                    flexShrink: 0, marginLeft: 8,
                  }}>
                    {lvl.label}
                  </span>
                </div>
                <div style={{ fontSize: 13, color: colors.textSecondary, lineHeight: 1.6 }}>
                  {typeLabel && (
                    <div style={{ fontSize: 11, color: colors.primary, fontWeight: 600, marginBottom: 6 }}>
                      {typeLabel}
                    </div>
                  )}
                  <div style={{
                    padding: '8px 12px', background: colors.bg, borderRadius: 6,
                    fontSize: 12, fontFamily: fonts.mono, marginBottom: 8,
                    wordBreak: 'break-all',
                  }}>
                    {(ev.quote || '').length > 120 ? (ev.quote || '').slice(0, 120) + '…' : (ev.quote || '—')}
                  </div>
                  <div style={{ fontSize: 11, color: '#94A3B8', marginBottom: 8 }}>
                    {[ev.metricName, ev.org, ev.year ? String(ev.year) : '', ev.refText ? `参考区间 ${ev.refText}` : '']
                      .filter(Boolean).join(' · ') || typeLabel || '来源未标注'}
                    {ev.page ? ` · 第 ${ev.page} 页` : ''}
                    {ev.knowledgeVersion ? ` · kv ${ev.knowledgeVersion}` : ''}
                  </div>
                  {ev.sourceUrl ? (
                    <a
                      href={ev.sourceUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      style={{
                        fontSize: 12, color: colors.primary, fontWeight: 600,
                        textDecoration: 'none',
                      }}
                    >
                      ↗ 打开来源核验
                    </a>
                  ) : (
                    <span style={{ fontSize: 11, color: '#94A3B8' }}>暂无公开链接</span>
                  )}
                </div>
              </div>
            );
          })}
          {evidence.length === 0 && (
            <div style={{
              padding: 32, textAlign: 'center', color: colors.textSecondary,
              background: colors.bg, borderRadius: 10, gridColumn: '1 / -1',
            }}>
              ℹ️ 暂未匹配到相关证据
            </div>
          )}
        </div>
      )}
    </div>
  );
}
