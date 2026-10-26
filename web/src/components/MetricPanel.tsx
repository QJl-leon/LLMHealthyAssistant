
import { colors, fonts, shadows } from './styles';

export interface MetricItem {
  metricCode: string;
  metricName: string;
  category: string;
  value: string;
  unit: string;
  refText: string;
  flag: string;
}

export interface TrendPoint {
  date: string;
  value: number;
}

export interface MetricTrendItem {
  metricCode: string;
  metricName: string;
  unit: string;
  points: TrendPoint[];
  direction: string;
}

function pick(raw: Record<string, unknown>, ...keys: string[]): unknown {
  for (const k of keys) {
    const v = raw[k];
    if (v !== undefined && v !== null && v !== '') return v;
  }
  return undefined;
}

function toStr(v: unknown): string {
  return v === undefined || v === null ? '' : String(v);
}

function toNum(v: unknown): number | null {
  if (typeof v === 'number') return Number.isFinite(v) ? v : null;
  if (typeof v === 'string' && v.trim() !== '') {
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

function refText(raw: Record<string, unknown>): string {
  const text = toStr(pick(raw, 'refText', 'ref_text'));
  if (text) return text;
  const low = toNum(pick(raw, 'refLow', 'ref_low'));
  const high = toNum(pick(raw, 'refHigh', 'ref_high'));
  const unit = toStr(pick(raw, 'unit'));
  if (low !== null && high !== null) return `${low}~${high} ${unit}`.trim();
  if (high !== null) return `<${high} ${unit}`.trim();
  if (low !== null) return `>${low} ${unit}`.trim();
  return '';
}

export function normalizeMetric(raw: Record<string, unknown>): MetricItem {
  const valueNum = toNum(pick(raw, 'valueNum', 'value_num', 'value'));
  const valueText = toStr(pick(raw, 'valueText', 'value_text'));
  return {
    metricCode: toStr(pick(raw, 'metricCode', 'metric_code')),
    metricName: toStr(pick(raw, 'metricName', 'metric_name', 'name')),
    category: toStr(pick(raw, 'category')) || '其他',
    value: valueText || (valueNum !== null ? String(valueNum) : '—'),
    unit: toStr(pick(raw, 'unit')),
    refText: refText(raw),
    flag: (toStr(pick(raw, 'flag')) || 'unknown').toLowerCase(),
  };
}

export function normalizeTrend(raw: Record<string, unknown>): MetricTrendItem {
  const rawPoints = (pick(raw, 'points', 'history', 'series') as unknown[]) || [];
  const points: TrendPoint[] = [];
  for (const p of rawPoints) {
    if (!p || typeof p !== 'object') continue;
    const item = p as Record<string, unknown>;
    const value = toNum(pick(item, 'value', 'valueNum', 'value_num'));
    if (value === null) continue;
    points.push({ date: toStr(pick(item, 'date', 'measuredAt', 'measured_at')), value });
  }
  points.sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));

  let direction = toStr(pick(raw, 'direction'));
  if (!direction && points.length >= 2) {
    const delta = points[points.length - 1].value - points[0].value;
    const scale = Math.abs(points[0].value) || 1;
    direction = Math.abs(delta) / scale < 0.05 ? 'stable' : delta > 0 ? 'rising' : 'falling';
  }

  return {
    metricCode: toStr(pick(raw, 'metricCode', 'metric_code')),
    metricName: toStr(pick(raw, 'metricName', 'metric_name', 'name')),
    unit: toStr(pick(raw, 'unit')),
    points,
    direction: direction || (points.length >= 2 ? 'stable' : ''),
  };
}

export function normalizeMetrics(payload: unknown): MetricItem[] {
  if (!Array.isArray(payload)) return [];
  return payload
    .filter((x): x is Record<string, unknown> => !!x && typeof x === 'object')
    .map(normalizeMetric);
}

export function normalizeTrends(payload: unknown): MetricTrendItem[] {
  if (!Array.isArray(payload)) return [];
  return payload
    .filter((x): x is Record<string, unknown> => !!x && typeof x === 'object')
    .map(normalizeTrend);
}

interface FlagStyle {
  arrow: string;
  color: string;
  bg: string;
}

const FLAG_STYLES: Record<string, FlagStyle> = {
  high:     { arrow: '↑', color: '#DC2626', bg: '#FEF2F2' },
  low:      { arrow: '↓', color: '#D97706', bg: '#FFFBEB' },
  critical: { arrow: '↑↑', color: '#991B1B', bg: '#FEE2E2' },
  normal:   { arrow: '正常', color: '#059669', bg: '#ECFDF5' },
  unknown:  { arrow: '—', color: '#94A3B8', bg: '#F8FAFC' },
};

export function flagStyle(flag: string): FlagStyle {
  return FLAG_STYLES[flag] || FLAG_STYLES.unknown;
}

export function isAbnormal(m: MetricItem): boolean {
  return m.flag === 'high' || m.flag === 'low' || m.flag === 'critical';
}

const CATEGORY_ORDER = ['血脂', '血糖', '肝功能', '肾功能', '血压', '体格'];

function orderCategories(categories: string[]): string[] {
  return [...categories].sort((a, b) => {
    const ia = CATEGORY_ORDER.indexOf(a);
    const ib = CATEGORY_ORDER.indexOf(b);
    if (ia === -1 && ib === -1) return a.localeCompare(b, 'zh-CN');
    if (ia === -1) return 1;
    if (ib === -1) return -1;
    return ia - ib;
  });
}

export function MetricOverview({ metrics }: { metrics: MetricItem[] }) {
  if (metrics.length === 0) return null;

  const abnormal = metrics.filter(isAbnormal).length;
  const groups = new Map<string, MetricItem[]>();
  for (const m of metrics) {
    const list = groups.get(m.category) || [];
    list.push(m);
    groups.set(m.category, list);
  }

  return (
    <div style={{
      background: colors.bgCard, borderRadius: 12, padding: '20px 24px',
      border: `1px solid ${colors.border}`, boxShadow: shadows.card, marginBottom: 24,
    }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 10, marginBottom: 16 }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: colors.text }}>
          📊 指标概览
        </h3>
        <span style={{ fontSize: 12, color: colors.textSecondary }}>
          共 {metrics.length} 项
        </span>
        {abnormal > 0 && (
          <span style={{
            fontSize: 12, fontWeight: 700, color: colors.danger,
            background: '#FEF2F2', padding: '2px 8px', borderRadius: 4,
          }}>
            {abnormal} 项异常
          </span>
        )}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        {orderCategories([...groups.keys()]).map(category => (
          <div key={category}>
            <div style={{
              fontSize: 13, fontWeight: 700, color: colors.primary,
              marginBottom: 6, paddingBottom: 4,
              borderBottom: `1px solid ${colors.border}`,
            }}>
              {category}
            </div>
            <div style={{ display: 'flex', flexDirection: 'column' }}>
              {groups.get(category)!.map((m, i) => {
                const fs = flagStyle(m.flag);
                const bad = isAbnormal(m);
                return (
                  <div
                    key={`${m.metricCode || m.metricName}-${i}`}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 12,
                      padding: '8px 10px', borderRadius: 6,
                      background: bad ? fs.bg : 'transparent',
                    }}
                  >
                    <span style={{ flex: '1 1 40%', fontSize: 14, color: colors.text }}>
                      {m.metricName || m.metricCode || '未知指标'}
                    </span>
                    <span style={{
                      flex: '0 0 auto', fontSize: 15, fontWeight: 700,
                      color: bad ? fs.color : colors.text, fontFamily: fonts.mono,
                    }}>
                      {m.value}
                      {m.unit && (
                        <span style={{ fontSize: 11, fontWeight: 400, marginLeft: 3 }}>
                          {m.unit}
                        </span>
                      )}
                      <span style={{ marginLeft: 6, fontSize: 12 }}>{fs.arrow}</span>
                    </span>
                    <span style={{
                      flex: '1 1 35%', fontSize: 12, color: colors.textSecondary,
                      textAlign: 'right',
                    }}>
                      参考区间 {m.refText || '—'}
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const DIRECTION_STYLES: Record<string, { label: string; color: string; icon: string }> = {
  rising:  { label: '上升', color: '#DC2626', icon: '↗' },
  falling: { label: '下降', color: '#059669', icon: '↘' },
  stable:  { label: '平稳', color: '#64748B', icon: '→' },
};

function Sparkline({ points, color }: { points: TrendPoint[]; color: string }) {
  if (points.length < 2) return null;
  const values = points.map(p => p.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const w = 96;
  const h = 28;
  const coords = points.map((p, i) => {
    const x = (i / (points.length - 1)) * w;
    const y = h - ((p.value - min) / span) * h;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });

  return (
    <svg width={w} height={h} style={{ display: 'block' }} aria-hidden="true">
      <polyline
        points={coords.join(' ')}
        fill="none"
        stroke={color}
        strokeWidth={1.8}
        strokeLinejoin="round"
        strokeLinecap="round"
      />
      <circle
        cx={coords[coords.length - 1].split(',')[0]}
        cy={coords[coords.length - 1].split(',')[1]}
        r={2.6}
        fill={color}
      />
    </svg>
  );
}

export function MetricTrend({ trends }: { trends: MetricTrendItem[] }) {
  if (trends.length === 0) return null;

  return (
    <div style={{
      background: colors.bgCard, borderRadius: 12, padding: '20px 24px',
      border: `1px solid ${colors.border}`, boxShadow: shadows.card, marginBottom: 24,
    }}>
      <h3 style={{ margin: '0 0 16px', fontSize: 16, fontWeight: 700, color: colors.text }}>
        📈 指标趋势
      </h3>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {trends.map((t, i) => {
          const dir = DIRECTION_STYLES[t.direction] || { label: '数据不足', color: '#94A3B8', icon: '·' };
          const first = t.points[0];
          const last = t.points[t.points.length - 1];
          return (
            <div
              key={`${t.metricCode || t.metricName}-${i}`}
              style={{
                display: 'flex', alignItems: 'center', gap: 14,
                padding: '10px 12px', borderRadius: 8, background: colors.bg,
              }}
            >
              <span style={{ flex: '1 1 30%', fontSize: 14, fontWeight: 600, color: colors.text }}>
                {t.metricName || t.metricCode}
              </span>
              <span style={{ flex: '0 0 auto', fontFamily: fonts.mono, fontSize: 13, color: colors.textSecondary }}>
                {first ? `${first.value} → ${last ? last.value : '—'}` : '—'}
                {t.unit && <span style={{ fontSize: 11, marginLeft: 4 }}>{t.unit}</span>}
              </span>
              <span style={{ flex: '0 0 auto', color: dir.color, fontSize: 12, fontWeight: 700 }}>
                {dir.icon} {dir.label}
              </span>
              <Sparkline points={t.points} color={dir.color} />
              {first && last && (
                <span style={{ fontSize: 11, color: colors.textSecondary, whiteSpace: 'nowrap' }}>
                  {first.date} → {last.date}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
