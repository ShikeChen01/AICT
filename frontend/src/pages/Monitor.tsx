/**
 * MonitorPage — dedicated multi-agent monitoring grid.
 * Shows a 2×2 grid of agent VNC views + live logs.
 * Promoted from a sidebar panel in WorkspacePage to a top-level page.
 */

import { useCallback, useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { AgentStreamProvider, useAgentStreamContext } from '../contexts/AgentStreamContext';
import { useProjectContext } from '../contexts/ProjectContext';
import { AgentSelector, MultiAgentGrid, ExpandedAgentModal } from '../components/Workspace';
import { AppLayout } from '../components/Layout';
import { ActivityFeed } from '../components/ActivityFeed';
import { useAgents } from '../hooks';
import { Panel } from '../components/ui';

function MonitorContent({ projectId }: { projectId: string }) {
  const {
    isConnected,
    workersReady,
    getBuffer,
    clearBuffer,
    activityLogs,
  } = useAgentStreamContext();

  const [selectedAgentIds, setSelectedAgentIds] = useState<string[]>([]);
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

  return (
    <>
      <div className="flex h-full min-h-0 flex-col overflow-hidden">
        {/* Connection status bar */}
        {(!isConnected || !workersReady) && (
          <div className="shrink-0 border-b border-[var(--color-warning)]/30 bg-[var(--color-warning-light)] px-4 py-1.5 text-center text-xs text-[var(--color-warning)]">
            {!isConnected ? 'WebSocket disconnected — reconnecting…' : 'Workers not ready — waiting for backend…'}
          </div>
        )}

        {/* Top: Agent selector bar */}
        <div className="shrink-0 border-b border-[var(--border-color)] bg-[var(--surface-card)]">
          <div className="flex items-center gap-4 px-4 py-2">
            <h2 className="text-sm font-semibold text-[var(--text-primary)] whitespace-nowrap">
              Agent Monitor
            </h2>
            <div className="flex-1 min-w-0">
              <AgentSelector
                agents={agents}
                selectedIds={selectedAgentIds}
                onToggle={handleToggleAgent}
              />
            </div>
          </div>
        </div>

        {/* Main grid area */}
        <div className="flex flex-1 min-h-0">
          {/* Grid */}
          <div className="flex-1 min-w-0 min-h-0">
            <MultiAgentGrid
              agents={agents}
              selectedIds={selectedAgentIds}
              getBuffer={getBuffer}
              onExpand={setExpandedAgentId}
              onClearBuffer={clearBuffer}
            />
          </div>

          {/* Activity sidebar */}
          <div className="w-80 shrink-0 border-l border-[var(--border-color)] flex flex-col min-h-0 bg-[var(--surface-card)]">
            <Panel
              title="Activity Timeline"
              subtitle="Realtime events across all agents"
              className="min-h-0 h-full"
              bodyClassName="min-h-0"
            >
              <ActivityFeed logs={activityLogs} />
            </Panel>
          </div>
        </div>
      </div>

      {/* Expanded agent modal (Co-Pilot mode shortcut from grid) */}
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

export function MonitorPage() {
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
        <MonitorContent projectId={projectId} />
      </AgentStreamProvider>
    </AppLayout>
  );
}

export default MonitorPage;
