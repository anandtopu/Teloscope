/**
 * AgentLens — Root App Component
 * Sidebar navigation + page routing.
 */
import React, { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, NavLink, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import {
  LayoutDashboard, Activity, Bell, FlaskConical,
  Settings, ChevronLeft, Zap, AlertCircle,
} from 'lucide-react';
import { useAppStore } from './store';

const DashboardPage  = lazy(() => import('./pages/Dashboard'));
const TracesPage     = lazy(() => import('./pages/Traces'));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, staleTime: 5_000 },
  },
});

const C = {
  bg:       '#0F1117',
  sidebar:  '#13151F',
  card:     '#1A1D27',
  border:   '#2A2D3A',
  text:     '#E2E8F0',
  muted:    '#718096',
  primary:  '#0D7EC4',
  accent:   '#00A896',
};

const NAV_ITEMS = [
  { path: '/',            label: 'Overview',    icon: LayoutDashboard },
  { path: '/traces',      label: 'Traces',      icon: Activity       },
  { path: '/alerts',      label: 'Alerts',      icon: Bell           },
  { path: '/evaluations', label: 'Evaluations', icon: FlaskConical   },
  { path: '/settings',    label: 'Settings',    icon: Settings       },
];

function Sidebar() {
  const { sidebarOpen, setSidebarOpen } = useAppStore();
  const w = sidebarOpen ? 220 : 60;

  return (
    <aside style={{
      width: w, minWidth: w, height: '100vh',
      background: C.sidebar, borderRight: `1px solid ${C.border}`,
      display: 'flex', flexDirection: 'column',
      transition: 'width 0.2s ease',
      position: 'fixed', left: 0, top: 0, zIndex: 100,
    }}>
      {/* Logo */}
      <div style={{
        height: 60, display: 'flex', alignItems: 'center',
        padding: sidebarOpen ? '0 20px' : '0', justifyContent: sidebarOpen ? 'flex-start' : 'center',
        borderBottom: `1px solid ${C.border}`, gap: 10,
      }}>
        <div style={{
          background: 'linear-gradient(135deg, #0D7EC4, #00A896)',
          borderRadius: 8, padding: '6px 8px', display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <Zap size={16} color="#fff" />
        </div>
        {sidebarOpen && (
          <span style={{ color: C.text, fontSize: 16, fontWeight: 700, letterSpacing: '-0.3px' }}>
            Agent<span style={{ color: C.primary }}>Lens</span>
          </span>
        )}
      </div>

      {/* Nav items */}
      <nav style={{ flex: 1, padding: '12px 8px', display: 'flex', flexDirection: 'column', gap: 2 }}>
        {NAV_ITEMS.map(({ path, label, icon: Icon }) => (
          <NavLink
            key={path}
            to={path}
            end={path === '/'}
            style={({ isActive }) => ({
              display: 'flex', alignItems: 'center',
              gap: 12, padding: '9px 12px', borderRadius: 8,
              textDecoration: 'none',
              background:  isActive ? `${C.primary}22` : 'transparent',
              color:       isActive ? C.primary : C.muted,
              fontWeight:  isActive ? 600 : 400,
              fontSize: 14,
              transition: 'all 0.1s',
              justifyContent: sidebarOpen ? 'flex-start' : 'center',
            })}
            title={!sidebarOpen ? label : undefined}
          >
            <Icon size={17} />
            {sidebarOpen && <span>{label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* Collapse button */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        style={{
          margin: 12, padding: '8px', borderRadius: 8,
          background: 'transparent', border: `1px solid ${C.border}`,
          color: C.muted, cursor: 'pointer', display: 'flex',
          alignItems: 'center', justifyContent: 'center',
        }}
        title={sidebarOpen ? 'Collapse sidebar' : 'Expand sidebar'}
      >
        <ChevronLeft size={15} style={{ transform: sidebarOpen ? 'none' : 'rotate(180deg)', transition: 'transform 0.2s' }} />
      </button>
    </aside>
  );
}

function TopBar() {
  const location = useLocation();
  const routeName = NAV_ITEMS.find((n) => n.path === location.pathname)?.label ?? 'AgentLens';
  const { project } = useAppStore();

  return (
    <header style={{
      height: 60, background: C.sidebar, borderBottom: `1px solid ${C.border}`,
      display: 'flex', alignItems: 'center', padding: '0 24px',
      justifyContent: 'space-between',
    }}>
      <div style={{ color: C.text, fontSize: 15, fontWeight: 600 }}>{routeName}</div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
        <div style={{ color: C.muted, fontSize: 13 }}>
          {project.name}
        </div>
        <div style={{
          width: 30, height: 30, borderRadius: '50%',
          background: 'linear-gradient(135deg, #0D7EC4, #00A896)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontSize: 12, fontWeight: 700,
        }}>
          AL
        </div>
      </div>
    </header>
  );
}

function PlaceholderPage({ title }: { title: string }) {
  return (
    <div style={{ padding: 48, textAlign: 'center', color: C.muted, fontFamily: 'Inter, system-ui' }}>
      <AlertCircle size={36} style={{ marginBottom: 16 }} />
      <div style={{ fontSize: 18, color: C.text, fontWeight: 600, marginBottom: 8 }}>{title}</div>
      <div style={{ fontSize: 14 }}>Coming in Phase 2 — see roadmap for details.</div>
    </div>
  );
}

function AppShell() {
  const { sidebarOpen } = useAppStore();
  const sidebarWidth = sidebarOpen ? 220 : 60;

  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: C.bg, fontFamily: "'Inter', system-ui, sans-serif" }}>
      <Sidebar />
      <div style={{ flex: 1, marginLeft: sidebarWidth, display: 'flex', flexDirection: 'column', transition: 'margin-left 0.2s ease' }}>
        <TopBar />
        <main style={{ flex: 1, overflowY: 'auto' }}>
          <Suspense fallback={
            <div style={{ padding: 48, textAlign: 'center', color: C.muted }}>Loading…</div>
          }>
            <Routes>
              <Route path="/"            element={<DashboardPage />} />
              <Route path="/traces"      element={<TracesPage />} />
              <Route path="/alerts"      element={<PlaceholderPage title="Alerts & Rules" />} />
              <Route path="/evaluations" element={<PlaceholderPage title="Evaluations" />} />
              <Route path="/settings"    element={<PlaceholderPage title="Settings" />} />
            </Routes>
          </Suspense>
        </main>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AppShell />
      </BrowserRouter>
    </QueryClientProvider>
  );
}
