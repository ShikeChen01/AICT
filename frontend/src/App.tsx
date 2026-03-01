/**
 * AICT Frontend Application
 * Main app with project-scoped routing, chat, kanban, and agent status.
 */

import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import {
  AuthCallbackPage,
  BackendLogsPage,
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

function ProtectedRoute() {
  const { firebaseUser, user, loading } = useAuth();
  const hasToken = Boolean(getAuthToken());
  if (loading) {
    return <div className="h-screen flex items-center justify-center text-gray-600">Loading...</div>;
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
        <div className="fixed left-0 right-0 top-0 z-50 border-b border-red-200 bg-red-50 px-4 py-2 text-center text-sm text-red-700">
          {projectsError}
        </div>
      )}
      {!isBackendConnected && (
        <div className="fixed left-0 right-0 top-0 z-50 border-b border-amber-200 bg-amber-50 px-4 py-2 text-center text-sm text-amber-800">
          Backend health check failed. Reconnecting...
        </div>
      )}

      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />
        <Route path="/test-login" element={<TestLoginPage />} />

        <Route element={<ProtectedRoute />}>
          <Route path="/repositories" element={<ProjectsPage onProjectsUpdated={refreshProjects} />} />
          <Route path="/settings" element={<UserSettingsPage />} />
          <Route path="/repository/:projectId/settings" element={<SettingsPage />} />

          <Route
            path="/"
            element={
              isProjectsLoading ? (
                <div className="h-screen flex items-center justify-center text-gray-600">
                  Loading...
                </div>
              ) : projects.length === 0 ? (
                <Navigate to="/repositories" replace />
              ) : (
                <Navigate to={`/repository/${projects[0].id}/workspace`} replace />
              )
            }
          />
          <Route path="/repository/:projectId/workspace" element={<WorkspacePage view="workspace" />} />
          <Route path="/repository/:projectId/kanban" element={<WorkspacePage view="kanban" />} />
          <Route path="/repository/:projectId/workflow" element={<WorkspacePage view="workflow" />} />
          <Route path="/repository/:projectId/artifacts" element={<WorkspacePage view="artifacts" />} />
          <Route path="/repository/:projectId/backend-logs" element={<BackendLogsPage />} />
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

    </BrowserRouter>
  );
}

function App() {
  return (
    <AuthProvider>
      <ProjectProvider>
        <AppShell />
      </ProjectProvider>
    </AuthProvider>
  );
}

export default App;
