/**
 * SandboxConfigEditor — user-level sandbox configuration profiles.
 *
 * CRUD interface for managing setup scripts that can be assigned to agents.
 * Each config defines a shell script that runs inside the sandbox container
 * to install apps, load data, or configure the environment.
 */

import { useCallback, useEffect, useState } from 'react';
import { Loader2, Plus, Trash2, Save, X, Monitor } from 'lucide-react';
import {
  listSandboxConfigs,
  listSandboxImages,
  createSandboxConfig,
  updateSandboxConfig,
  deleteSandboxConfig,
  type SandboxOSImage,
} from '../../api/client';
import type { SandboxConfig } from '../../types';
import { Button, Card, Input, Textarea } from '../ui';

interface EditingConfig {
  id: string | null; // null = creating new
  name: string;
  description: string;
  setup_script: string;
  os_image: string;
}

export function SandboxConfigEditor() {
  const [configs, setConfigs] = useState<SandboxConfig[]>([]);
  const [osImages, setOsImages] = useState<SandboxOSImage[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [editing, setEditing] = useState<EditingConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const [data, images] = await Promise.all([
        listSandboxConfigs(),
        listSandboxImages().catch(() => []),
      ]);
      setConfigs(data);
      if (images.length > 0) setOsImages(images);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load configs');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleSave = async () => {
    if (!editing || !editing.name.trim()) return;
    setSaving(true);
    setError(null);
    try {
      if (editing.id) {
        // Update existing
        await updateSandboxConfig(editing.id, {
          name: editing.name.trim(),
          description: editing.description.trim() || null,
          setup_script: editing.setup_script,
          os_image: editing.os_image || null,
        });
      } else {
        // Create new
        await createSandboxConfig({
          name: editing.name.trim(),
          description: editing.description.trim() || null,
          setup_script: editing.setup_script,
          os_image: editing.os_image || null,
        });
      }
      setEditing(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save config');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    setConfirmDelete(null);
    setError(null);
    try {
      await deleteSandboxConfig(id);
      if (editing?.id === id) setEditing(null);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete config');
    }
  };

  const defaultOsImage = osImages.find((img) => img.default)?.slug ?? 'ubuntu-22.04';

  const startEditing = (config: SandboxConfig) => {
    setEditing({
      id: config.id,
      name: config.name,
      description: config.description ?? '',
      setup_script: config.setup_script,
      os_image: config.os_image ?? defaultOsImage,
    });
    setError(null);
  };

  const startCreating = () => {
    setEditing({
      id: null,
      name: '',
      description: '',
      setup_script: '#!/bin/bash\n# Install apps and configure the sandbox environment\n\n',
      os_image: defaultOsImage,
    });
    setError(null);
  };

  if (loading) {
    return <div className="p-4 text-sm text-gray-500">Loading sandbox configs...</div>;
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="ml-auto text-red-400 hover:text-red-600">&times;</button>
        </div>
      )}

      {/* Config list */}
      {configs.length === 0 && !editing && (
        <div className="text-sm text-gray-500">
          No sandbox configs yet. Create one to define a reusable setup script for agent sandboxes.
        </div>
      )}

      {configs.map((cfg) => (
        <div
          key={cfg.id}
          className={`flex items-center gap-3 rounded-lg border px-4 py-3 ${
            editing?.id === cfg.id
              ? 'border-blue-300 bg-blue-50/50'
              : 'border-[var(--border-color)] bg-[var(--surface-card)]'
          }`}
        >
          <div className="min-w-0 flex-1">
            <div className="text-sm font-medium text-[var(--text-primary)]">{cfg.name}</div>
            {cfg.description && (
              <div className="text-xs text-[var(--text-muted)] mt-0.5">{cfg.description}</div>
            )}
            <div className="flex items-center gap-2 mt-0.5">
              {cfg.os_image && (
                <span className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                  cfg.os_image.startsWith('windows')
                    ? 'bg-blue-100 text-blue-700'
                    : 'bg-orange-100 text-orange-700'
                }`}>
                  <Monitor className="w-3 h-3" />
                  {osImages.find((img) => img.slug === cfg.os_image)?.display_name ?? cfg.os_image}
                </span>
              )}
              <span className="text-xs text-gray-400">
                {cfg.setup_script ? `${cfg.setup_script.split('\n').length} lines` : 'Empty script'}
              </span>
            </div>
          </div>

          <div className="flex items-center gap-1.5">
            <Button
              size="sm"
              variant="outline"
              onClick={() => startEditing(cfg)}
              disabled={editing?.id === cfg.id}
            >
              Edit
            </Button>
            {confirmDelete === cfg.id ? (
              <div className="flex items-center gap-1">
                <Button
                  size="sm"
                  variant="danger"
                  onClick={() => handleDelete(cfg.id)}
                >
                  Confirm
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setConfirmDelete(null)}
                >
                  Cancel
                </Button>
              </div>
            ) : (
              <button
                type="button"
                onClick={() => setConfirmDelete(cfg.id)}
                className="p-1.5 text-gray-400 hover:text-red-600 rounded"
                title="Delete"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
      ))}

      {/* Editor panel */}
      {editing && (
        <Card className="p-4 border-blue-200">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold text-gray-900">
              {editing.id ? 'Edit Config' : 'New Config'}
            </h3>
            <button
              onClick={() => setEditing(null)}
              className="p-1 text-gray-400 hover:text-gray-600 rounded"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          <div className="space-y-3">
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Name</label>
              <Input
                value={editing.name}
                onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                placeholder="e.g. Chrome + Slack + VS Code"
                maxLength={100}
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Description</label>
              <Input
                value={editing.description}
                onChange={(e) => setEditing({ ...editing, description: e.target.value })}
                placeholder="Optional description of what this config sets up"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Operating System</label>
              <select
                value={editing.os_image}
                onChange={(e) => setEditing({ ...editing, os_image: e.target.value })}
                className="w-full rounded border border-[var(--border-color)] bg-[var(--surface-card)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-1 focus:ring-blue-500"
              >
                {osImages.length > 0 ? (
                  osImages.map((img) => (
                    <option key={img.slug} value={img.slug}>
                      {img.display_name}
                      {img.default ? ' — Default' : ''}
                    </option>
                  ))
                ) : (
                  <option value="ubuntu-22.04">Ubuntu 22.04 LTS</option>
                )}
              </select>
              <p className="text-xs text-gray-400 mt-1">
                Base operating system for the sandbox container.
              </p>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-600 mb-1">Setup Script</label>
              <Textarea
                value={editing.setup_script}
                onChange={(e) => setEditing({ ...editing, setup_script: e.target.value })}
                rows={10}
                className="font-mono text-xs"
                placeholder="#!/bin/bash&#10;apt-get update && apt-get install -y chromium&#10;..."
              />
              <p className="text-xs text-gray-400 mt-1">
                Shell commands run inside the sandbox after creation. Use this to install apps, download data, or configure the environment.
              </p>
            </div>

            <div className="flex items-center gap-2 pt-1">
              <Button
                onClick={handleSave}
                disabled={saving || !editing.name.trim()}
              >
                {saving ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : editing.id ? (
                  <Save className="w-4 h-4" />
                ) : (
                  <Plus className="w-4 h-4" />
                )}
                {editing.id ? 'Save' : 'Create'}
              </Button>
              <Button
                variant="secondary"
                onClick={() => setEditing(null)}
                disabled={saving}
              >
                Cancel
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Create button */}
      {!editing && (
        <Button
          variant="outline"
          onClick={startCreating}
        >
          <Plus className="w-4 h-4" />
          New Config
        </Button>
      )}
    </div>
  );
}

export default SandboxConfigEditor;
