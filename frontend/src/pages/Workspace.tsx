/**
 * WorkspacePage — main workspace: Sidebar | Main (chat/kanban/workflow/artifacts) | Agents panel.
 * Wraps content in AgentStreamProvider so agent chat and stream buffers work.
 */

import { useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { AgentStreamProvider, useAgentStreamContext } from '../contexts/AgentStreamContext';
import { useProjectContext } from '../contexts/ProjectContext';
import { WorkspaceLayout } from '../components/Workspace';
import { AgentChatView } from '../components/AgentChat';
import { KanbanBoard } from '../components/Kanban';
import { WorkflowGraph } from '../components/Workflow';
import { ArtifactBrowser } from '../components/Artifacts';
import { AgentsPanel } from '../components/Agents';
import type { Project } from '../types';

export type WorkspaceView = 'workspace' | 'kanban' | 'workflow' | 'artifacts';

interface WorkspacePageProps {
  view: WorkspaceView;
}

function WorkspaceContent({
  projectId,
  view,
  project,
  loading: projectsLoading,
}: {
  projectId: string;
  view: WorkspaceView;
  project: Project | undefined;
  loading: boolean;
}) {
  const { isConnected } = useAgentStreamContext();
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);

  let main: React.ReactNode;
  switch (view) {
    case 'workspace':
      main = (
        <AgentChatView
          projectId={projectId}
          selectedAgentId={selectedAgentId}
          onSelectAgent={setSelectedAgentId}
        />
      );
      break;
    case 'kanban':
      main = <KanbanBoard projectId={projectId} />;
      break;
    case 'workflow':
      main = <WorkflowGraph projectId={projectId} />;
      break;
    case 'artifacts':
      if (projectsLoading) {
        main = (
          <div className="flex h-full items-center justify-center text-gray-500">
            Loading project...
          </div>
        );
      } else if (!project) {
        main = (
          <div className="flex h-full items-center justify-center text-gray-600">
            Project not found.
          </div>
        );
      } else {
        main = <ArtifactBrowser projectId={projectId} project={project} />;
      }
      break;
    default:
      main = null;
  }

  const agentsPanel =
    view !== 'workflow' ? <AgentsPanel projectId={projectId} /> : undefined;

  return (
    <WorkspaceLayout
      activeProjectId={projectId}
      main={main}
      agentsPanel={agentsPanel}
      isWsConnected={isConnected}
    />
  );
}

export function WorkspacePage({ view }: WorkspacePageProps) {
  const { projectId } = useParams<{ projectId: string }>();
  const { projects, loading } = useProjectContext();

  if (!projectId) {
    return <Navigate to="/repositories" replace />;
  }

  const project = projects.find((p) => p.id === projectId);
  if (!loading && !project) {
    return <Navigate to="/repositories" replace />;
  }

  return (
    <AgentStreamProvider projectId={projectId}>
      <WorkspaceContent
        projectId={projectId}
        view={view}
        project={project}
        loading={loading}
      />
    </AgentStreamProvider>
  );
}

export default WorkspacePage;
