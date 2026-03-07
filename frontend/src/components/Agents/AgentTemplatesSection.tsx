/**
 * Agent Templates Section — manages agent designs (templates).
 *
 * System defaults (Manager, CTO, Engineer) can be edited but not deleted.
 * Users can create new worker templates and delete them.
 */

import { useState, useEffect, useCallback } from 'react';
import {
  Plus,
  Trash2,
  Save,
  Loader2,
  BrainCircuit,
  Settings2,
  ChevronDown,
  ChevronUp,
  X,
  Play,
} from 'lucide-react';
import {
  listTemplates,
  createTemplate,
  updateTemplate,
  deleteTemplate,
  spawnFromTemplate,
} from '../../api/client';
import type { AgentTemplate, CreateAgentTemplate } from '../../types';
import { Button, Input } from '../ui';

// ── Model options ──────────────────────────────────────────────────────

const MODEL_OPTIONS = [
  { value: 'claude-opus-4-6', label: 'Claude Opus 4.6 (powerful)' },
  { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6 (balanced)' },
  { value: 'claude-haiku-4-6', label: 'Claude Haiku 4.6 (fast)' },
  { value: 'gpt-5.2', label: 'GPT-5.2' },
  { value: 'gpt-4o', label: 'GPT-4o' },
  { value: 'gpt-4o-mini', label: 'GPT-4o Mini' },
  { value: 'o4-mini', label: 'o4-mini (reasoning)' },
  { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
  { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash' },
  { value: 'kimi-k2-0711-preview', label: 'Kimi K2 (very cheap)' },
];

const BASE_ROLE_LABELS: Record<string, string> = {
  manager: 'Manager',
  cto: 'CTO',
  worker: 'Worker / Engineer',
};

// ── TemplateCard ──────────────────────────────────────────────────────

interface TemplateCardProps {
  template: AgentTemplate;
  onSave: (id: string, updates: { name?: string; model?: string; provider?: string | null; thinking_enabled?: boolean }) => Promise<void>;
  onDelete: (id: string) => Promise<void>;
  onSpawn: (id: string, displayName?: string) => Promise<void>;
}

function TemplateCard({ template, onSave, onDelete, onSpawn }: TemplateCardProps) {
  const [expanded, setExpanded] = useState(false);
  const [name, setName] = useState(template.name);
  const [model, setModel] = useState(template.model);
  const [provider, setProvider] = useState(template.provider ?? '');
  const [thinkingEnabled, setThinkingEnabled] = useState(template.thinking_enabled);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [spawning, setSpawning] = useState(false);

  const isDirty =
    name !== template.name ||
    model !== template.model ||
    (provider || null) !== template.provider ||
    thinkingEnabled !== template.thinking_enabled;

  const handleSave = async () => {
    setSaving(true);
    try {
      await onSave(template.id, {
        name,
        model,
        provider: provider.trim() || null,
        thinking_enabled: thinkingEnabled,
      });
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`Delete template "${template.name}"? This cannot be undone.`)) return;
    setDeleting(true);
    try {
      await onDelete(template.id);
    } finally {
      setDeleting(false);
    }
  };

  const handleSpawn = async () => {
    setSpawning(true);
    try {
      await onSpawn(template.id);
    } finally {
      setSpawning(false);
    }
  };

  return (
    <div className="border border-[var(--border-color)] rounded-lg overflow-hidden">
      <button
        type="button"
        className="w-full flex items-center justify-between px-4 py-3 bg-[var(--surface-muted)] hover:bg-[var(--surface-hover)] transition-colors text-left"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <Settings2 className="w-4 h-4 text-[var(--text-muted)]" />
          <div>
            <span className="font-medium text-[var(--text-primary)]">{template.name}</span>
            <span className="ml-2 text-xs text-[var(--text-muted)]">
              ({BASE_ROLE_LABELS[template.base_role] ?? template.base_role})
            </span>
            {template.is_system_default && (
              <span className="ml-2 text-xs bg-[var(--color-primary)]/15 text-[var(--color-primary)] px-1.5 py-0.5 rounded">
                system
              </span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-xs text-[var(--text-muted)] font-mono">{template.model}</span>
          {thinkingEnabled && (
            <BrainCircuit className="w-4 h-4 text-[var(--color-accent)]" aria-label="Thinking enabled" />
          )}
          {expanded ? <ChevronUp className="w-4 h-4 text-[var(--text-faint)]" /> : <ChevronDown className="w-4 h-4 text-[var(--text-faint)]" />}
        </div>
      </button>

      {expanded && (
        <div className="p-4 space-y-4 border-t border-[var(--border-color)]">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">Template Name</label>
              <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. QA Tester" />
            </div>
            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">Model</label>
              <select
                className="w-full border border-[var(--border-color)] rounded-lg px-3 py-2 text-sm bg-[var(--surface-card)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              >
                {MODEL_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
                {!MODEL_OPTIONS.find((o) => o.value === model) && (
                  <option value={model}>{model} (custom)</option>
                )}
              </select>
            </div>
            <div>
              <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                Provider <span className="text-[var(--text-faint)] font-normal">(optional, inferred if blank)</span>
              </label>
              <Input
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                placeholder="anthropic / openai / google / kimi"
              />
            </div>
            <div className="flex items-center gap-3 self-end pb-1">
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  className="rounded"
                  checked={thinkingEnabled}
                  onChange={(e) => setThinkingEnabled(e.target.checked)}
                />
                <span className="text-sm font-medium text-[var(--text-secondary)] flex items-center gap-1">
                  <BrainCircuit className="w-4 h-4 text-[var(--color-accent)]" />
                  Enable two-stage thinking
                </span>
              </label>
            </div>
          </div>

          <p className="text-xs text-[var(--text-muted)]">
            Template changes only affect <strong>newly created agents</strong>. Existing agents keep their current model and settings.
          </p>

          <div className="flex justify-between items-center">
            {!template.is_system_default ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={handleDelete}
                disabled={deleting}
                className="text-[var(--color-danger)] hover:text-[var(--color-danger)] hover:bg-[var(--color-danger-light)]"
              >
                {deleting ? <Loader2 className="w-4 h-4 animate-spin" /> : <Trash2 className="w-4 h-4" />}
                Delete
              </Button>
            ) : (
              <span />
            )}
            <div className="flex items-center gap-2">
              <Button
                type="button"
                variant="secondary"
                size="sm"
                onClick={handleSpawn}
                disabled={spawning}
                title="Spawn a new agent from this template"
              >
                {spawning ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                Spawn Agent
              </Button>
              <Button
                type="button"
                size="sm"
                onClick={handleSave}
                disabled={saving || !isDirty}
              >
                {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
                Save
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ── CreateTemplateForm ────────────────────────────────────────────────

interface CreateTemplateFormProps {
  onCreated: (template: AgentTemplate) => void;
  onCancel: () => void;
  projectId: string;
}

function CreateTemplateForm({ onCreated, onCancel, projectId }: CreateTemplateFormProps) {
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [baseRole, setBaseRole] = useState('worker');
  const [model, setModel] = useState('gpt-5.2');
  const [provider, setProvider] = useState('');
  const [thinkingEnabled, setThinkingEnabled] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleCreate = async () => {
    if (!name.trim()) { setError('Template name is required'); return; }
    setSaving(true);
    setError(null);
    try {
      const template = await createTemplate(projectId, {
        name: name.trim(),
        base_role: baseRole as 'worker' | 'manager' | 'cto',
        model,
        provider: provider.trim() || null,
        thinking_enabled: thinkingEnabled,
        description: description.trim() || undefined,
      } as CreateAgentTemplate);
      onCreated(template);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to create template');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="border border-[var(--color-primary)]/20 rounded-lg p-4 bg-[var(--color-primary)]/5 space-y-4">
      <div className="flex justify-between items-center">
        <h4 className="text-sm font-semibold text-[var(--text-primary)]">New Agent Design</h4>
        <button type="button" onClick={onCancel} className="text-[var(--text-faint)] hover:text-[var(--text-secondary)]">
          <X className="w-4 h-4" />
        </button>
      </div>
      {error && <p className="text-sm text-[var(--color-danger)]">{error}</p>}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">Template Name</label>
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. QA Tester" />
        </div>
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">Base Role</label>
          <select
            className="w-full border border-[var(--border-color)] rounded-lg px-3 py-2 text-sm bg-[var(--surface-card)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
            value={baseRole}
            onChange={(e) => setBaseRole(e.target.value)}
          >
            <option value="worker">Worker / Engineer</option>
            <option value="manager">Manager</option>
            <option value="cto">CTO</option>
          </select>
        </div>
        <div className="sm:col-span-2">
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
            Description <span className="text-[var(--text-faint)] font-normal">(optional)</span>
          </label>
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Brief description of what this agent design does"
          />
        </div>
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">Model</label>
          <select
            className="w-full border border-[var(--border-color)] rounded-lg px-3 py-2 text-sm bg-[var(--surface-card)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          >
            {MODEL_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
            Provider <span className="text-[var(--text-faint)] font-normal">(optional, inferred if blank)</span>
          </label>
          <Input
            value={provider}
            onChange={(e) => setProvider(e.target.value)}
            placeholder="anthropic / openai / google / kimi"
          />
        </div>
        <div className="flex items-center gap-2 self-end pb-1">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              className="rounded"
              checked={thinkingEnabled}
              onChange={(e) => setThinkingEnabled(e.target.checked)}
            />
            <span className="text-sm font-medium text-[var(--text-secondary)] flex items-center gap-1">
              <BrainCircuit className="w-4 h-4 text-[var(--color-accent)]" />
              Enable thinking
            </span>
          </label>
        </div>
      </div>
      <div className="flex justify-end">
        <Button type="button" size="sm" onClick={handleCreate} disabled={saving}>
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Plus className="w-4 h-4" />}
          Create Design
        </Button>
      </div>
    </div>
  );
}

// ── AgentTemplatesSection ──────────────────────────────────────────────

interface AgentTemplatesSectionProps {
  projectId: string;
}

export function AgentTemplatesSection({ projectId }: AgentTemplatesSectionProps) {
  const [templates, setTemplates] = useState<AgentTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showCreateForm, setShowCreateForm] = useState(false);

  const fetchTemplates = useCallback(async () => {
    try {
      setLoading(true);
      const data = await listTemplates(projectId);
      setTemplates(data);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load templates');
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => { fetchTemplates(); }, [fetchTemplates]);

  const handleSave = async (id: string, updates: Parameters<typeof updateTemplate>[1]) => {
    const updated = await updateTemplate(id, updates);
    setTemplates((prev) => prev.map((t) => (t.id === id ? updated : t)));
  };

  const handleDelete = async (id: string) => {
    await deleteTemplate(id);
    setTemplates((prev) => prev.filter((t) => t.id !== id));
  };

  const handleCreated = (template: AgentTemplate) => {
    setTemplates((prev) => [...prev, template]);
    setShowCreateForm(false);
  };

  const [spawnMessage, setSpawnMessage] = useState<string | null>(null);

  const handleSpawn = async (id: string, displayName?: string) => {
    try {
      setSpawnMessage(null);
      const agent = await spawnFromTemplate(id, displayName ? { display_name: displayName } : undefined);
      setSpawnMessage(`Agent "${agent.display_name}" spawned successfully!`);
      setTimeout(() => setSpawnMessage(null), 4000);
    } catch (e: unknown) {
      setSpawnMessage(e instanceof Error ? `Spawn failed: ${e.message}` : 'Spawn failed');
      setTimeout(() => setSpawnMessage(null), 5000);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-[var(--text-muted)] py-4">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>Loading templates…</span>
      </div>
    );
  }

  if (error) {
    return <p className="text-sm text-[var(--color-danger)]">{error}</p>;
  }

  // Sort: system defaults first, then custom
  const sorted = [...templates].sort((a, b) => {
    if (a.is_system_default && !b.is_system_default) return -1;
    if (!a.is_system_default && b.is_system_default) return 1;
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="space-y-3">
      {spawnMessage && (
        <div className={`text-sm px-3 py-2 rounded-lg ${
          spawnMessage.startsWith('Spawn failed')
            ? 'bg-[var(--color-danger-light)] text-[var(--color-danger)]'
            : 'bg-[var(--color-success-light)] text-[var(--color-success)]'
        }`}>
          {spawnMessage}
        </div>
      )}
      {sorted.map((template) => (
        <TemplateCard
          key={template.id}
          template={template}
          onSave={handleSave}
          onDelete={handleDelete}
          onSpawn={handleSpawn}
        />
      ))}

      {showCreateForm ? (
        <CreateTemplateForm
          projectId={projectId}
          onCreated={handleCreated}
          onCancel={() => setShowCreateForm(false)}
        />
      ) : (
        <Button
          type="button"
          variant="secondary"
          size="sm"
          onClick={() => setShowCreateForm(true)}
          className="w-full"
        >
          <Plus className="w-4 h-4" />
          New Agent Design
        </Button>
      )}

      <p className="text-xs text-[var(--text-muted)]">
        System templates (Manager, CTO, Engineer) are created automatically. You can edit their model and settings.
        Create additional agent designs for specialized roles (e.g. "QA Tester", "DevOps Engineer") and spawn agents from them.
      </p>
    </div>
  );
}
