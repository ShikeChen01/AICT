/**
 * AICT Frontend Application
 * Main app with project-scoped routing, chat, kanban, and agent status.
 */

import { useState, useEffect } from 'react';
import {
  BrowserRouter,
  Routes,
  Route,
  NavLink,
  Navigate,
  useNavigate,
  useParams,
} from 'react-router-dom';
import { ChatView } from './components/Chat';
import { KanbanBoard } from './components/Kanban';
import { AgentsPanel } from './components/Agents';
import { getProjects, healthCheck, setAuthToken } from './api/client';
import type { Project } from './types';

// Set auth token SYNCHRONOUSLY before any component renders/fetches.
// Must run at module level so child useEffect hooks already have the token.
setAuthToken(import.meta.env.VITE_API_TOKEN || 'change-me-in-production');

type AppView = 'chat' | 'kanban';

interface SidebarProps {
  projects: Project[];
  activeProjectId: string;
  activeView: AppView;
  onProjectChange: (projectId: string) => void;
}

function Sidebar({ projects, activeProjectId, activeView, onProjectChange }: SidebarProps) {
  const chatPath = activeProjectId ? `/project/${activeProjectId}/chat` : '/';
  const kanbanPath = activeProjectId ? `/project/${activeProjectId}/kanban` : '/';

  return (
    <aside className="w-64 bg-gray-900 text-white flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-gray-800">
        <h1 className="text-2xl font-bold">AICT</h1>
        <p className="text-sm text-gray-400">Multi-Agent Platform</p>
      </div>

      {/* Project selector */}
      <div className="p-4 border-b border-gray-800">
        <label htmlFor="project-selector" className="block text-xs uppercase tracking-wide text-gray-400 mb-2">
          Project
        </label>
        <select
          id="project-selector"
          value={activeProjectId}
          onChange={(e) => onProjectChange(e.target.value)}
          className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4">
        <ul className="space-y-2">
          <li>
            <NavLink
              to={chatPath}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive || activeView === 'chat'
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                }`
              }
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                />
              </svg>
              Chat with GM
            </NavLink>
          </li>
          <li>
            <NavLink
              to={kanbanPath}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive || activeView === 'kanban'
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                }`
              }
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2"
                />
              </svg>
              Kanban Board
            </NavLink>
          </li>
        </ul>
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-gray-800">
        <div className="flex items-center gap-3 text-sm text-gray-400">
          <div className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
              />
            </svg>
          </div>
          <div>
            <p className="text-white font-medium">User</p>
            <p className="text-xs">MVP-0</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

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

function LegacyRouteRedirect({
  projects,
  view,
  isLoading,
}: {
  projects: Project[];
  view: AppView;
  isLoading: boolean;
}) {
  if (isLoading) {
    return (
      <div className="h-screen flex items-center justify-center text-gray-600">
        Loading projects...
      </div>
    );
  }
  if (projects.length === 0) {
    return (
      <div className="h-screen flex items-center justify-center text-gray-600">
        No projects available.
      </div>
    );
  }
  return <Navigate to={`/project/${projects[0].id}/${view}`} replace />;
}

function ProjectPage({
  projects,
  view,
}: {
  projects: Project[];
  view: AppView;
}) {
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();

  const activeProject =
    (projectId && projects.find((project) => project.id === projectId)) || null;

  useEffect(() => {
    if (projects.length === 0) return;
    if (!projectId || !activeProject) {
      navigate(`/project/${projects[0].id}/${view}`, { replace: true });
    }
  }, [activeProject, navigate, projectId, projects, view]);

  if (projects.length === 0) {
    return (
      <div className="h-screen flex items-center justify-center text-gray-600">
        No projects available.
      </div>
    );
  }

  const resolvedProject = activeProject ?? projects[0];

  return (
    <div className="flex h-screen bg-gray-100">
      <Sidebar
        projects={projects}
        activeProjectId={resolvedProject.id}
        activeView={view}
        onProjectChange={(nextProjectId) => navigate(`/project/${nextProjectId}/${view}`)}
      />
      <main className="flex-1 overflow-hidden">
        {view === 'chat' ? (
          <ChatView projectId={resolvedProject.id} />
        ) : (
          <KanbanBoard projectId={resolvedProject.id} />
        )}
      </main>
      <AgentsPanel projectId={resolvedProject.id} />
    </div>
  );
}

function App() {
  const [isBackendConnected, setIsBackendConnected] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [isProjectsLoading, setIsProjectsLoading] = useState(false);
  const [projectsError, setProjectsError] = useState<string | null>(null);

  // Token is set synchronously at module level above (before any component renders).

  useEffect(() => {
    const loadProjects = async () => {
      setIsProjectsLoading(true);
      setProjectsError(null);
      try {
        const nextProjects = await getProjects();
        setProjects(nextProjects);
      } catch (error) {
        const message =
          error instanceof Error ? error.message : 'Failed to load projects';
        setProjectsError(message);
      } finally {
        setIsProjectsLoading(false);
      }
    };
    void loadProjects();
  }, []);

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
        <Route
          path="/"
          element={
            <LegacyRouteRedirect
              projects={projects}
              view="chat"
              isLoading={isProjectsLoading}
            />
          }
        />
        <Route
          path="/chat"
          element={
            <LegacyRouteRedirect
              projects={projects}
              view="chat"
              isLoading={isProjectsLoading}
            />
          }
        />
        <Route
          path="/kanban"
          element={
            <LegacyRouteRedirect
              projects={projects}
              view="kanban"
              isLoading={isProjectsLoading}
            />
          }
        />
        <Route path="/project/:projectId/chat" element={<ProjectPage projects={projects} view="chat" />} />
        <Route path="/project/:projectId/kanban" element={<ProjectPage projects={projects} view="kanban" />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <ConnectionStatus isConnected={isBackendConnected} />
    </BrowserRouter>
  );
}

export default App;
