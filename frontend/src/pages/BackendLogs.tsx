import { Link, Navigate, useParams } from 'react-router-dom';
import { UsageStreamView } from '../components/BackendLogs';
import { ConnectionStatus } from '../components/Workspace/ConnectionStatus';
import { AgentStreamProvider, useAgentStreamContext } from '../contexts/AgentStreamContext';
import { useProjectContext } from '../contexts/ProjectContext';

function UsageStreamContent({ projectId }: { projectId: string }) {
  const { projects, loading } = useProjectContext();
  const { usageEvents, clearUsageEvents, isConnected, workersReady } = useAgentStreamContext();
  const project = projects.find((p) => p.id === projectId);

  if (loading) {
    return <div className="flex h-screen items-center justify-center text-gray-500">Loading project...</div>;
  }

  if (!project) {
    return <Navigate to="/repositories" replace />;
  }

  return (
    <div className="h-screen overflow-hidden bg-[var(--app-bg)]">
      <header className="border-b border-[var(--border-color)] bg-[var(--surface-card)] px-6 py-4">
        <div className="mx-auto flex w-full max-w-7xl items-center justify-between gap-3">
          <div className="min-w-0">
            <h1 className="truncate text-lg font-semibold text-[var(--text-primary)]">
              AI Usage &mdash; {project.name}
            </h1>
            <p className="text-xs text-[var(--text-muted)]">
              Real-time LLM call stream: tokens, cost, and model breakdown.
            </p>
          </div>
          <Link
            to={`/repository/${projectId}/workspace`}
            className="rounded-md border border-[var(--border-color)] bg-[var(--surface-card)] px-3 py-1.5 text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
          >
            Back to workspace
          </Link>
        </div>
      </header>

      <main className="mx-auto h-[calc(100vh-73px)] max-w-7xl p-4">
        <UsageStreamView events={usageEvents} onClear={clearUsageEvents} />
      </main>

      <div className="pointer-events-none">
        <ConnectionStatus isConnected={isConnected} workersReady={workersReady} />
      </div>
    </div>
  );
}

export function BackendLogsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  if (!projectId) {
    return <Navigate to="/repositories" replace />;
  }

  return (
    <AgentStreamProvider
      projectId={projectId}
      enablePrimaryStream
      enableBackendLogStream={false}
      wsChannels="usage"
    >
      <UsageStreamContent projectId={projectId} />
    </AgentStreamProvider>
  );
}

export default BackendLogsPage;
