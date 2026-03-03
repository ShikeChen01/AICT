/**
 * SandboxManager — manage sandbox containers for project agents.
 *
 * Lists all sandboxes, shows status, allows toggling persistence,
 * restarting, and destroying sandboxes.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  listSandboxes,
  toggleSandboxPersistence,
  restartSandbox,
  destroySandbox,
  type SandboxInfo,
} from '../../api/client';
import { Badge, Button } from '../ui';

interface SandboxManagerProps {
  projectId: string;
}

function statusColor(status: string | null): string {
  switch (status) {
    case 'assigned':
    case 'idle':
      return 'bg-green-100 text-green-800';
    case 'resetting':
      return 'bg-amber-100 text-amber-800';
    case 'unhealthy':
      return 'bg-red-100 text-red-800';
    default:
      return 'bg-gray-100 text-gray-600';
  }
}

export function SandboxManager({ projectId }: SandboxManagerProps) {
  const [sandboxes, setSandboxes] = useState<SandboxInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [confirmDestroy, setConfirmDestroy] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listSandboxes(projectId);
      setSandboxes(data);
    } catch {
      // silently fail — pool manager may be unreachable
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, 10_000);
    return () => clearInterval(interval);
  }, [refresh]);

  const handleTogglePersistence = async (agentId: string, current: boolean) => {
    setActionInProgress(agentId);
    try {
      await toggleSandboxPersistence(agentId, !current);
      await refresh();
    } finally {
      setActionInProgress(null);
    }
  };

  const handleRestart = async (agentId: string) => {
    setActionInProgress(agentId);
    try {
      await restartSandbox(agentId);
      await refresh();
    } finally {
      setActionInProgress(null);
    }
  };

  const handleDestroy = async (agentId: string) => {
    setActionInProgress(agentId);
    setConfirmDestroy(null);
    try {
      await destroySandbox(agentId);
      await refresh();
    } finally {
      setActionInProgress(null);
    }
  };

  if (loading) {
    return <div className="p-4 text-sm text-gray-500">Loading sandboxes...</div>;
  }

  if (sandboxes.length === 0) {
    return (
      <div className="p-4 text-sm text-gray-500">
        No active sandboxes. Sandboxes are created when agents use GUI tools.
      </div>
    );
  }

  return (
    <div className="space-y-2 p-4">
      {sandboxes.map((sb) => {
        const isActing = actionInProgress === sb.agent_id;
        return (
          <div
            key={sb.agent_id}
            className="flex items-center gap-3 rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] px-4 py-3"
          >
            {/* Agent info */}
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <span className="truncate text-sm font-medium text-[var(--text-primary)]">
                  {sb.agent_name}
                </span>
                <Badge variant="default" className="text-[10px]">{sb.agent_role}</Badge>
              </div>
              <div className="mt-0.5 text-xs text-[var(--text-muted)]">
                {sb.sandbox_id}
              </div>
            </div>

            {/* Status */}
            <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${statusColor(sb.status)}`}>
              {sb.status ?? 'unknown'}
            </span>

            {/* Persistent toggle */}
            <button
              type="button"
              disabled={isActing}
              onClick={() => handleTogglePersistence(sb.agent_id, sb.persistent)}
              className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
                sb.persistent
                  ? 'bg-blue-100 text-blue-800 hover:bg-blue-200'
                  : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
              } disabled:opacity-50`}
              title={sb.persistent ? 'Sandbox is persistent — click to make ephemeral' : 'Sandbox is ephemeral — click to make persistent'}
            >
              {sb.persistent ? 'Persistent' : 'Ephemeral'}
            </button>

            {/* Actions */}
            <div className="flex items-center gap-1.5">
              <Button
                size="sm"
                variant="outline"
                disabled={isActing}
                onClick={() => handleRestart(sb.agent_id)}
              >
                {isActing ? '...' : 'Restart'}
              </Button>

              {confirmDestroy === sb.agent_id ? (
                <div className="flex items-center gap-1">
                  <Button
                    size="sm"
                    variant="danger"
                    disabled={isActing}
                    onClick={() => handleDestroy(sb.agent_id)}
                  >
                    Confirm
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setConfirmDestroy(null)}
                  >
                    Cancel
                  </Button>
                </div>
              ) : (
                <Button
                  size="sm"
                  variant="outline"
                  disabled={isActing}
                  onClick={() => setConfirmDestroy(sb.agent_id)}
                >
                  Destroy
                </Button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export default SandboxManager;
