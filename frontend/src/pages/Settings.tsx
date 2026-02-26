/**
 * Repository Settings Page — Phases 2, 3, 4
 *
 * Sections:
 *  1. General (name, description)
 *  2. Git Integration (repo URL)
 *  3. Agent Limits (max engineers)
 *  4. Model Selection (per-role model overrides — Phase 3)
 *  5. Prompt Customization (per-role prompt overrides — Phase 3)
 *  6. Token Budget & Usage (daily budget, rollup — Phase 4)
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import {
  ArrowLeft,
  GitBranch,
  Save,
  Loader2,
  AlertCircle,
  CheckCircle,
  Cpu,
  MessageSquare,
  BarChart2,
  Users,
} from 'lucide-react';
import {
  getProject,
  updateProject,
  getProjectSettings,
  updateProjectSettings,
  getProjectUsage,
} from '../api/client';
import type {
  Project,
  ProjectSettings,
  ModelOverrides,
  PromptOverrides,
  ProjectUsageResponse,
} from '../types';
import { Button, Card, Input, Textarea } from '../components/ui';

const MODEL_PRESETS = [
  'claude-sonnet-4-6',
  'claude-opus-4-6',
  'gpt-5.2',
  'gpt-4o',
  'gemini-2.0-flash',
  'gemini-2.5-pro',
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

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

export function SettingsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [project, setProject] = useState<Project | null>(null);
  const [ps, setPs] = useState<ProjectSettings | null>(null);
  const [usage, setUsage] = useState<ProjectUsageResponse | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // General form state
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [repoUrl, setRepoUrl] = useState('');

  // Agent limits
  const [maxEngineers, setMaxEngineers] = useState(5);

  // Phase 3: model overrides
  const [modelOverrides, setModelOverrides] = useState<ModelOverrides>({});

  // Phase 3: prompt overrides
  const [promptOverrides, setPromptOverrides] = useState<PromptOverrides>({});

  // Phase 4: daily token budget
  const [dailyTokenBudget, setDailyTokenBudget] = useState(0);

  const fetchAll = useCallback(async () => {
    if (!projectId) return;
    try {
      setIsLoading(true);
      const [proj, settings, usageData] = await Promise.all([
        getProject(projectId),
        getProjectSettings(projectId),
        getProjectUsage(projectId).catch(() => null),
      ]);
      setProject(proj);
      setPs(settings);
      setUsage(usageData);
      setName(proj.name);
      setDescription(proj.description || '');
      setRepoUrl(proj.code_repo_url || '');
      setMaxEngineers(settings.max_engineers);
      setModelOverrides(settings.model_overrides || {});
      setPromptOverrides(settings.prompt_overrides || {});
      setDailyTokenBudget(settings.daily_token_budget || 0);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings');
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !project) return;
    setIsSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const repoUpdates: Record<string, string | null> = {};
      if (name !== project.name) repoUpdates.name = name;
      if (description !== (project.description || '')) repoUpdates.description = description || null;
      if (repoUrl !== (project.code_repo_url || '')) repoUpdates.code_repo_url = repoUrl || null;
      if (Object.keys(repoUpdates).length > 0) {
        const updated = await updateProject(projectId, repoUpdates);
        setProject(updated);
      }

      const updatedSettings = await updateProjectSettings(projectId, {
        max_engineers: maxEngineers,
        model_overrides: Object.keys(modelOverrides).length > 0 ? modelOverrides : null,
        prompt_overrides: Object.keys(promptOverrides).length > 0 ? promptOverrides : null,
        daily_token_budget: dailyTokenBudget,
      });
      setPs(updatedSettings);
      setSuccess('Settings saved successfully');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
      </div>
    );
  }

  if (!project) {
    return (
      <div className="min-h-screen bg-[var(--app-bg)] flex items-center justify-center">
        <div className="text-center">
          <AlertCircle className="w-12 h-12 mx-auto text-red-500 mb-4" />
          <h2 className="text-lg font-semibold text-gray-900">Repository not found</h2>
          <button onClick={() => navigate('/repositories')} className="mt-4 text-blue-600 hover:text-blue-800">
            Back to Repositories
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      <header className="bg-[var(--surface-card)] border-b border-[var(--border-color)]">
        <div className="max-w-4xl mx-auto px-6 py-4 flex items-center gap-4">
          <button
            onClick={() => navigate(`/repository/${projectId}/workspace`)}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div>
            <h1 className="text-xl font-semibold text-gray-900">Repository Settings</h1>
            <p className="text-sm text-gray-500">{project.name}</p>
          </div>
        </div>
      </header>

      <main className="max-w-4xl mx-auto px-6 py-8">
        {error && (
          <Card className="mb-6 flex items-center gap-3 border-red-200 bg-red-50 px-4 py-3 text-red-700">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <span className="text-sm">{error}</span>
            <button onClick={() => setError(null)} className="ml-auto">&times;</button>
          </Card>
        )}
        {success && (
          <Card className="mb-6 flex items-center gap-3 border-green-200 bg-green-50 px-4 py-3 text-green-700">
            <CheckCircle className="w-5 h-5 flex-shrink-0" />
            <span className="text-sm">{success}</span>
            <button onClick={() => setSuccess(null)} className="ml-auto">&times;</button>
          </Card>
        )}

        <form onSubmit={handleSave} className="space-y-8">
          {/* ── General ── */}
          <Card className="p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">General</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Repository Name</label>
                <Input type="text" value={name} onChange={(e) => setName(e.target.value)} required />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
                <Textarea value={description} onChange={(e) => setDescription(e.target.value)} rows={3} />
              </div>
            </div>
          </Card>

          {/* ── Git ── */}
          <Card className="p-6">
            <div className="flex items-center gap-2 mb-4">
              <GitBranch className="w-5 h-5 text-gray-500" />
              <h2 className="text-lg font-semibold text-gray-900">Git Integration</h2>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Repository URL</label>
              <Input
                type="url"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/user/repo"
              />
              <p className="text-xs text-gray-500 mt-1">GitHub token is configured in User Settings.</p>
            </div>
          </Card>

          {/* ── Agent Limits ── */}
          <Card className="p-6">
            <div className="flex items-center gap-2 mb-4">
              <Users className="w-5 h-5 text-gray-500" />
              <h2 className="text-lg font-semibold text-gray-900">Agent Limits</h2>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Max Engineers <span className="text-gray-400 font-normal">(1–20)</span>
              </label>
              <Input
                type="number"
                value={maxEngineers}
                onChange={(e) => setMaxEngineers(Number(e.target.value))}
                min={1}
                max={20}
              />
              <p className="text-xs text-gray-500 mt-1">
                Maximum number of Engineer agents the Manager can spawn for this project.
              </p>
            </div>
          </Card>

          {/* ── Model Selection (Phase 3) ── */}
          <Card className="p-6">
            <div className="flex items-center gap-2 mb-1">
              <Cpu className="w-5 h-5 text-gray-500" />
              <h2 className="text-lg font-semibold text-gray-900">Model Selection</h2>
            </div>
            <p className="text-sm text-gray-500 mb-4">
              Override the default model for each agent role. Leave blank to use the global default.
            </p>
            <div className="space-y-3">
              {ROLE_KEYS.map(({ key, label }) => (
                <div key={key}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
                  <div className="flex gap-2">
                    <Input
                      type="text"
                      value={modelOverrides[key] || ''}
                      onChange={(e) =>
                        setModelOverrides((prev) => ({
                          ...prev,
                          [key]: e.target.value || undefined,
                        }))
                      }
                      placeholder="e.g. claude-sonnet-4-6 (leave blank for default)"
                      list={`model-presets-${key}`}
                      className="flex-1"
                    />
                    <datalist id={`model-presets-${key}`}>
                      {MODEL_PRESETS.map((m) => <option key={m} value={m} />)}
                    </datalist>
                    {modelOverrides[key] && (
                      <button
                        type="button"
                        onClick={() =>
                          setModelOverrides((prev) => {
                            const next = { ...prev };
                            delete next[key];
                            return next;
                          })
                        }
                        className="text-xs text-gray-400 hover:text-red-500 px-2"
                      >
                        clear
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </Card>

          {/* ── Prompt Customization (Phase 3) ── */}
          <Card className="p-6">
            <div className="flex items-center gap-2 mb-1">
              <MessageSquare className="w-5 h-5 text-gray-500" />
              <h2 className="text-lg font-semibold text-gray-900">Prompt Customization</h2>
            </div>
            <p className="text-sm text-gray-500 mb-4">
              Add project-specific instructions appended to each role's system prompt.
              Maximum 2,000 characters per role.
            </p>
            <div className="space-y-4">
              {PROMPT_ROLE_KEYS.map(({ key, label }) => (
                <div key={key}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
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
                  <p className="text-xs text-gray-400 text-right mt-0.5">
                    {(promptOverrides[key] || '').length}/2000
                  </p>
                </div>
              ))}
            </div>
          </Card>

          {/* ── Token Budget (Phase 4) ── */}
          <Card className="p-6">
            <div className="flex items-center gap-2 mb-1">
              <BarChart2 className="w-5 h-5 text-gray-500" />
              <h2 className="text-lg font-semibold text-gray-900">Token Budget &amp; Usage</h2>
            </div>
            <p className="text-sm text-gray-500 mb-4">
              Set a daily token limit (UTC). Agents will be halted once the budget is reached.
              Set to 0 for unlimited.
            </p>
            <div className="mb-6">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Daily Token Budget <span className="text-gray-400 font-normal">(0 = unlimited)</span>
              </label>
              <Input
                type="number"
                value={dailyTokenBudget}
                onChange={(e) => setDailyTokenBudget(Number(e.target.value))}
                min={0}
                step={1000}
              />
            </div>

            {usage && (
              <div>
                <h3 className="text-sm font-semibold text-gray-700 mb-3">Today's Usage</h3>
                <div className="grid grid-cols-3 gap-4 mb-4">
                  {[
                    { label: 'Input tokens', value: fmtTokens(usage.today.total_input_tokens) },
                    { label: 'Output tokens', value: fmtTokens(usage.today.total_output_tokens) },
                    { label: 'Total tokens', value: fmtTokens(usage.today.total_tokens) },
                  ].map(({ label, value }) => (
                    <div key={label} className="bg-gray-50 rounded-lg p-3 text-center">
                      <div className="text-lg font-semibold text-gray-900">{value}</div>
                      <div className="text-xs text-gray-500">{label}</div>
                    </div>
                  ))}
                </div>

                {usage.today.by_model.length > 0 && (
                  <div className="mb-4">
                    <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">By model</h4>
                    <div className="space-y-1">
                      {usage.today.by_model.map((row) => (
                        <div key={`${row.provider}-${row.model}`} className="flex items-center text-sm">
                          <span className="flex-1 text-gray-700 font-mono text-xs">{row.model}</span>
                          <span className="text-gray-500 text-xs mr-4">{row.calls} calls</span>
                          <span className="text-gray-700 text-xs">
                            {fmtTokens(row.input_tokens + row.output_tokens)} tokens
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {usage.recent_calls.length > 0 && (
                  <div>
                    <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Recent calls</h4>
                    <div className="overflow-auto max-h-40">
                      <table className="w-full text-xs text-gray-600">
                        <thead>
                          <tr className="border-b border-gray-200 text-gray-500">
                            <th className="text-left py-1 pr-3">Model</th>
                            <th className="text-right pr-3">In</th>
                            <th className="text-right pr-3">Out</th>
                            <th className="text-right">Time</th>
                          </tr>
                        </thead>
                        <tbody>
                          {usage.recent_calls.map((c) => (
                            <tr key={c.id} className="border-b border-gray-100">
                              <td className="font-mono py-1 pr-3">{c.model}</td>
                              <td className="text-right pr-3">{fmtTokens(c.input_tokens)}</td>
                              <td className="text-right pr-3">{fmtTokens(c.output_tokens)}</td>
                              <td className="text-right text-gray-400">
                                {new Date(c.created_at).toLocaleTimeString()}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            )}
          </Card>

          <div className="flex justify-end">
            <Button type="submit" disabled={isSaving} className="px-6">
              {isSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save Changes
            </Button>
          </div>
        </form>
      </main>
    </div>
  );
}

export default SettingsPage;
