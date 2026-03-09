/**
 * WorkspacePage — main workspace: chat/kanban views.
 * Wraps content in AgentStreamProvider so agent chat and stream buffers work.
 *
 * NOTE: Multi-agent monitoring grid and co-pilot mode have been promoted to
 * their own top-level pages (/monitor and /copilot). This page is now focused
 * on the chat + kanban views.
 */

import { useCallback, useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { AgentStreamProvider, useAgentStreamContext } from '../contexts/AgentStreamContext';
import { useProjectContext } from '../contexts/ProjectContext';
import { WorkspaceLayout } from '../components/Workspace';
import { AppLayout } from '../components/Layout';
import { AgentChatView } from '../components/AgentChat';
import { KanbanBoard } from '../components/Kanban';

export type WorkspaceView = 'workspace' | 'kanban';

interface WorkspacePageProps {
  view: WorkspaceView;
}

function WorkspaceContent({
  projectId,
  view,
}: {
  projectId: string;
  view: WorkspaceView;
}) {
  const {
    isConnected,
    workersReady,
  } = useAgentStreamContext();

  // Single agent for chat targeting
  const [chatAgentId, setChatAgentId] = useState<string | null>(null);

  const handleSelectChatAgent = useCallback((agentId: string | null) => {
    setChatAgentId(agentId);
  }, []);

  let main: React.ReactNode;
  switch (view) {
    case 'workspace':
      main = (
        <AgentChatView
          projectId={projectId}
          selectedAgentId={chatAgentId}
          onSelectAgent={handleSelectChatAgent}
        />
      );
      break;
    case 'kanban':
      main = <KanbanBoard projectId={projectId} />;
      break;
    default:
      main = null;
  }

  return (
    <WorkspaceLayout
      main={main}
      isWsConnected={isConnected}
      workersReady={workersReady}
    />
  );
}

export function WorkspacePage({ view }: WorkspacePageProps) {
  const { projectId } = useParams<{ projectId: string }>();
  const { projects, loading } = useProjectContext();

  if (!projectId) {
    return <Navigate to="/projects" replace />;
  }

  const project = projects.find((p) => p.id === projectId);
  if (!loading && !project) {
    return <Navigate to="/projects" replace />;
  }

  return (
    <AppLayout>
      <AgentStreamProvider projectId={projectId}>
        <WorkspaceContent
          projectId={projectId}
          view={view}
        />
      </AgentStreamProvider>
    </AppLayout>
  );
}

export default WorkspacePage;
