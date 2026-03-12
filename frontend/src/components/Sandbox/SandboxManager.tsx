/**
 * SandboxManager — manage sandbox containers for project agents.
 *
 * Lists all sandboxes, shows status, allows toggling persistence,
 * restarting, resetting (fresh), destroying, config assignment/apply,
 * and reassigning sandboxes between agents.
 */

import { useCallback, useEffect, useState } from 'react';
import {
  listSandboxes,
  restartSandbox,
  destroySandbox,
  applySandboxConfig,
  listSandboxConfigs,
  assignSandboxConfig,
  claimSandbox,
  releaseSandbox,
  updateSandbox,
} from '../../api/client';
import type { SandboxConfig, Sandbox } from '../../types';
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
  const [sandboxes, setSandboxes] = useState<Sandbox[]>([]);
  const [configs, setConfigs] = useState<SandboxConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [actionInProgress, setActionInProgress] = useState<string | null>(null);
  const [confirmDestroy, setConfirmDestroy] = useState<string | null>(null);
  const [confirmReset, setConfirmReset] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [sbData, cfgData] = await Promise.all([
        listSandboxes(projectId),
        listSandboxConfigs().catch(() => [] as SandboxConfig[]),
      ] as const);
      setSandboxes(sbData);
      setConfigs(cfgData);
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

  const handleTogglePersistence = async (sandboxId: string, current: boolean) => {
    setActionInProgress(sandboxId);
    try {
      await updateSandbox(sandboxId, { persistent: !current });
      await refresh();
    } finally {
      setActionInProgress(null);
    }
  };

  const handleRestart = async (sandboxId: string) => {
    setActionInProgress(sandboxId);
    try {
      await restartSandbox(sandboxId);
      await refresh();
    } finally {
      setActionInProgress(null);
    }
  };

  const handleReset = async (sandboxId: string, agentId: string | null) => {
    setActionInProgress(sandboxId);
    setConfirmReset(null);
    try {
      await releaseSandbox(sandboxId);
      if (agentId) {
        await claimSandbox(agentId);
      }
      await refresh();
    } finally {
      setActionInProgress(null);
    }
  };

  const handleDestroy = async (sandboxId: string) => {
    setActionInProgress(sandboxId);
    try {
      await destroySandbox(sandboxId);
      await refresh();
    } finally {
      setActionInProgress(null);
    }
  };

  const handleAssignConfig = async (agentId: string | null, configId: string | null) => {
    if (!agentId) return;
    setActionInProgress(agentId);
    try {
      await assignSandboxConfig(agentId, configId);
      await refresh();
    } finally {
      setActionInProgress(null);
    }
  };

  const handleApplyConfig = async (sandboxId: string) => {
    setActionInProgress(sandboxId);
    try {
      await applySandboxConfig(sandboxId);
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
        const isActing = actionInProgress === sb.id;
        return (
          <div
            key={sb.id}
            className="rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] px-4 py-3"
          >
            {/* Top row: agent info + status + persistence + actions */}
            <div className="flex items-center gap-3">
              {/* Agent info */}
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium text-[var(--text-primary)]">
                    {sb.agent_name ?? 'Unknown'}
                  </span>
                  <Badge variant="default" className="text-[10px]">{sb.agent_role ?? 'engineer'}</Badge>
                </div>
                <div className="mt-0.5 flex items-center gap-2 text-xs text-[var(--text-muted)]">
                  <span className="font-mono text-[10px]">{sb.orchestrator_sandbox_id}</span>
                  {sb.os_image && (
                    <span className={`inline-flex items-center rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                      sb.os_image.startsWith('windows')
                        ? 'bg-blue-100 text-blue-700'
                        : 'bg-orange-100 text-orange-700'
                    }`}>
                      {sb.os_image}
                    </span>
                  )}
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
                onClick={() => handleTogglePersistence(sb.id, sb.persistent)}
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
                  onClick={() => handleRestart(sb.id)}
                  title="Restart container (keeps installed apps)"
                >
                  Restart
                </Button>

                {confirmReset === sb.id ? (
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="danger"
                      disabled={isActing}
                      onClick={() => handleReset(sb.id, sb.agent_id)}
                    >
                      Confirm Reset
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => setConfirmReset(null)}
                    >
                      Cancel
                    </Button>
                  </div>
                ) : (
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={isActing}
                    onClick={() => setConfirmReset(sb.id)}
                    title="Destroy and create a fresh sandbox (loses all data)"
                  >
                    Reset
                  </Button>
                )}

                {confirmDestroy === sb.id ? (
                  <div className="flex items-center gap-1">
                    <Button
                      size="sm"
                      variant="danger"
                      disabled={isActing}
                      onClick={() => handleDestroy(sb.id)}
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
                    onClick={() => setConfirmDestroy(sb.id)}
                    title="Permanently destroy sandbox and volume"
                  >
                    Destroy
                  </Button>
                )}
              </div>
            </div>

            {/* Bottom row: config */}
            {sb.agent_id && (
              <div className="mt-2 flex items-center gap-3 pt-2 border-t border-[var(--border-color)]">
                {/* Config assignment */}
                <div className="flex items-center gap-2 flex-1">
                  <label className="text-xs text-gray-500 whitespace-nowrap">Config:</label>
                  <select
                    value={sb.sandbox_config_id ?? ''}
                    onChange={(e) => handleAssignConfig(sb.agent_id, e.target.value || null)}
                    disabled={isActing}
                    className="max-w-[180px] rounded border border-[var(--border-color)] bg-[var(--surface-card)] px-2 py-1 text-xs text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
                  >
                    <option value="">— None —</option>
                    {configs.map((cfg) => (
                      <option key={cfg.id} value={cfg.id}>
                        {cfg.name}
                      </option>
                    ))}
                  </select>
                  {sb.sandbox_config_id && (
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={isActing}
                      onClick={() => handleApplyConfig(sb.id)}
                      title="Re-run the config setup script on this sandbox"
                    >
                      {isActing ? '...' : 'Apply'}
                    </Button>
                  )}
                </div>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export default SandboxManager;
