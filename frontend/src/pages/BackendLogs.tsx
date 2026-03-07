import { Navigate, useParams } from 'react-router-dom';
import { UsageStreamView } from '../components/BackendLogs';
import { AgentStreamProvider, useAgentStreamContext } from '../contexts/AgentStreamContext';
import { useProjectContext } from '../contexts/ProjectContext';
import { AppLayout } from '../components/Layout';

function UsageStreamContent({ projectId }: { projectId: string }) {
  const { projects, loading } = useProjectContext();
  const { usageEvents, clearUsageEvents } = useAgentStreamContext();
  const project = projects.find((p) => p.id === projectId);

  if (loading) {
    return <div className="flex h-screen items-center justify-center text-gray-500">Loading project...</div>;
  }

  if (!project) {
    return <Navigate to="/projects" replace />;
  }

  return (
    <AppLayout>
    <div className="flex-1 overflow-hidden bg-[var(--app-bg)]">
      <div className="mx-auto max-w-7xl px-6 pt-4 pb-2">
        <h1 className="text-xl font-semibold text-[var(--text-primary)]">
          Logs &mdash; {project.name}
        </h1>
        <p className="text-xs text-[var(--text-muted)]">
          Real-time LLM call stream: tokens, cost, and model breakdown.
        </p>
      </div>

      <main className="mx-auto h-[calc(100vh-140px)] max-w-7xl p-4">
        <UsageStreamView events={usageEvents} onClear={clearUsageEvents} />
      </main>
    </div>
    </AppLayout>
  );
}

export function BackendLogsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  if (!projectId) {
    return <Navigate to="/projects" replace />;
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
