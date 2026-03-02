/**
 * WorkspacePage — main workspace: Sidebar | Main (chat/kanban/prompt assembly/project architecture) | Agents panel.
 * Wraps content in AgentStreamProvider so agent chat and stream buffers work.
 */

import { useEffect, useRef, useState } from 'react';
import { Navigate, useParams } from 'react-router-dom';
import { AgentStreamProvider, useAgentStreamContext } from '../contexts/AgentStreamContext';
import { useProjectContext } from '../contexts/ProjectContext';
import { WorkspaceLayout } from '../components/Workspace';
import { AgentChatView } from '../components/AgentChat';
import { KanbanBoard } from '../components/Kanban';
import { PromptBuilderPage } from '../components/PromptBuilder';
import { ArchitecturePage } from '../components/Architecture/ArchitecturePage';
import { AgentsPanel } from '../components/Agents';
import { ActivityFeed } from '../components/ActivityFeed';
import { AgentStream } from '../components/AgentChat/AgentStream';
import { Panel } from '../components/ui';
export type WorkspaceView = 'workspace' | 'kanban' | 'workflow' | 'artifacts';

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
  const [selectedAgentId, setSelectedAgentId] = useState<string | null>(null);
  const [streamRatio, setStreamRatio] = useState(0.38);
  const [agentsRatio, setAgentsRatio] = useState(0.45);
  const [isResizingStream, setIsResizingStream] = useState(false);
  const [isResizingAgents, setIsResizingAgents] = useState(false);
  const monitoringRef = useRef<HTMLDivElement | null>(null);
  const lowerStackRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isResizingStream) return;
    const onMove = (event: MouseEvent) => {
      const rect = monitoringRef.current?.getBoundingClientRect();
      if (!rect) return;
      const next = (event.clientY - rect.top) / rect.height;
      const clamped = Math.min(Math.max(next, 0.2), 0.8);
      setStreamRatio(clamped);
    };
    const onUp = () => setIsResizingStream(false);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'row-resize';
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [isResizingStream]);

  useEffect(() => {
    if (!isResizingAgents) return;
    const onMove = (event: MouseEvent) => {
      const rect = lowerStackRef.current?.getBoundingClientRect();
      if (!rect) return;
      const next = (event.clientY - rect.top) / rect.height;
      const clamped = Math.min(Math.max(next, 0.2), 0.8);
      setAgentsRatio(clamped);
    };
    const onUp = () => setIsResizingAgents(false);
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'row-resize';
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [isResizingAgents]);

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
      main = <PromptBuilderPage projectId={projectId} />;
      break;
    case 'artifacts':
      main = <ArchitecturePage projectId={projectId} />;
      break;
    default:
      main = null;
  }

  const agentsPanel =
    view === 'workspace' ? (
      <div ref={monitoringRef} className="flex h-full min-h-0 flex-col">
        <Panel
          title="Live stream"
          subtitle={selectedAgentId ? 'Selected agent output' : 'Select an agent to monitor'}
          className="min-h-0"
          bodyClassName="min-h-0"
          style={{ flex: `0 0 ${Math.round(streamRatio * 100)}%` }}
        >
          <AgentStream
            buffer={selectedAgentId ? getBuffer(selectedAgentId) : getBuffer('')}
            onClear={selectedAgentId ? () => clearBuffer(selectedAgentId) : undefined}
          />
        </Panel>
        <div
          role="separator"
          aria-orientation="horizontal"
          aria-label="Resize live stream panel"
          onMouseDown={(event) => {
            event.preventDefault();
            setIsResizingStream(true);
          }}
          className="my-1 h-1.5 cursor-row-resize rounded bg-transparent hover:bg-[var(--border-color)] active:bg-[var(--color-primary)]/40"
        />
        <div ref={lowerStackRef} className="flex min-h-0 flex-1 flex-col">
          <Panel
            title="Agents"
            subtitle="Status, queue, and latest signals"
            className="min-h-0"
            bodyClassName="min-h-0"
            style={{ flex: `0 0 ${Math.round(agentsRatio * 100)}%` }}
          >
            <AgentsPanel projectId={projectId} selectedAgentId={selectedAgentId} onSelectAgent={setSelectedAgentId} />
          </Panel>
          <div
            role="separator"
            aria-orientation="horizontal"
            aria-label="Resize agents panel"
            onMouseDown={(event) => {
              event.preventDefault();
              setIsResizingAgents(true);
            }}
            className="my-1 h-1.5 cursor-row-resize rounded bg-transparent hover:bg-[var(--border-color)] active:bg-[var(--color-primary)]/40"
          />
          <Panel
            title="Activity timeline"
            subtitle="Realtime events across all agents"
            className="min-h-0 flex-1"
            bodyClassName="min-h-0"
            headerActions={(
              <button
                type="button"
                onClick={() => {
                  const logsUrl = `/repository/${projectId}/backend-logs`;
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
    <WorkspaceLayout
      activeProjectId={projectId}
      main={main}
      monitoringPanel={agentsPanel}
      isWsConnected={isConnected}
      workersReady={workersReady}
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
      />
    </AgentStreamProvider>
  );
}

export default WorkspacePage;
