/**
 * Agent Build Page — tabbed interface with Configure, Prompt Builder, and Templates.
 * This is the foundation for the future Agent Designer (Feature 1.3).
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  Cpu,
  MessageSquare,
  Loader2,
  AlertCircle,
  CheckCircle,
  Save,
  Blocks,
  LayoutTemplate,
} from 'lucide-react';
import {
  getProject,
  getProjectSettings,
  updateProjectSettings,
} from '../api/client';
import type {
  Project,
  ModelOverrides,
  PromptOverrides,
} from '../types';
import { Button, Card, Textarea } from '../components/ui';
import { AppLayout } from '../components/Layout';
import { AgentTemplatesSection } from '../components/Agents/AgentTemplatesSection';
import { PromptBuilderPage } from '../components/PromptBuilder/PromptBuilderPage';

// ── Constants ──────────────────────────────────────────────────────────

type ModelGroup = { label: string; models: { value: string; label: string }[] };

const MODEL_GROUPS: ModelGroup[] = [
  {
    label: 'Anthropic',
    models: [
      { value: 'claude-opus-4-6',    label: 'Claude Opus 4.6 (powerful)' },
      { value: 'claude-sonnet-4-6',  label: 'Claude Sonnet 4.6 (balanced)' },
      { value: 'claude-haiku-4-6',   label: 'Claude Haiku 4.6 (fast)' },
    ],
  },
  {
    label: 'OpenAI',
    models: [
      { value: 'gpt-5.2',      label: 'GPT-5.2' },
      { value: 'gpt-4o',       label: 'GPT-4o' },
      { value: 'gpt-4o-mini',  label: 'GPT-4o Mini (cheap)' },
      { value: 'o4-mini',      label: 'o4-mini (reasoning)' },
    ],
  },
  {
    label: 'Google',
    models: [
      { value: 'gemini-2.5-pro',        label: 'Gemini 2.5 Pro' },
      { value: 'gemini-2.0-flash',      label: 'Gemini 2.0 Flash (fast)' },
      { value: 'gemini-2.0-flash-lite', label: 'Gemini 2.0 Flash Lite (cheapest)' },
    ],
  },
  {
    label: 'Kimi / Moonshot',
    models: [
      { value: 'kimi-k2-0711-preview', label: 'Kimi K2 (Kimi 2.5, very cheap)' },
      { value: 'moonshot-v1-8k',       label: 'Moonshot v1 8k' },
      { value: 'moonshot-v1-32k',      label: 'Moonshot v1 32k' },
      { value: 'moonshot-v1-128k',     label: 'Moonshot v1 128k' },
    ],
  },
];

const ROLE_KEYS: { key: keyof ModelOverrides; label: string }[] = [
  { key: 'manager', label: 'Manager' },
  { key: 'cto', label: 'CTO' },
  { key: 'engineer_junior', label: 'Engineer (Junior)' },
  { key: 'engineer_intermediate', label: 'Engineer (Intermediate)' },
  { key: 'engineer_senior', label: 'Engineer (Senior)' },
];

const PROMPT_ROLE_KEYS: { key: keyof PromptOverrides; label: string }[] = [
  { key: 'manager', label: 'Manager' },
  { key: 'cto', label: 'CTO' },
  { key: 'engineer', label: 'Engineers (all tiers)' },
];

type AgentBuildTab = 'configure' | 'prompt-builder' | 'templates';

const TABS: { key: AgentBuildTab; label: string; icon: React.ReactNode }[] = [
  { key: 'configure', label: 'Configure', icon: <Cpu className="w-4 h-4" /> },
  { key: 'prompt-builder', label: 'Prompt Builder', icon: <Blocks className="w-4 h-4" /> },
  { key: 'templates', label: 'Templates', icon: <LayoutTemplate className="w-4 h-4" /> },
];

// ── Component ──────────────────────────────────────────────────────────

export function AgentBuildPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [activeTab, setActiveTab] = useState<AgentBuildTab>('configure');
  const [project, setProject] = useState<Project | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Form state
  const [modelOverrides, setModelOverrides] = useState<ModelOverrides>({});
  const [promptOverrides, setPromptOverrides] = useState<PromptOverrides>({});

  // ── Data loading ────────────────────────────────────────────────────
  const fetchAll = useCallback(async () => {
    if (!projectId) return;
    try {
      setIsLoading(true);
      const [proj, settings] = await Promise.all([
        getProject(projectId),
        getProjectSettings(projectId),
      ]);
      setProject(proj);
      setModelOverrides(settings.model_overrides || {});
      setPromptOverrides(settings.prompt_overrides || {});
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load agent configuration');
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // ── Save ────────────────────────────────────────────────────────────
  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId) return;
    setIsSaving(true);
    setError(null);
    setSuccess(null);
    try {
      await updateProjectSettings(projectId, {
        model_overrides: Object.keys(modelOverrides).length > 0 ? modelOverrides : null,
        prompt_overrides: Object.keys(promptOverrides).length > 0 ? promptOverrides : null,
      });
      setSuccess('Agent configuration saved.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save agent configuration');
    } finally {
      setIsSaving(false);
    }
  };

  // ── Loading / error states ──────────────────────────────────────────
  if (isLoading) {
    return (
      <AppLayout>
        <div className="flex flex-1 items-center justify-center">
          <Loader2 className="w-8 h-8 animate-spin text-[var(--color-primary)]" />
        </div>
      </AppLayout>
    );
  }

  if (!project) {
    return (
      <AppLayout>
        <div className="flex flex-1 items-center justify-center">
          <div className="text-center">
            <AlertCircle className="w-12 h-12 mx-auto text-[var(--color-danger)] mb-4" />
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Project not found</h2>
            <button
              onClick={() => navigate('/projects')}
              className="mt-4 text-[var(--color-primary)] hover:underline"
            >
              Back to Projects
            </button>
          </div>
        </div>
      </AppLayout>
    );
  }

  // ── Render ──────────────────────────────────────────────────────────
  return (
    <AppLayout>
      <div className="flex flex-1 flex-col min-h-0 overflow-hidden bg-[var(--app-bg)]">
        {/* Header + Tabs */}
        <div className="shrink-0 border-b border-[var(--border-color)] bg-[var(--surface-card)]">
          <div className="max-w-6xl mx-auto px-6 pt-5 pb-0">
            <div className="mb-4">
              <h1 className="text-xl font-semibold text-[var(--text-primary)]">Agent Build</h1>
              <p className="text-sm text-[var(--text-muted)]">
                Configure models, prompts, and agent templates for {project.name}
              </p>
            </div>
            <nav className="flex gap-1">
              {TABS.map((tab) => (
                <button
                  key={tab.key}
                  type="button"
                  onClick={() => setActiveTab(tab.key)}
                  className={`flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-t-lg border-b-2 transition-colors ${
                    activeTab === tab.key
                      ? 'border-[var(--color-primary)] text-[var(--color-primary)] bg-[var(--color-primary-light)]'
                      : 'border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)]'
                  }`}
                >
                  {tab.icon}
                  {tab.label}
                </button>
              ))}
            </nav>
          </div>
        </div>

        {/* Tab content */}
        <div className="flex-1 min-h-0 overflow-hidden">
          {activeTab === 'configure' && (
            <div className="h-full overflow-y-auto">
              <main className="max-w-4xl mx-auto px-6 py-8">
                {error && (
                  <Card className="mb-6 flex items-center gap-3 border-[var(--color-danger)]/20 bg-[var(--color-danger-light)] px-4 py-3 text-[var(--color-danger)]">
                    <AlertCircle className="w-5 h-5 flex-shrink-0" />
                    <span className="text-sm">{error}</span>
                    <button onClick={() => setError(null)} className="ml-auto">&times;</button>
                  </Card>
                )}
                {success && (
                  <Card className="mb-6 flex items-center gap-3 border-[var(--color-success)]/20 bg-[var(--color-success-light)] px-4 py-3 text-[var(--color-success)]">
                    <CheckCircle className="w-5 h-5 flex-shrink-0" />
                    <span className="text-sm">{success}</span>
                    <button onClick={() => setSuccess(null)} className="ml-auto">&times;</button>
                  </Card>
                )}

                <form onSubmit={handleSave} className="space-y-8">

                  {/* ── Model Selection ── */}
                  <Card className="p-6">
                    <div className="flex items-center gap-2 mb-1">
                      <Cpu className="w-5 h-5 text-[var(--text-muted)]" />
                      <h2 className="text-lg font-semibold text-[var(--text-primary)]">Model Selection</h2>
                    </div>
                    <p className="text-sm text-[var(--text-muted)] mb-4">
                      Override the default model for each agent role. Select "— global default —" to inherit
                      from server config.
                    </p>
                    <div className="space-y-3">
                      {ROLE_KEYS.map(({ key, label }) => (
                        <div key={key}>
                          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">{label}</label>
                          <select
                            value={modelOverrides[key] || ''}
                            onChange={(e) =>
                              setModelOverrides((prev) => ({
                                ...prev,
                                [key]: e.target.value || undefined,
                              }))
                            }
                            className="w-full rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] px-3 py-2 text-sm text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-primary)]"
                          >
                            <option value="">— global default —</option>
                            {MODEL_GROUPS.map((group) => (
                              <optgroup key={group.label} label={group.label}>
                                {group.models.map((m) => (
                                  <option key={m.value} value={m.value}>
                                    {m.label}
                                  </option>
                                ))}
                              </optgroup>
                            ))}
                          </select>
                        </div>
                      ))}
                    </div>
                  </Card>

                  {/* ── Prompt Customization ── */}
                  <Card className="p-6">
                    <div className="flex items-center gap-2 mb-1">
                      <MessageSquare className="w-5 h-5 text-[var(--text-muted)]" />
                      <h2 className="text-lg font-semibold text-[var(--text-primary)]">Prompt Customization</h2>
                    </div>
                    <p className="text-sm text-[var(--text-muted)] mb-4">
                      Add project-specific instructions appended to each role's system prompt.
                      Maximum 2,000 characters per role.
                    </p>
                    <div className="space-y-4">
                      {PROMPT_ROLE_KEYS.map(({ key, label }) => (
                        <div key={key}>
                          <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">{label}</label>
                          <Textarea
                            value={promptOverrides[key] || ''}
                            onChange={(e) =>
                              setPromptOverrides((prev) => ({
                                ...prev,
                                [key]: e.target.value || undefined,
                              }))
                            }
                            rows={3}
                            placeholder={`Additional instructions for ${label.toLowerCase()}…`}
                            maxLength={2000}
                          />
                          <p className="text-xs text-[var(--text-muted)] text-right mt-0.5">
                            {(promptOverrides[key] || '').length}/2000
                          </p>
                        </div>
                      ))}
                    </div>
                  </Card>

                  <div className="flex justify-end">
                    <Button type="submit" disabled={isSaving} className="px-6">
                      {isSaving ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Save className="w-4 h-4" />
                      )}
                      Save Changes
                    </Button>
                  </div>
                </form>
              </main>
            </div>
          )}

          {activeTab === 'prompt-builder' && projectId && (
            <PromptBuilderPage projectId={projectId} />
          )}

          {activeTab === 'templates' && projectId && (
            <div className="h-full overflow-y-auto">
              <main className="max-w-4xl mx-auto px-6 py-8">
                <AgentTemplatesSection projectId={projectId} />
              </main>
            </div>
          )}
        </div>
      </div>
    </AppLayout>
  );
}

export default AgentBuildPage;
