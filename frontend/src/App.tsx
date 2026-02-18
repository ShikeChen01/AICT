/**
 * AICT Frontend Application
 * Main app with project-scoped routing, chat, kanban, and agent status.
 */

import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { AuthCallbackPage, LoginPage, ProjectsPage, RegisterPage, SettingsPage, UserSettingsPage, WorkspacePage } from './pages';
import { getAuthToken, healthCheck } from './api/client';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { ProjectProvider, useProjectContext } from './contexts/ProjectContext';

function ConnectionStatus({ isConnected }: { isConnected: boolean }) {
  return (
    <div
      className={`fixed bottom-4 right-4 flex items-center gap-2 px-3 py-2 rounded-full text-sm font-medium ${
        isConnected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
      }`}
    >
      <div
        className={`w-2 h-2 rounded-full ${
          isConnected ? 'bg-green-500' : 'bg-red-500 animate-pulse'
        }`}
      />
      {isConnected ? 'Connected' : 'Connecting...'}
    </div>
  );
}

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
  const [isBackendConnected, setIsBackendConnected] = useState(false);
  const { projects, loading: isProjectsLoading, error: projectsError, refreshProjects } = useProjectContext();

  useEffect(() => {
    if (loading || (!firebaseUser && !user)) return;
    if (!getAuthToken()) return;
    void refreshProjects();
  }, [firebaseUser, user, loading, refreshProjects]);

  // Check backend connection
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
        <div className="fixed top-0 left-0 right-0 z-50 bg-red-50 border-b border-red-200 px-4 py-2 text-sm text-red-700 text-center">
          {projectsError}
        </div>
      )}

      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/register" element={<RegisterPage />} />
        <Route path="/auth/callback" element={<AuthCallbackPage />} />

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
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <ConnectionStatus isConnected={isBackendConnected} />
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
