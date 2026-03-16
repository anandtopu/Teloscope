/**
 * AgentLens — Global State Store (Zustand)
 * Manages auth, selected project, time range, and live metrics.
 */
import { create } from 'zustand';
import { devtools, persist } from 'zustand/middleware';

// ─── Types ────────────────────────────────────────────────────────────────────

export interface Project {
  orgId:     string;
  projectId: string;
  name:      string;
}

export interface TimeRange {
  label:   string;
  minutes: number;
}

export const TIME_RANGES: TimeRange[] = [
  { label: '15m',  minutes: 15   },
  { label: '1h',   minutes: 60   },
  { label: '6h',   minutes: 360  },
  { label: '24h',  minutes: 1440 },
  { label: '7d',   minutes: 10080},
];

export interface MetricsSummary {
  invocationCount:   number;
  successCount:      number;
  errorCount:        number;
  errorRate:         number;
  avgLatencyMs:      number;
  p50LatencyMs:      number;
  p95LatencyMs:      number;
  p99LatencyMs:      number;
  totalTokens:       number;
  totalCostUsd:      number;
  avgCostPerCall:    number;
}

export interface Alert {
  alertId:      string;
  ruleId:       string;
  severity:     'info' | 'warning' | 'error' | 'critical';
  title:        string;
  description:  string;
  metric:       string;
  currentValue: number;
  threshold:    number;
  agentName:    string | null;
  firedAt:      string;
  resolvedAt:   string | null;
  acknowledged: boolean;
}

// ─── Store ────────────────────────────────────────────────────────────────────

interface AppState {
  // Auth
  apiKey:     string;
  setApiKey:  (key: string) => void;

  // Project context
  project:    Project;
  setProject: (p: Project) => void;

  // Time range
  timeRange:    TimeRange;
  setTimeRange: (tr: TimeRange) => void;

  // Live metrics
  metrics:      MetricsSummary | null;
  setMetrics:   (m: MetricsSummary) => void;

  // Active alerts (live count for badge)
  activeAlerts:    Alert[];
  setActiveAlerts: (a: Alert[]) => void;

  // UI state
  sidebarOpen:    boolean;
  setSidebarOpen: (v: boolean) => void;

  // Selected trace (for detail panel)
  selectedTraceId:    string | null;
  setSelectedTraceId: (id: string | null) => void;
}

export const useAppStore = create<AppState>()(
  devtools(
    persist(
      (set) => ({
        apiKey:    '',
        setApiKey: (apiKey) => set({ apiKey }),

        project: {
          orgId:     'default',
          projectId: 'default',
          name:      'Default Project',
        },
        setProject: (project) => set({ project }),

        timeRange:    TIME_RANGES[1],  // default 1h
        setTimeRange: (timeRange) => set({ timeRange }),

        metrics:    null,
        setMetrics: (metrics) => set({ metrics }),

        activeAlerts:    [],
        setActiveAlerts: (activeAlerts) => set({ activeAlerts }),

        sidebarOpen:    true,
        setSidebarOpen: (sidebarOpen) => set({ sidebarOpen }),

        selectedTraceId:    null,
        setSelectedTraceId: (selectedTraceId) => set({ selectedTraceId }),
      }),
      {
        name: 'agentlens-store',
        partialize: (state) => ({
          apiKey:   state.apiKey,
          project:  state.project,
          timeRange: state.timeRange,
        }),
      },
    ),
  ),
);
