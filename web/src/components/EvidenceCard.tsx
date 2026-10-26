
import { colors, fonts, shadows } from './styles';

export interface EvidenceItem {
  evidenceId?: string;
  sourceType?: string;
  sourceName?: string;
  sourceLevel?: number;
  quote?: string;
  page?: number;
  sourceUrl?: string;
  knowledgeVersion?: string;

  title?: string;
  org?: string;
  year?: number | string;
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
}

interface Props {
  evidence: EvidenceItem[];
}

const LEVEL_LABELS: Record<number, string> = {
  1: '权威机构',
  2: '专业期刊',
  3: '开放研究',
  4: '用户资料',
};

const LEVEL_COLORS: Record<number, string> = {
  1: '#059669',
  2: '#2563EB',
  3: '#D97706',
  4: '#64748B',
};

const EVIDENCE_LEVEL_COLORS: Record<string, string> = {
  A: '#059669',
  B: '#2563EB',
  C: '#D97706',
};

const SOURCE_TYPE_LABELS: Record<string, string> = {
  guideline: '健康指南库',
  case: '病历案例库',
  metric_catalog: '体检指标目录',
};

function text(...values: Array<string | number | undefined>): string {
  for (const v of values) {
    if (v !== undefined && v !== null && String(v).trim() !== '') return String(v);
  }
  return '';
}

function CardShell({ children }: { children: React.ReactNode }) {
  return (
    <div style={{
      padding: 16, background: colors.bgCard, borderRadius: 10,
      border: `1px solid ${colors.border}`, boxShadow: shadows.card,
    }}>
      {children}
    </div>
  );
}

function CardHeader({ ev }: { ev: EvidenceItem }) {
  const typeLabel = SOURCE_TYPE_LABELS[ev.sourceType || ''] || '';
  const levelLabel = LEVEL_LABELS[ev.sourceLevel || 3] || '开放研究';
  const levelColor = LEVEL_COLORS[ev.sourceLevel || 3] || '#64748B';
  return (
    <div style={{
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      gap: 8, marginBottom: 8,
    }}>
      <span style={{ fontSize: 12, color: colors.textSecondary, fontWeight: 600 }}>
        {typeLabel || '证据'}
      </span>
      <span style={{
        padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 600,
        background: `${levelColor}1A`, color: levelColor, whiteSpace: 'nowrap',
      }}>
        {levelLabel}
      </span>
    </div>
  );
}

function Quote({ quote }: { quote: string }) {
  if (!quote) return null;
  return (
    <div style={{
      marginTop: 8, padding: '8px 12px', background: colors.bg, borderRadius: 6,
      fontSize: 12, color: colors.textSecondary, lineHeight: 1.6,
      fontFamily: fonts.mono, wordBreak: 'break-word',
    }}>
      {quote.length > 200 ? quote.slice(0, 200) + '…' : quote}
    </div>
  );
}

function SourceLink({ ev }: { ev: EvidenceItem }) {
  if (!ev.sourceUrl) return null;
  return (
    <a
      href={ev.sourceUrl}
      target="_blank"
      rel="noopener noreferrer"
      style={{ display: 'inline-block', marginTop: 8, fontSize: 12, color: colors.primary, fontWeight: 600, textDecoration: 'none' }}
    >
      ↗ 打开来源核验
    </a>
  );
}

export default function EvidenceCard({ evidence }: Props) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      {evidence.map((ev, i) => {
        const type = ev.sourceType || '';
        const pageText = ev.page ? ` · 第 ${ev.page} 页` : '';

        if (type === 'guideline') {
          const lvl = (ev.evidenceLevel || 'B').toUpperCase();
          const year = text(ev.year);
          const org = text(ev.org, ev.sourceName);
          return (
            <CardShell key={i}>
              <CardHeader ev={ev} />
              <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                <span style={{ fontWeight: 700, fontSize: 15, color: colors.text, flex: 1 }}>
                  {text(ev.title, ev.sourceName, '健康指南')}
                </span>
                <span style={{
                  padding: '2px 8px', borderRadius: 4, fontSize: 11, fontWeight: 700,
                  background: `${EVIDENCE_LEVEL_COLORS[lvl] || '#64748B'}1A`,
                  color: EVIDENCE_LEVEL_COLORS[lvl] || '#64748B', whiteSpace: 'nowrap',
                }}>
                  证据等级 {lvl}
                </span>
              </div>
              <div style={{ fontSize: 13, color: colors.textSecondary, lineHeight: 1.7, marginTop: 4 }}>
                📖 {org || '来源未标注'}{year ? ` · ${year}` : ''}{pageText}
              </div>
              <Quote quote={ev.quote || ''} />
              <SourceLink ev={ev} />
            </CardShell>
          );
        }

        if (type === 'case') {
          const rows: Array<[string, string]> = [
            ['主诉', text(ev.chiefComplaint)],
            ['检查发现', text(ev.findings)],
            ['干预方案', text(ev.intervention)],
            ['随访结局', text(ev.outcome)],
          ];
          return (
            <CardShell key={i}>
              <CardHeader ev={ev} />
              <div style={{ fontWeight: 700, fontSize: 15, color: colors.text, marginBottom: 4 }}>
                {text(ev.caseCode, ev.sourceName, '病历案例')}
              </div>
              <div style={{ fontSize: 13, color: colors.textSecondary, marginBottom: 8 }}>
                🧾 {[text(ev.ageBand), text(ev.sex)].filter(Boolean).join(' / ') || '人群信息未标注'}{pageText}
              </div>
              <div style={{ fontSize: 13, color: colors.text, lineHeight: 1.7 }}>
                {rows.filter(([, v]) => v).map(([label, value]) => (
                  <div key={label} style={{ display: 'flex', gap: 8 }}>
                    <span style={{ color: colors.textSecondary, flexShrink: 0 }}>{label}:</span>
                    <span>{value}</span>
                  </div>
                ))}
              </div>
              <Quote quote={ev.quote || ''} />
              <SourceLink ev={ev} />
            </CardShell>
          );
        }

        if (type === 'metric_catalog') {
          return (
            <CardShell key={i}>
              <CardHeader ev={ev} />
              <div style={{ fontWeight: 700, fontSize: 15, color: colors.text, marginBottom: 6 }}>
                {text(ev.metricName, ev.sourceName, '体检指标')}
              </div>
              <div style={{ fontSize: 13, color: colors.textSecondary, lineHeight: 1.7 }}>
                📏 参考区间: <strong style={{ color: colors.text }}>{text(ev.refText, ev.quote, '—')}</strong>{pageText}
              </div>
              <SourceLink ev={ev} />
            </CardShell>
          );
        }

        return (
          <CardShell key={i}>
            <CardHeader ev={ev} />
            <div style={{ fontWeight: 700, fontSize: 15, color: colors.text }}>
              {text(ev.sourceName, ev.title, '未标注来源')}
            </div>
            <Quote quote={ev.quote || ''} />
            <SourceLink ev={ev} />
          </CardShell>
        );
      })}
    </div>
  );
}
