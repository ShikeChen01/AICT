/**
 * AICT Frontend Application
 * Main app with project-scoped routing, chat, kanban, and agent status.
 */

import { useState, useEffect, useCallback } from 'react';
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
import { AgentInspector, AgentsPanel } from './components/Agents';
import { WorkflowGraph } from './components/Workflow';
import { ActivityFeed } from './components/ActivityFeed';
import { ArtifactBrowser } from './components/Artifacts';
import { ProjectsPage, SettingsPage } from './pages';
import { getProjects, healthCheck, setAuthToken } from './api/client';
import { useAgents, useWebSocket } from './hooks';
import type {
  AgentLogData,
  AgentRole,
  Project,
  SandboxLogData,
  WorkflowUpdateData,
} from './types';

// Set auth token SYNCHRONOUSLY before any component renders/fetches.
// Must run at module level so child useEffect hooks already have the token.
setAuthToken(import.meta.env.VITE_API_TOKEN || 'change-me-in-production');

type AppView = 'chat' | 'kanban' | 'workflow' | 'artifacts';

interface SidebarProps {
  projects: Project[];
  activeProjectId: string;
  activeView: AppView;
  onProjectChange: (projectId: string) => void;
}

function Sidebar({ projects, activeProjectId, activeView, onProjectChange }: SidebarProps) {
  const chatPath = activeProjectId ? `/project/${activeProjectId}/chat` : '/';
  const kanbanPath = activeProjectId ? `/project/${activeProjectId}/kanban` : '/';
  const workflowPath = activeProjectId ? `/project/${activeProjectId}/workflow` : '/';
  const artifactsPath = activeProjectId ? `/project/${activeProjectId}/artifacts` : '/';

  return (
    <aside className="w-64 bg-gray-900 text-white flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-gray-800">
        <NavLink to="/projects" className="group block">
          <h1 className="text-2xl font-bold group-hover:text-blue-300 transition-colors">AICT</h1>
          <p className="text-sm text-gray-400 group-hover:text-gray-300 transition-colors">
            Multi-Agent Platform
          </p>
        </NavLink>
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
          <li>
            <NavLink
              to={workflowPath}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive || activeView === 'workflow'
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
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
              Workflow
            </NavLink>
          </li>
          <li>
            <NavLink
              to={artifactsPath}
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive || activeView === 'artifacts'
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
                  d="M3 7h5l2 2h11v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7z"
                />
              </svg>
              Artifacts
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
  isProjectsLoading,
}: {
  projects: Project[];
  view: AppView;
  isProjectsLoading: boolean;
}) {
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();

  const activeProject =
    (projectId && projects.find((project) => project.id === projectId)) || null;

  useEffect(() => {
    if (isProjectsLoading) return;
    if (projects.length === 0) {
      navigate('/projects', { replace: true });
      return;
    }
    if (!projectId || !activeProject) {
      navigate(`/project/${projects[0].id}/${view}`, { replace: true });
    }
  }, [activeProject, isProjectsLoading, navigate, projectId, projects, view]);

  if (projects.length === 0) {
    return (
      <div className="h-screen flex items-center justify-center text-gray-600">
        No projects available.
      </div>
    );
  }

  const resolvedProject = activeProject ?? projects[0];
  const { agents } = useAgents(view === 'workflow' ? resolvedProject.id : null);
  const { subscribe } = useWebSocket(view === 'workflow' ? resolvedProject.id : null);
  const [activityLogs, setActivityLogs] = useState<
    (AgentLogData & { timestamp: string; id: string })[]
  >([]);
  const [workflowUpdate, setWorkflowUpdate] = useState<WorkflowUpdateData | null>(null);
  const [selectedInspectorAgentId, setSelectedInspectorAgentId] = useState<string | null>(null);

  useEffect(() => {
    setActivityLogs([]);
    setWorkflowUpdate(null);
    setSelectedInspectorAgentId(null);
  }, [resolvedProject.id, view]);

  useEffect(() => {
    if (view !== 'workflow') return;

    const unsubscribeWorkflow = subscribe<WorkflowUpdateData>('workflow_update', (data) => {
      setWorkflowUpdate(data);
    });

    const unsubscribeAgentLog = subscribe<AgentLogData>('agent_log', (data) => {
      const next = {
        ...data,
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        timestamp: new Date().toISOString(),
      };
      setActivityLogs((prev) => [...prev.slice(-199), next]);
    });

    const unsubscribeSandboxLog = subscribe<SandboxLogData>('sandbox_log', (data) => {
      const role = (agents.find((agent) => agent.id === data.agent_id)?.role ??
        'engineer') as AgentRole;
      const next: AgentLogData & { timestamp: string; id: string } = {
        project_id: data.project_id,
        agent_id: data.agent_id,
        agent_role: role,
        log_type: 'message',
        content: `[${data.stream}] ${data.content}`,
        id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
        timestamp: new Date().toISOString(),
      };
      setActivityLogs((prev) => [...prev.slice(-199), next]);
    });

    return () => {
      unsubscribeWorkflow();
      unsubscribeAgentLog();
      unsubscribeSandboxLog();
    };
  }, [agents, subscribe, view]);

  useEffect(() => {
    if (view !== 'workflow' || selectedInspectorAgentId || agents.length === 0) return;
    const defaultAgent =
      agents.find((agent) => agent.role === 'manager') ||
      agents.find((agent) => agent.role === 'om') ||
      agents[0];
    if (defaultAgent) {
      setSelectedInspectorAgentId(defaultAgent.id);
    }
  }, [agents, selectedInspectorAgentId, view]);

  const handleWorkflowNodeClick = (nodeId: string) => {
    const roleMap: Record<string, AgentRole | null> = {
      manager: 'manager',
      om: 'om',
      engineer: 'engineer',
      manager_tools: null,
      om_tools: null,
      engineer_tools: null,
      end: null,
    };
    const role = roleMap[nodeId];
    if (!role) return;
    const matchedAgent = agents.find((agent) => agent.role === role);
    if (matchedAgent) {
      setSelectedInspectorAgentId(matchedAgent.id);
    }
  };

  const renderView = () => {
    switch (view) {
      case 'chat':
        return <ChatView projectId={resolvedProject.id} />;
      case 'kanban':
        return <KanbanBoard projectId={resolvedProject.id} />;
      case 'workflow':
        return (
          <div className="flex h-full">
            <div className="flex-1 p-4">
              <div className="bg-white rounded-lg border border-gray-200 h-full">
                <div className="px-4 py-3 border-b border-gray-200">
                  <h2 className="text-lg font-semibold text-gray-900">Workflow Graph</h2>
                  <p className="text-sm text-gray-500">Manager → OM → Engineer pipeline</p>
                </div>
                <div className="h-[calc(100%-60px)]">
                  <WorkflowGraph
                    projectId={resolvedProject.id}
                    workflowUpdate={workflowUpdate}
                    onNodeClick={handleWorkflowNodeClick}
                  />
                </div>
              </div>
            </div>
            <div className="w-[420px] p-4 pl-0 flex flex-col gap-4">
              <div className="h-1/2 min-h-0">
                <ActivityFeed logs={activityLogs} />
              </div>
              <div className="h-1/2 min-h-0">
                <AgentInspector agentId={selectedInspectorAgentId} />
              </div>
            </div>
          </div>
        );
      case 'artifacts':
        return (
          <div className="h-full p-4">
            <ArtifactBrowser projectId={resolvedProject.id} project={resolvedProject} />
          </div>
        );
      default:
        return <ChatView projectId={resolvedProject.id} />;
    }
  };

  return (
    <div className="flex h-screen bg-gray-100">
      <Sidebar
        projects={projects}
        activeProjectId={resolvedProject.id}
        activeView={view}
        onProjectChange={(nextProjectId) => navigate(`/project/${nextProjectId}/${view}`)}
      />
      <main className="flex-1 overflow-hidden">
        {renderView()}
      </main>
      {view !== 'workflow' && view !== 'artifacts' && <AgentsPanel projectId={resolvedProject.id} />}
    </div>
  );
}

function App() {
  const [isBackendConnected, setIsBackendConnected] = useState(false);
  const [projects, setProjects] = useState<Project[]>([]);
  const [isProjectsLoading, setIsProjectsLoading] = useState(false);
  const [projectsError, setProjectsError] = useState<string | null>(null);

  // Token is set synchronously at module level above (before any component renders).

  const loadProjects = useCallback(async () => {
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
  }, []);

  useEffect(() => {
    void loadProjects();
  }, [loadProjects]);

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
        {/* Projects Dashboard */}
        <Route path="/projects" element={<ProjectsPage onProjectsUpdated={loadProjects} />} />
        
        {/* Project Settings */}
        <Route path="/project/:projectId/settings" element={<SettingsPage />} />
        
        {/* Legacy routes redirect to first project */}
        <Route
          path="/"
          element={
            isProjectsLoading ? (
              <div className="h-screen flex items-center justify-center text-gray-600">
                Loading...
              </div>
            ) : projects.length === 0 ? (
              <Navigate to="/projects" replace />
            ) : (
              <Navigate to={`/project/${projects[0].id}/chat`} replace />
            )
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
        
        {/* Project views */}
        <Route
          path="/project/:projectId/chat"
          element={<ProjectPage projects={projects} view="chat" isProjectsLoading={isProjectsLoading} />}
        />
        <Route
          path="/project/:projectId/kanban"
          element={<ProjectPage projects={projects} view="kanban" isProjectsLoading={isProjectsLoading} />}
        />
        <Route
          path="/project/:projectId/workflow"
          element={<ProjectPage projects={projects} view="workflow" isProjectsLoading={isProjectsLoading} />}
        />
        <Route
          path="/project/:projectId/artifacts"
          element={<ProjectPage projects={projects} view="artifacts" isProjectsLoading={isProjectsLoading} />}
        />
        
        {/* Fallback */}
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>

      <ConnectionStatus isConnected={isBackendConnected} />
    </BrowserRouter>
  );
}

export default App;
