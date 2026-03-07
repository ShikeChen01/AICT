/**
 * AICT Frontend Application
 * Main app with project-scoped routing, chat, kanban, and agent status.
 */

import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import {
  AgentBuildPage,
  AuthCallbackPage,
  BackendLogsPage,
  DashboardPage,
  LoginPage,
  ProjectsPage,
  RegisterPage,
  SettingsPage,
  TestLoginPage,
  UserSettingsPage,
  WorkspacePage,
} from './pages';
import { getAuthToken, healthCheck } from './api/client';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ProjectProvider, useProjectContext } from './contexts/ProjectContext';
import { ThemeProvider } from './contexts/ThemeContext';

function ProtectedRoute() {
  const { firebaseUser, user, loading } = useAuth();
  const hasToken = Boolean(getAuthToken());
  if (loading) {
    return <div className="h-screen flex items-center justify-center text-[var(--text-muted)]">Loading...</div>;
  }
  if (!firebaseUser && !user && !hasToken) {
    return <Navigate to="/login" replace />;
  }
  return <Outlet />;
}

function AppShell() {
  const { firebaseUser, user, loading } = useAuth();
  const [isBackendConnected, setIsBackendConnected] = useState(true);
  const { projects, loading: isProjectsLoading, error: projectsError, refreshProjects } = useProjectContext();

  useEffect(() => {
    if (loading || (!firebaseUser && !user)) return;
    if (!getAuthToken()) return;
    void refreshProjects();
  }, [firebaseUser, user, loading, refreshProjects]);

  useEffect(() => {
    const checkConnection = async () => {
      try {
        await healthCheck();
        setIsBackendConnected(true);
      } catch {
        setIsBackendConnected(false);
      }
    };

    checkConnection();
    const interval = setInterval(checkConnection, 30000); // Check every 30s

    return () => clearInterval(interval);
  }, []);

  return (
    <BrowserRouter>
      {projectsError && (
        <div className="fixed left-0 right-0 top-0 z-50 border-b border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] px-4 py-2 text-center text-sm text-[var(--color-danger)]">
          {projectsError}
        </div>
      )}
      {!isBackendConnected && (
        <div className="fixed left-0 right-0 top-0 z-50 border-b border-[var(--color-warning)]/30 bg-[var(--color-warning-light)] px-4 py-2 text-center text-sm text-[var(--color-warning)]">
          Backend health check failed. Reconnecting...
        </div>
      )}

      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route path="/test-login" element={<TestLoginPage />} />

        <Route element={<ProtectedRoute />}>
          <Route path="/projects" element={<ProjectsPage onProjectsUpdated={refreshProjects} />} />
          <Route path="/settings" element={<UserSettingsPage />} />
          <Route path="/project/:projectId/settings" element={<SettingsPage />} />

          <Route
            path="/"
            element={
              isProjectsLoading ? (
                <div className="h-screen flex items-center justify-center text-[var(--text-muted)]">
                  Loading...
                </div>
              ) : projects.length === 0 ? (
                <Navigate to="/projects" replace />
              ) : (
                <Navigate to={`/project/${projects[0].id}/workspace`} replace />
              )
            }
          />
          <Route path="/project/:projectId/workspace" element={<WorkspacePage view="workspace" />} />
          <Route path="/project/:projectId/dashboard" element={<DashboardPage />} />
          <Route path="/project/:projectId/kanban" element={<WorkspacePage view="kanban" />} />
          <Route path="/project/:projectId/agent-build" element={<AgentBuildPage />} />
          <Route path="/project/:projectId/logs" element={<BackendLogsPage />} />

          {/* Backward-compatible redirects */}
          <Route path="/repositories" element={<Navigate to="/projects" replace />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

    </BrowserRouter>
  );
}

function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <ProjectProvider>
          <AppShell />
        </ProjectProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}

export default App;
