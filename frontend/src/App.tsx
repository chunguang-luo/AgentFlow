import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';

import { AuthProvider, useAuth } from './auth';
import { AppShell } from './components/AppShell';
import { AuditPage } from './pages/AuditPage';
import { FlowEditorPage } from './pages/FlowEditorPage';
import { FlowsPage } from './pages/FlowsPage';
import { LoginPage } from './pages/LoginPage';
import { ProvidersPage } from './pages/ProvidersPage';
import { RunDetailPage } from './pages/RunDetailPage';
import { RunsPage } from './pages/RunsPage';

function AppRoutes() {
  const { state } = useAuth();

  if (state.phase === 'loading') {
    return <div className="boot-screen">Loading AgentFlow</div>;
  }

  if (state.phase === 'anonymous') {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route path="/login" element={<Navigate to="/flows" replace />} />
      <Route element={<AppShell />}>
        <Route path="/" element={<Navigate to="/flows" replace />} />
        <Route path="/flows" element={<FlowsPage />} />
        <Route path="/flows/new" element={<FlowEditorPage />} />
        <Route path="/flows/:flowId/edit" element={<FlowEditorPage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunDetailPage />} />
        <Route path="/providers" element={<ProvidersPage />} />
        <Route path="/settings/providers" element={<ProvidersPage />} />
        <Route path="/audit" element={<AuditPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/flows" replace />} />
    </Routes>
  );
}

export function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
