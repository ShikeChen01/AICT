/**
 * WorkspacePage — main workspace: chat/kanban views with multi-agent monitoring.
 * Wraps content in AgentStreamProvider so agent chat and stream buffers work.
 *
 * Phase 3: Multi-agent 2×2 grid with VNC + logs per agent.
 */

import { useCallback, useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { AgentStreamProvider, useAgentStreamContext } from '../contexts/AgentStreamContext';
import { useProjectContext } from '../contexts/ProjectContext';
import { WorkspaceLayout, AgentSelector, MultiAgentGrid, ExpandedAgentModal } from '../components/Workspace';
import { AppLayout } from '../components/Layout';
import { AgentChatView } from '../components/AgentChat';
import { KanbanBoard } from '../components/Kanban';
import { ActivityFeed } from '../components/ActivityFeed';
import { useAgents } from '../hooks';
import { Panel } from '../components/ui';

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
    getBuffer,
    clearBuffer,
    activityLogs,
  } = useAgentStreamContext();

  // Multi-agent selection (up to 4)
  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([]);
  // Single agent for chat targeting
  const [chatAgentId, setChatAgentId] = useState<string | null>(null);
  // Expanded modal for co-pilot mode
  const [expandedAgentId, setExpandedAgentId] = useState<string | null>(null);

  const { agents } = useAgents(projectId);

  const expandedAgent = expandedAgentId ? agents.find((a) => a.id === expandedAgentId) : null;

  const handleToggleAgent = useCallback((agentId: string) => {
    setSelectedAgentIds((prev) => {
      if (prev.includes(agentId)) {
        return prev.filter((id) => id !== agentId);
      }
      if (prev.length >= 4) return prev;
      return [...prev, agentId];
    });
  }, []);

  const handleSelectChatAgent = useCallback((agentId: string | null) => {
    setChatAgentId(agentId);
    // Also add to grid monitoring if not already selected
    if (agentId) {
      setSelectedAgentIds((prev) => {
        if (prev.includes(agentId)) return prev;
        if (prev.length >= 4) return prev;
        return [...prev, agentId];
      });
    }
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

  const monitoringPanel =
    view === 'workspace' ? (
      <div className="flex h-full min-h-0 flex-col">
        {/* Agent selector */}
        <div className="shrink-0 border-b border-[var(--border-color)]">
          <AgentSelector
            agents={agents}
            selectedIds={selectedAgentIds}
            onToggle={handleToggleAgent}
          />
        </div>

        {/* Multi-agent grid */}
        <div className="flex-1 min-h-0">
          <MultiAgentGrid
            agents={agents}
            selectedIds={selectedAgentIds}
            getBuffer={getBuffer}
            onExpand={setExpandedAgentId}
            onClearBuffer={clearBuffer}
          />
        </div>

        {/* Activity timeline (collapsed) */}
        <div className="shrink-0 border-t border-[var(--border-color)]" style={{ maxHeight: '30%' }}>
          <Panel
            title="Activity timeline"
            subtitle="Realtime events across all agents"
            className="min-h-0 h-full"
            bodyClassName="min-h-0"
            headerActions={(
              <button
                type="button"
                onClick={() => {
                  const logsUrl = `/project/${projectId}/logs`;
                  const tab = window.open(logsUrl, '_blank', 'noopener,noreferrer');
                  if (!tab) {
                    window.location.assign(logsUrl);
                  }
                }}
                className="rounded-md border border-[var(--border-color)] bg-[var(--surface-card)] px-2.5 py-1 text-xs font-medium text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
              >
                Backend logs
              </button>
            )}
          >
            <ActivityFeed logs={activityLogs} />
          </Panel>
        </div>
      </div>
    ) : undefined;

  return (
    <>
      <WorkspaceLayout
        main={main}
        monitoringPanel={monitoringPanel}
        isWsConnected={isConnected}
        workersReady={workersReady}
      />

      {/* Expanded agent modal (Co-Pilot mode) */}
      {expandedAgent && (
        <ExpandedAgentModal
          agent={expandedAgent}
          buffer={getBuffer(expandedAgent.id)}
          onClose={() => setExpandedAgentId(null)}
          onClearBuffer={clearBuffer}
        />
      )}
    </>
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
