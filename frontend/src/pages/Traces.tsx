/**
 * AgentLens — Traces Page
 * Lists all traces; clicking one opens the span waterfall/tree detail view.
 */
import React, { useState } from 'react';
import { Search, Filter, ChevronRight, ChevronDown, Cpu, Wrench, Database, Shield, Link } from 'lucide-react';
import { useTraces, useTrace, Trace, Span } from '../hooks/api';
import { useAppStore } from '../store';

const COLORS = {
  bg: '#0F1117', card: '#1A1D27', border: '#2A2D3A',
  text: '#E2E8F0', muted: '#718096', primary: '#0D7EC4',
  success: '#00A896', error: '#E74C3C', warning: '#F39C12',
};

const KIND_CONFIG: Record<string, { color: string; icon: React.ElementType }> = {
  agent:     { color: '#0D7EC4', icon: Cpu },
  llm:       { color: '#9B59B6', icon: Cpu },
  tool:      { color: '#00A896', icon: Wrench },
  retrieval: { color: '#F39C12', icon: Database },
  memory:    { color: '#1ABC9C', icon: Database },
  chain:     { color: '#95A5A6', icon: Link },
  guardrail: { color: '#E74C3C', icon: Shield },
};

// ─── Span Row in waterfall ─────────────────────────────────────────

function SpanRow({
  span, depth, totalDurationMs, traceStart,
}: {
  span: Span & { children?: Span[] };
  depth: number;
  totalDurationMs: number;
  traceStart: number;
}) {
  const [open, setOpen] = useState(depth < 2);
  const cfg = KIND_CONFIG[span.kind] ?? KIND_CONFIG.chain;
  const KindIcon = cfg.icon;

  const spanStart = span.start_time ? new Date(span.start_time).getTime() - traceStart : 0;
  const spanDuration = span.duration_ms ?? 0;
  const leftPct  = totalDurationMs ? (spanStart / totalDurationMs) * 100 : 0;
  const widthPct = totalDurationMs ? Math.max((spanDuration / totalDurationMs) * 100, 0.5) : 0.5;
  const hasChildren = span.children && span.children.length > 0;

  return (
    <>
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr',
        gap: 0,
        borderBottom: `1px solid ${COLORS.border}`,
        minHeight: 36,
      }}>
        {/* Left: span name */}
        <div style={{
          display: 'flex', alignItems: 'center',
          paddingLeft: 12 + depth * 20,
          paddingRight: 12, paddingTop: 8, paddingBottom: 8,
          borderRight: `1px solid ${COLORS.border}`,
          gap: 8,
        }}>
          {hasChildren ? (
            <button onClick={() => setOpen(!open)} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: COLORS.muted }}>
              {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>
          ) : <span style={{ width: 14 }} />}

          <div style={{
            background: `${cfg.color}22`,
            borderRadius: 5,
            padding: '2px 6px',
            display: 'flex', alignItems: 'center', gap: 4,
          }}>
            <KindIcon size={11} color={cfg.color} />
            <span style={{ color: cfg.color, fontSize: 10, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
              {span.kind}
            </span>
          </div>

          <span style={{ color: span.status === 'ERROR' ? COLORS.error : COLORS.text, fontSize: 13, fontFamily: 'monospace' }}>
            {span.name}
          </span>

          {span.status === 'ERROR' && (
            <span style={{ background: '#E74C3C22', color: COLORS.error, borderRadius: 4, padding: '1px 5px', fontSize: 10 }}>
              ERR
            </span>
          )}
        </div>

        {/* Right: waterfall bar */}
        <div style={{ position: 'relative', padding: '8px 12px', display: 'flex', alignItems: 'center' }}>
          <div style={{ position: 'relative', width: '100%', height: 16, background: COLORS.border + '44', borderRadius: 3 }}>
            <div style={{
              position: 'absolute',
              left: `${Math.min(leftPct, 95)}%`,
              width: `${Math.min(widthPct, 100 - Math.min(leftPct, 95))}%`,
              height: '100%',
              background: cfg.color,
              borderRadius: 3,
              opacity: 0.85,
            }} />
          </div>
          <span style={{ color: COLORS.muted, fontSize: 11, marginLeft: 8, whiteSpace: 'nowrap', minWidth: 60 }}>
            {spanDuration < 1 ? '<1ms' : `${Math.round(spanDuration)}ms`}
          </span>
        </div>
      </div>

      {open && hasChildren && span.children?.map((child) => (
        <SpanRow
          key={child.span_id}
          span={child}
          depth={depth + 1}
          totalDurationMs={totalDurationMs}
          traceStart={traceStart}
        />
      ))}
    </>
  );
}

// ─── Build span tree ───────────────────────────────────────────────

function buildSpanTree(spans: Span[]): (Span & { children?: Span[] })[] {
  const map = new Map<string, Span & { children?: Span[] }>();
  spans.forEach((s) => map.set(s.span_id, { ...s, children: [] }));

  const roots: (Span & { children?: Span[] })[] = [];
  spans.forEach((s) => {
    const node = map.get(s.span_id)!;
    if (s.parent_span_id && map.has(s.parent_span_id)) {
      map.get(s.parent_span_id)!.children!.push(node);
    } else {
      roots.push(node);
    }
  });
  return roots;
}

// ─── Trace Row ─────────────────────────────────────────────────────

function TraceRow({ trace, onClick, selected }: { trace: Trace; onClick: () => void; selected: boolean }) {
  return (
    <div
      onClick={onClick}
      style={{
        display: 'grid',
        gridTemplateColumns: '1fr 80px 90px 70px 80px 80px',
        gap: 0,
        borderBottom: `1px solid ${COLORS.border}`,
        cursor: 'pointer',
        background: selected ? COLORS.primary + '18' : 'transparent',
        transition: 'background 0.1s',
      }}
      onMouseOver={(e) => { if (!selected) e.currentTarget.style.background = COLORS.border + '44'; }}
      onMouseOut={(e) => { e.currentTarget.style.background = selected ? COLORS.primary + '18' : 'transparent'; }}
    >
      <div style={{ padding: '10px 16px' }}>
        <div style={{ color: COLORS.text, fontSize: 13, fontWeight: 500 }}>{trace.agent_name}</div>
        <div style={{ color: COLORS.muted, fontSize: 11, marginTop: 2, fontFamily: 'monospace' }}>
          {trace.trace_id.slice(0, 8)}…
        </div>
      </div>
      <div style={{ padding: '10px 12px', display: 'flex', alignItems: 'center' }}>
        <span style={{
          background: trace.status === 'OK' ? '#00A89622' : '#E74C3C22',
          color:      trace.status === 'OK' ? COLORS.success : COLORS.error,
          borderRadius: 6, padding: '2px 8px', fontSize: 11, fontWeight: 600,
        }}>
          {trace.status}
        </span>
      </div>
      <div style={{ padding: '10px 12px', color: COLORS.muted, fontSize: 13, display: 'flex', alignItems: 'center' }}>
        {trace.duration_ms ? `${Math.round(trace.duration_ms)}ms` : '—'}
      </div>
      <div style={{ padding: '10px 12px', color: COLORS.muted, fontSize: 13, display: 'flex', alignItems: 'center' }}>
        {trace.total_spans}
      </div>
      <div style={{ padding: '10px 12px', color: COLORS.muted, fontSize: 13, display: 'flex', alignItems: 'center' }}>
        {trace.total_tokens.toLocaleString()}
      </div>
      <div style={{ padding: '10px 12px', color: COLORS.success, fontSize: 13, display: 'flex', alignItems: 'center' }}>
        ${trace.total_cost_usd.toFixed(5)}
      </div>
    </div>
  );
}

// ─── Main Traces Page ─────────────────────────────────────────────

export default function TracesPage() {
  const [search, setSearch]   = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');

  const { data: tracesData } = useTraces({ agentName: search || undefined, status: statusFilter || undefined });
  const { data: traceDetail } = useTrace(selectedId);

  const traceStart = traceDetail?.spans?.[0]?.start_time
    ? new Date(traceDetail.spans[0].start_time).getTime()
    : Date.now();
  const totalDurationMs = traceDetail?.trace?.duration_ms ?? 0;
  const spanTree = traceDetail?.spans ? buildSpanTree(traceDetail.spans) : [];

  return (
    <div style={{ display: 'flex', height: 'calc(100vh - 60px)', background: COLORS.bg, fontFamily: "'Inter', system-ui, sans-serif" }}>

      {/* ── Left: Trace List ──────────────────────────────────── */}
      <div style={{ flex: selectedId ? '0 0 50%' : '1', display: 'flex', flexDirection: 'column', borderRight: `1px solid ${COLORS.border}` }}>

        {/* Toolbar */}
        <div style={{ padding: '16px 20px', borderBottom: `1px solid ${COLORS.border}`, display: 'flex', gap: 10 }}>
          <div style={{ flex: 1, position: 'relative' }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', color: COLORS.muted }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Filter by agent name…"
              style={{
                width: '100%', paddingLeft: 32, paddingRight: 12,
                height: 36, background: COLORS.card, border: `1px solid ${COLORS.border}`,
                borderRadius: 8, color: COLORS.text, fontSize: 13, outline: 'none',
                boxSizing: 'border-box',
              }}
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            style={{
              height: 36, padding: '0 12px', background: COLORS.card, border: `1px solid ${COLORS.border}`,
              borderRadius: 8, color: COLORS.text, fontSize: 13, outline: 'none',
            }}
          >
            <option value="">All statuses</option>
            <option value="OK">OK</option>
            <option value="ERROR">ERROR</option>
          </select>
        </div>

        {/* Column headers */}
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 80px 90px 70px 80px 80px',
          borderBottom: `1px solid ${COLORS.border}`, background: COLORS.card,
        }}>
          {['Agent', 'Status', 'Duration', 'Spans', 'Tokens', 'Cost'].map((h) => (
            <div key={h} style={{ padding: '8px 12px', color: COLORS.muted, fontSize: 12, fontWeight: 600 }}>{h}</div>
          ))}
        </div>

        {/* Trace rows */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {tracesData?.traces?.map((trace) => (
            <TraceRow
              key={trace.trace_id}
              trace={trace}
              selected={selectedId === trace.trace_id}
              onClick={() => setSelectedId(selectedId === trace.trace_id ? null : trace.trace_id)}
            />
          ))}
          {(!tracesData?.traces || tracesData.traces.length === 0) && (
            <div style={{ padding: 48, textAlign: 'center', color: COLORS.muted, fontSize: 13 }}>
              No traces found. Check your filters or instrument your first agent.
            </div>
          )}
        </div>
      </div>

      {/* ── Right: Span Tree ─────────────────────────────────── */}
      {selectedId && (
        <div style={{ flex: '0 0 50%', display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
          {/* Detail Header */}
          <div style={{ padding: '16px 20px', borderBottom: `1px solid ${COLORS.border}`, background: COLORS.card }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
              <div>
                <h3 style={{ color: COLORS.text, margin: '0 0 4px', fontSize: 15, fontWeight: 600 }}>
                  {traceDetail?.trace?.agent_name ?? '…'}
                </h3>
                <code style={{ color: COLORS.muted, fontSize: 11 }}>{selectedId}</code>
              </div>
              <button onClick={() => setSelectedId(null)} style={{ background: 'none', border: 'none', color: COLORS.muted, cursor: 'pointer', fontSize: 18 }}>×</button>
            </div>
            <div style={{ display: 'flex', gap: 20, marginTop: 12 }}>
              {[
                ['Spans',     traceDetail?.spans?.length ?? '—'],
                ['Duration',  traceDetail?.trace?.duration_ms ? `${Math.round(traceDetail.trace.duration_ms)}ms` : '—'],
                ['Tokens',    (traceDetail?.trace?.total_tokens ?? 0).toLocaleString()],
                ['Cost',      `$${(traceDetail?.trace?.total_cost_usd ?? 0).toFixed(6)}`],
                ['Framework', traceDetail?.trace?.framework ?? '—'],
              ].map(([label, val]) => (
                <div key={label}>
                  <div style={{ color: COLORS.muted, fontSize: 11 }}>{label}</div>
                  <div style={{ color: COLORS.text, fontSize: 13, fontWeight: 600 }}>{val}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Waterfall header */}
          <div style={{
            display: 'grid', gridTemplateColumns: '1fr 1fr',
            borderBottom: `1px solid ${COLORS.border}`, background: COLORS.card,
          }}>
            <div style={{ padding: '8px 12px', color: COLORS.muted, fontSize: 12, fontWeight: 600, borderRight: `1px solid ${COLORS.border}` }}>SPAN</div>
            <div style={{ padding: '8px 12px', color: COLORS.muted, fontSize: 12, fontWeight: 600 }}>WATERFALL</div>
          </div>

          {/* Span tree */}
          <div style={{ flex: 1 }}>
            {spanTree.map((span) => (
              <SpanRow
                key={span.span_id}
                span={span}
                depth={0}
                totalDurationMs={totalDurationMs}
                traceStart={traceStart}
              />
            ))}
            {spanTree.length === 0 && (
              <div style={{ padding: 32, textAlign: 'center', color: COLORS.muted, fontSize: 13 }}>
                Loading spans…
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
