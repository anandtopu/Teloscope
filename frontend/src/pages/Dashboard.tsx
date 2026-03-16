/**
 * AgentLens — Main Dashboard Page
 * Real-time overview: KPIs, latency chart, cost breakdown, recent traces, active alerts.
 */
import React, { useEffect } from 'react';
import {
  LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, PieChart, Pie, Cell, Legend,
} from 'recharts';
import {
  Activity, AlertTriangle, CheckCircle, Clock,
  DollarSign, Zap, TrendingUp, TrendingDown,
} from 'lucide-react';
import { useMetricsSummary, useCostBreakdown, useTraces, useAlerts } from '../hooks/api';
import { useAppStore, TIME_RANGES } from '../store';

// ─── Color palette ────────────────────────────────────────────────
const COLORS = {
  primary:  '#0D7EC4',
  success:  '#00A896',
  error:    '#E74C3C',
  warning:  '#F39C12',
  neutral:  '#95A5A6',
  bg:       '#0F1117',
  card:     '#1A1D27',
  border:   '#2A2D3A',
  text:     '#E2E8F0',
  muted:    '#718096',
};

const CHART_COLORS = ['#0D7EC4', '#00A896', '#F39C12', '#E74C3C', '#9B59B6', '#1ABC9C'];

// ─── KPI Card ─────────────────────────────────────────────────────
function KpiCard({
  label, value, unit = '', icon: Icon, trend, trendLabel, color = COLORS.primary,
}: {
  label: string;
  value: string | number;
  unit?: string;
  icon: React.ElementType;
  trend?: 'up' | 'down' | 'neutral';
  trendLabel?: string;
  color?: string;
}) {
  return (
    <div style={{
      background: COLORS.card,
      border: `1px solid ${COLORS.border}`,
      borderRadius: 12,
      padding: '20px 24px',
      display: 'flex',
      flexDirection: 'column',
      gap: 12,
      flex: '1 1 180px',
      minWidth: 160,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <span style={{ color: COLORS.muted, fontSize: 13, fontWeight: 500 }}>{label}</span>
        <div style={{
          background: `${color}22`,
          borderRadius: 8,
          padding: '6px 8px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <Icon size={16} color={color} />
        </div>
      </div>
      <div>
        <span style={{ color: COLORS.text, fontSize: 28, fontWeight: 700, letterSpacing: '-0.5px' }}>
          {value}
        </span>
        {unit && <span style={{ color: COLORS.muted, fontSize: 13, marginLeft: 4 }}>{unit}</span>}
      </div>
      {trendLabel && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
          {trend === 'up'   ? <TrendingUp size={12} color={COLORS.error} />   :
           trend === 'down' ? <TrendingDown size={12} color={COLORS.success} /> :
           null}
          <span style={{ color: COLORS.muted, fontSize: 12 }}>{trendLabel}</span>
        </div>
      )}
    </div>
  );
}

// ─── Status Badge ──────────────────────────────────────────────────
function StatusBadge({ status }: { status: string }) {
  const cfg = status === 'OK'
    ? { bg: '#00A89622', color: '#00A896', label: 'OK' }
    : status === 'ERROR'
    ? { bg: '#E74C3C22', color: '#E74C3C', label: 'ERROR' }
    : { bg: '#95A5A622', color: '#95A5A6', label: status };

  return (
    <span style={{
      background: cfg.bg,
      color: cfg.color,
      borderRadius: 6,
      padding: '2px 8px',
      fontSize: 11,
      fontWeight: 600,
      letterSpacing: '0.5px',
    }}>
      {cfg.label}
    </span>
  );
}

// ─── Alert Severity Badge ─────────────────────────────────────────
function SeverityBadge({ severity }: { severity: string }) {
  const colors: Record<string, { bg: string; fg: string }> = {
    critical: { bg: '#E74C3C33', fg: '#E74C3C' },
    error:    { bg: '#E74C3C22', fg: '#E95C4B' },
    warning:  { bg: '#F39C1222', fg: '#F39C12' },
    info:     { bg: '#0D7EC422', fg: '#0D7EC4' },
  };
  const c = colors[severity] ?? colors.info;
  return (
    <span style={{
      background: c.bg, color: c.fg,
      borderRadius: 6, padding: '2px 8px',
      fontSize: 11, fontWeight: 600, textTransform: 'uppercase',
    }}>
      {severity}
    </span>
  );
}

// ─── Section Header ────────────────────────────────────────────────
function SectionHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
      <h2 style={{ color: COLORS.text, fontSize: 16, fontWeight: 600, margin: 0 }}>{title}</h2>
      {action}
    </div>
  );
}

// ─── Mock latency sparkline data (replace with real API time-series) ──────────
function generateMockLatencyData(points = 24) {
  return Array.from({ length: points }, (_, i) => ({
    time: `${String(i).padStart(2, '0')}:00`,
    p50:  Math.round(120 + Math.random() * 80),
    p95:  Math.round(280 + Math.random() * 200),
    p99:  Math.round(500 + Math.random() * 400),
  }));
}

// ─── Dashboard Page ────────────────────────────────────────────────
export default function DashboardPage() {
  const { timeRange, setTimeRange } = useAppStore();
  const { data: metricsData, isLoading: metricsLoading } = useMetricsSummary();
  const { data: costData } = useCostBreakdown();
  const { data: tracesData } = useTraces({ limit: 10 });
  const { data: alertsData } = useAlerts(false);

  const m = metricsData?.metrics;
  const latencyData = generateMockLatencyData();

  return (
    <div style={{ padding: '24px 32px', minHeight: '100vh', background: COLORS.bg, fontFamily: "'Inter', system-ui, sans-serif" }}>

      {/* ── Page Header ────────────────────────────────────────── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 28 }}>
        <div>
          <h1 style={{ color: COLORS.text, fontSize: 22, fontWeight: 700, margin: 0 }}>
            Overview
          </h1>
          <p style={{ color: COLORS.muted, fontSize: 13, marginTop: 4 }}>
            Real-time agent performance across all frameworks
          </p>
        </div>

        {/* Time range selector */}
        <div style={{ display: 'flex', gap: 6, background: COLORS.card, borderRadius: 10, padding: 4, border: `1px solid ${COLORS.border}` }}>
          {TIME_RANGES.map((tr) => (
            <button
              key={tr.label}
              onClick={() => setTimeRange(tr)}
              style={{
                padding: '6px 14px',
                borderRadius: 7,
                border: 'none',
                cursor: 'pointer',
                fontSize: 13,
                fontWeight: 500,
                background: timeRange.label === tr.label ? COLORS.primary : 'transparent',
                color:      timeRange.label === tr.label ? '#fff' : COLORS.muted,
                transition: 'all 0.15s',
              }}
            >
              {tr.label}
            </button>
          ))}
        </div>
      </div>

      {/* ── KPI Row ─────────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 28 }}>
        <KpiCard
          label="Invocations"
          value={metricsLoading ? '—' : (m?.invocation_count ?? 0).toLocaleString()}
          icon={Activity}
          color={COLORS.primary}
          trendLabel={`Last ${timeRange.label}`}
        />
        <KpiCard
          label="Error Rate"
          value={metricsLoading ? '—' : `${((m?.error_rate ?? 0) * 100).toFixed(1)}`}
          unit="%"
          icon={AlertTriangle}
          color={m?.error_rate && m.error_rate > 0.05 ? COLORS.error : COLORS.success}
          trend={m?.error_rate && m.error_rate > 0.05 ? 'up' : 'down'}
          trendLabel={m?.error_rate && m.error_rate > 0.05 ? 'Above threshold' : 'Within SLO'}
        />
        <KpiCard
          label="Avg Latency"
          value={metricsLoading ? '—' : Math.round(m?.avg_latency_ms ?? 0).toLocaleString()}
          unit="ms"
          icon={Clock}
          color={COLORS.warning}
        />
        <KpiCard
          label="P95 Latency"
          value={metricsLoading ? '—' : Math.round(m?.p95_latency_ms ?? 0).toLocaleString()}
          unit="ms"
          icon={Zap}
          color={COLORS.warning}
        />
        <KpiCard
          label="Total Cost"
          value={metricsLoading ? '—' : `$${(m?.total_cost_usd ?? 0).toFixed(4)}`}
          icon={DollarSign}
          color={COLORS.success}
          trendLabel={`${(m?.total_tokens ?? 0).toLocaleString()} tokens`}
        />
        <KpiCard
          label="Success Rate"
          value={metricsLoading ? '—' : `${(100 - (m?.error_rate ?? 0) * 100).toFixed(1)}`}
          unit="%"
          icon={CheckCircle}
          color={COLORS.success}
        />
      </div>

      {/* ── Charts Row ──────────────────────────────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 20, marginBottom: 28 }}>

        {/* Latency chart */}
        <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 24 }}>
          <SectionHeader title="Latency Percentiles (ms)" />
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={latencyData} margin={{ top: 4, right: 8, left: -20, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
              <XAxis dataKey="time" tick={{ fill: COLORS.muted, fontSize: 11 }} tickLine={false} />
              <YAxis tick={{ fill: COLORS.muted, fontSize: 11 }} tickLine={false} />
              <Tooltip
                contentStyle={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 8 }}
                labelStyle={{ color: COLORS.muted }}
                itemStyle={{ color: COLORS.text }}
              />
              <Legend wrapperStyle={{ color: COLORS.muted, fontSize: 12 }} />
              <Line type="monotone" dataKey="p50" stroke={COLORS.success}  dot={false} strokeWidth={2} name="P50" />
              <Line type="monotone" dataKey="p95" stroke={COLORS.warning}  dot={false} strokeWidth={2} name="P95" />
              <Line type="monotone" dataKey="p99" stroke={COLORS.error}    dot={false} strokeWidth={2} name="P99" />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Cost by model */}
        <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 24 }}>
          <SectionHeader title="LLM Cost by Model" />
          {costData?.breakdown && costData.breakdown.length > 0 ? (
            <ResponsiveContainer width="100%" height={220}>
              <BarChart
                data={costData.breakdown.slice(0, 6).map((b) => ({
                  name: `${b.provider}/${b.model}`.slice(0, 20),
                  cost: b.cost_usd,
                  calls: b.call_count,
                }))}
                margin={{ top: 4, right: 8, left: -20, bottom: 40 }}
              >
                <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                <XAxis dataKey="name" tick={{ fill: COLORS.muted, fontSize: 10 }} angle={-30} textAnchor="end" />
                <YAxis tick={{ fill: COLORS.muted, fontSize: 11 }} tickLine={false} />
                <Tooltip
                  contentStyle={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 8 }}
                  formatter={(v: number) => [`$${v.toFixed(6)}`, 'Cost']}
                />
                <Bar dataKey="cost" fill={COLORS.primary} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          ) : (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 220, color: COLORS.muted, fontSize: 13 }}>
              No cost data yet
            </div>
          )}
        </div>
      </div>

      {/* ── Bottom Row: Recent Traces + Alerts ──────────────────── */}
      <div style={{ display: 'grid', gridTemplateColumns: '3fr 2fr', gap: 20 }}>

        {/* Recent Traces */}
        <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 24 }}>
          <SectionHeader
            title="Recent Traces"
            action={
              <button style={{ color: COLORS.primary, background: 'none', border: 'none', cursor: 'pointer', fontSize: 13 }}>
                View all →
              </button>
            }
          />
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
                {['Agent', 'Status', 'Duration', 'Tokens', 'Cost', 'LLM Calls'].map((h) => (
                  <th key={h} style={{ color: COLORS.muted, fontSize: 12, fontWeight: 600, textAlign: 'left', padding: '8px 12px' }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {tracesData?.traces?.map((trace) => (
                <tr
                  key={trace.trace_id}
                  style={{ borderBottom: `1px solid ${COLORS.border}`, cursor: 'pointer' }}
                  onMouseOver={(e) => (e.currentTarget.style.background = COLORS.border + '44')}
                  onMouseOut={(e)  => (e.currentTarget.style.background = 'transparent')}
                >
                  <td style={{ padding: '10px 12px', color: COLORS.text, fontSize: 13 }}>
                    <span title={trace.trace_id}>{trace.agent_name}</span>
                    <span style={{ color: COLORS.muted, fontSize: 11, display: 'block' }}>
                      {trace.framework}
                    </span>
                  </td>
                  <td style={{ padding: '10px 12px' }}><StatusBadge status={trace.status} /></td>
                  <td style={{ padding: '10px 12px', color: COLORS.muted, fontSize: 13 }}>
                    {trace.duration_ms ? `${Math.round(trace.duration_ms)}ms` : '—'}
                  </td>
                  <td style={{ padding: '10px 12px', color: COLORS.muted, fontSize: 13 }}>
                    {trace.total_tokens.toLocaleString()}
                  </td>
                  <td style={{ padding: '10px 12px', color: COLORS.success, fontSize: 13 }}>
                    ${trace.total_cost_usd.toFixed(6)}
                  </td>
                  <td style={{ padding: '10px 12px', color: COLORS.muted, fontSize: 13 }}>
                    {trace.llm_call_count}
                  </td>
                </tr>
              ))}
              {(!tracesData?.traces || tracesData.traces.length === 0) && (
                <tr>
                  <td colSpan={6} style={{ padding: 32, textAlign: 'center', color: COLORS.muted, fontSize: 13 }}>
                    No traces yet. Instrument your agent and send the first trace.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>

        {/* Active Alerts */}
        <div style={{ background: COLORS.card, border: `1px solid ${COLORS.border}`, borderRadius: 12, padding: 24 }}>
          <SectionHeader
            title={`Active Alerts ${alertsData?.alerts?.length ? `(${alertsData.alerts.length})` : ''}`}
            action={
              <button style={{ color: COLORS.primary, background: 'none', border: 'none', cursor: 'pointer', fontSize: 13 }}>
                Manage →
              </button>
            }
          />
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {alertsData?.alerts?.length ? alertsData.alerts.map((alert: any) => (
              <div key={alert.alert_id} style={{
                background: COLORS.bg,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 8,
                padding: '12px 14px',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                  <span style={{ color: COLORS.text, fontSize: 13, fontWeight: 600 }}>{alert.title}</span>
                  <SeverityBadge severity={alert.severity} />
                </div>
                <p style={{ color: COLORS.muted, fontSize: 12, margin: '0 0 6px' }}>{alert.description}</p>
                <div style={{ color: COLORS.muted, fontSize: 11 }}>
                  Fired: {new Date(alert.fired_at).toLocaleTimeString()}
                  {alert.agent_name && ` · ${alert.agent_name}`}
                </div>
              </div>
            )) : (
              <div style={{ textAlign: 'center', color: COLORS.muted, fontSize: 13, padding: '40px 0' }}>
                <CheckCircle size={28} color={COLORS.success} style={{ marginBottom: 8 }} />
                <div>All clear — no active alerts</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
