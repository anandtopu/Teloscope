/**
 * AgentLens — API Client & React Query Hooks
 * Typed fetch helpers for all backend endpoints.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useAppStore } from '../store';

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

// ─── Fetch Helper ─────────────────────────────────────────────────────────────

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const apiKey = useAppStore.getState().apiKey;
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': apiKey,
      ...init?.headers,
    },
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API ${res.status}: ${err}`);
  }
  return res.json() as Promise<T>;
}

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Trace {
  trace_id:        string;
  name:            string;
  agent_name:      string;
  framework:       string;
  environment:     string;
  start_time:      string;
  end_time:        string | null;
  duration_ms:     number | null;
  status:          'OK' | 'ERROR' | 'UNSET';
  total_spans:     number;
  llm_call_count:  number;
  tool_call_count: number;
  error_count:     number;
  total_tokens:    number;
  total_cost_usd:  number;
}

export interface Span {
  span_id:        string;
  trace_id:       string;
  parent_span_id: string | null;
  name:           string;
  kind:           string;
  status:         string;
  start_time:     string;
  end_time:       string | null;
  duration_ms:    number | null;
  llm_model:      string | null;
  llm_provider:   string | null;
  prompt_tokens:  number;
  completion_tokens: number;
  cost_usd:       number;
  error:          string | null;
  input_json:     string | null;
  output_json:    string | null;
}

export interface MetricsSummary {
  invocation_count:  number;
  success_count:     number;
  error_count:       number;
  error_rate:        number;
  avg_latency_ms:    number;
  p50_latency_ms:    number;
  p95_latency_ms:    number;
  p99_latency_ms:    number;
  total_tokens:      number;
  total_cost_usd:    number;
  avg_cost_per_call: number;
}

export interface AlertRule {
  rule_id:        string;
  name:           string;
  severity:       string;
  metric:         string;
  operator:       string;
  threshold:      number;
  window_minutes: number;
  enabled:        boolean;
}

export interface EvalResult {
  eval_id:         string;
  trace_id:        string;
  judge_model:     string;
  overall_score:   number | null;
  overall_verdict: string;
  dimensions:      { name: string; score: number; verdict: string; reasoning: string }[];
  cost_usd:        number;
  evaluated_at:    string;
}

// ─── Hooks: Traces ────────────────────────────────────────────────────────────

export function useTraces(filters: {
  agentName?:  string;
  status?:     string;
  environment?: string;
  limit?:      number;
  offset?:     number;
} = {}) {
  const { project, timeRange } = useAppStore();
  const params = new URLSearchParams({
    org_id:     project.orgId,
    project_id: project.projectId,
    limit:      String(filters.limit ?? 50),
    offset:     String(filters.offset ?? 0),
  });
  if (filters.agentName)   params.set('agent_name',  filters.agentName);
  if (filters.status)      params.set('status',       filters.status);
  if (filters.environment) params.set('environment',  filters.environment);

  return useQuery({
    queryKey: ['traces', project, filters, timeRange],
    queryFn:  () => apiFetch<{ traces: Trace[]; total: number }>(`/api/v1/traces?${params}`),
    refetchInterval: 15_000,
  });
}

export function useTrace(traceId: string | null) {
  const { project } = useAppStore();
  return useQuery({
    queryKey:  ['trace', traceId],
    queryFn:   () => apiFetch<{ trace: Trace; spans: Span[] }>(
      `/api/v1/traces/${traceId}?org_id=${project.orgId}`
    ),
    enabled: !!traceId,
  });
}

// ─── Hooks: Metrics ───────────────────────────────────────────────────────────

export function useMetricsSummary(agentName?: string) {
  const { project, timeRange } = useAppStore();
  const params = new URLSearchParams({
    org_id:         project.orgId,
    project_id:     project.projectId,
    window_minutes: String(timeRange.minutes),
  });
  if (agentName) params.set('agent_name', agentName);

  return useQuery({
    queryKey:        ['metrics-summary', project, timeRange, agentName],
    queryFn:         () => apiFetch<{ metrics: MetricsSummary }>(`/api/v1/metrics/summary?${params}`),
    refetchInterval: 10_000,
  });
}

export function useCostBreakdown() {
  const { project, timeRange } = useAppStore();
  const params = new URLSearchParams({
    org_id:         project.orgId,
    project_id:     project.projectId,
    window_minutes: String(timeRange.minutes),
  });

  return useQuery({
    queryKey: ['cost-breakdown', project, timeRange],
    queryFn:  () => apiFetch<{ breakdown: { provider: string; model: string; call_count: number; cost_usd: number }[] }>(
      `/api/v1/metrics/cost?${params}`
    ),
    refetchInterval: 30_000,
  });
}

export function useErrorBreakdown() {
  const { project, timeRange } = useAppStore();
  const params = new URLSearchParams({
    org_id:         project.orgId,
    project_id:     project.projectId,
    window_minutes: String(timeRange.minutes),
  });

  return useQuery({
    queryKey: ['error-breakdown', project, timeRange],
    queryFn:  () => apiFetch<{ errors: { error_type: string; count: number; pct: number }[] }>(
      `/api/v1/metrics/errors?${params}`
    ),
  });
}

// ─── Hooks: Alerts ────────────────────────────────────────────────────────────

export function useAlerts(resolved?: boolean) {
  const { project } = useAppStore();
  const params = new URLSearchParams({ org_id: project.orgId });
  if (resolved !== undefined) params.set('resolved', String(resolved));

  return useQuery({
    queryKey:        ['alerts', project, resolved],
    queryFn:         () => apiFetch<{ alerts: AlertRule[] }>(`/api/v1/alerts?${params}`),
    refetchInterval: 10_000,
  });
}

export function useAlertRules() {
  const { project } = useAppStore();
  const params = new URLSearchParams({
    org_id:     project.orgId,
    project_id: project.projectId,
  });

  return useQuery({
    queryKey: ['alert-rules', project],
    queryFn:  () => apiFetch<{ rules: AlertRule[] }>(`/api/v1/alerts/rules?${params}`),
  });
}

// ─── Hooks: Evaluations ───────────────────────────────────────────────────────

export function useEvaluations(traceId?: string) {
  const { project } = useAppStore();
  const params = new URLSearchParams({
    org_id:     project.orgId,
    project_id: project.projectId,
  });
  if (traceId) params.set('trace_id', traceId);

  return useQuery({
    queryKey: ['evaluations', project, traceId],
    queryFn:  () => apiFetch<{ evaluations: EvalResult[] }>(`/api/v1/evaluations?${params}`),
  });
}

export function useRunEvaluation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: {
      trace_id:    string;
      org_id:      string;
      project_id:  string;
      dimensions?: string[];
      judge_model?: string;
    }) => apiFetch<EvalResult>('/api/v1/evaluations/run', {
      method: 'POST',
      body:   JSON.stringify(req),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['evaluations'] });
    },
  });
}
