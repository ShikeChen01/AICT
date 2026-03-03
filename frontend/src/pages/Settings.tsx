/**
 * Repository Settings Page — Phases 2, 3, 4 + 4b (rate limits + cost)
 *
 * Sections:
 *  1. General (name, description)
 *  2. Git Integration (repo URL)
 *  3. Agent Limits (max engineers)
 *  4. Model Selection (per-role model overrides — Phase 3)
 *  5. Prompt Customization (per-role prompt overrides — Phase 3)
 *  6. Rate Limits (calls/hour + tokens/hour — Phase 4b)
 *  7. Token Budget & Cost (daily token budget, daily cost budget, rollup — Phase 4/4b)
 *  8. Secrets (per-project tokens agents can read; enable "secrets" block in Prompt Builder)
 */

import { useState, useEffect, useCallback, useRef } from 'react';
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
  Users,
  Gauge,
  DollarSign,
  Key,
  Trash2,
  Upload,
  Monitor,
} from 'lucide-react';
import {
  getProject,
  updateProject,
  getProjectSettings,
  updateProjectSettings,
  getProjectUsage,
  listProjectSecrets,
  upsertProjectSecret,
  deleteProjectSecret,
} from '../api/client';
import type {
  Project,
  ProjectSecret,
  ProjectSettings,
  ModelOverrides,
  PromptOverrides,
  ProjectUsageResponse,
} from '../types';
import { Button, Card, Input, Textarea } from '../components/ui';
import { SandboxManager } from '../components/Sandbox/SandboxManager';

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

// ── Helpers ────────────────────────────────────────────────────────────

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`;
  return String(n);
}

function fmtCost(usd: number): string {
  if (usd === 0) return '$0.00';
  if (usd < 0.001) return `$${usd.toFixed(6)}`;
  if (usd < 0.01)  return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(4)}`;
}

/** Parse .env-style content into key-value pairs. Skips comments and empty lines. */
function parseEnvFile(content: string): { name: string; value: string }[] {
  const pairs: { name: string; value: string }[] = [];
  const lines = content.split(/\r?\n/);
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eq = trimmed.indexOf('=');
    if (eq <= 0) continue;
    const name = trimmed.slice(0, eq).trim();
    let value = trimmed.slice(eq + 1).trim();
    if (value.startsWith('"') && value.endsWith('"')) value = value.slice(1, -1);
    if (!name) continue;
    pairs.push({ name, value });
  }
  return pairs;
}

// ── Component ──────────────────────────────────────────────────────────

export function SettingsPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [project, setProject] = useState<Project | null>(null);
  const [, setPs] = useState<ProjectSettings | null>(null);
  const [usage, setUsage] = useState<ProjectUsageResponse | null>(null);

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // ── Form state ──────────────────────────────────────────────────────
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [repoUrl, setRepoUrl] = useState('');
  const [maxEngineers, setMaxEngineers] = useState(5);
  const [modelOverrides, setModelOverrides] = useState<ModelOverrides>({});
  const [promptOverrides, setPromptOverrides] = useState<PromptOverrides>({});
  // Rate limits
  const [callsPerHour, setCallsPerHour] = useState(0);
  const [tokensPerHour, setTokensPerHour] = useState(0);
  // Budgets
  const [dailyTokenBudget, setDailyTokenBudget] = useState(0);
  const [dailyCostBudget, setDailyCostBudget] = useState(0);
  // Secrets
  const [secrets, setSecrets] = useState<ProjectSecret[]>([]);
  const [secretName, setSecretName] = useState('');
  const [secretValue, setSecretValue] = useState('');
  const [secretsSaving, setSecretsSaving] = useState(false);
  // .env upload
  const [envPreview, setEnvPreview] = useState<{ count: number; names: string[]; pairs: { name: string; value: string }[] } | null>(null);
  const [envUploading, setEnvUploading] = useState(false);
  const envFileInputRef = useRef<HTMLInputElement>(null);

  // ── Data loading ────────────────────────────────────────────────────
  const fetchAll = useCallback(async () => {
    if (!projectId) return;
    try {
      setIsLoading(true);
      const [proj, settings, usageData, secretsList] = await Promise.all([
        getProject(projectId),
        getProjectSettings(projectId),
        getProjectUsage(projectId).catch(() => null),
        listProjectSecrets(projectId).catch(() => []),
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
      setCallsPerHour(settings.calls_per_hour_limit || 0);
      setTokensPerHour(settings.tokens_per_hour_limit || 0);
      setDailyTokenBudget(settings.daily_token_budget || 0);
      setDailyCostBudget(settings.daily_cost_budget_usd || 0);
      setSecrets(secretsList);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load settings');
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => { fetchAll(); }, [fetchAll]);

  // ── Save ────────────────────────────────────────────────────────────
  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId || !project) return;
    setIsSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const repoUpdates: Record<string, string | null> = {};
      if (name !== project.name) repoUpdates.name = name;
      if (description !== (project.description || ''))
        repoUpdates.description = description || null;
      if (repoUrl !== (project.code_repo_url || ''))
        repoUpdates.code_repo_url = repoUrl || null;
      if (Object.keys(repoUpdates).length > 0) {
        const updated = await updateProject(projectId, repoUpdates);
        setProject(updated);
      }

      const updatedSettings = await updateProjectSettings(projectId, {
        max_engineers: maxEngineers,
        model_overrides: Object.keys(modelOverrides).length > 0 ? modelOverrides : null,
        prompt_overrides: Object.keys(promptOverrides).length > 0 ? promptOverrides : null,
        calls_per_hour_limit: callsPerHour,
        tokens_per_hour_limit: tokensPerHour,
        daily_token_budget: dailyTokenBudget,
        daily_cost_budget_usd: dailyCostBudget,
      });
      setPs(updatedSettings);
      // Refresh usage after save (limits changed — active agents will pick up within 5s)
      getProjectUsage(projectId).then(setUsage).catch(() => null);
      setSuccess('Settings saved. Active agents will respect new limits within 5 seconds.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setIsSaving(false);
    }
  };

  // ── Loading / error states ──────────────────────────────────────────
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
          <button
            onClick={() => navigate('/repositories')}
            className="mt-4 text-blue-600 hover:text-blue-800"
          >
            Back to Repositories
          </button>
        </div>
      </div>
    );
  }

  // ── Derived values for usage display ──────────────────────────────
  const hourlyCallsUsed = usage?.last_hour.total_calls ?? 0;
  const hourlyTokensUsed = usage?.last_hour.total_tokens ?? 0;
  const callsPct = callsPerHour > 0 ? Math.min(100, (hourlyCallsUsed / callsPerHour) * 100) : 0;
  const tokensPct = tokensPerHour > 0 ? Math.min(100, (hourlyTokensUsed / tokensPerHour) * 100) : 0;
  const todayCost = usage?.today.estimated_cost_usd ?? 0;
  const costPct = dailyCostBudget > 0 ? Math.min(100, (todayCost / dailyCostBudget) * 100) : 0;

  // ── Render ──────────────────────────────────────────────────────────
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

          {/* ── 1. General ── */}
          <Card className="p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">General</h2>
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Repository Name
                </label>
                <Input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Description
                </label>
                <Textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  rows={3}
                />
              </div>
            </div>
          </Card>

          {/* ── 2. Git ── */}
          <Card className="p-6">
            <div className="flex items-center gap-2 mb-4">
              <GitBranch className="w-5 h-5 text-gray-500" />
              <h2 className="text-lg font-semibold text-gray-900">Git Integration</h2>
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Repository URL
              </label>
              <Input
                type="url"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/user/repo"
              />
              <p className="text-xs text-gray-500 mt-1">
                GitHub token is configured in User Settings.
              </p>
            </div>
          </Card>

          {/* ── 3. Agent Limits ── */}
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
                Maximum Engineer agents the Manager can spawn for this project.
              </p>
            </div>
          </Card>

          {/* ── 4. Model Selection ── */}
          <Card className="p-6">
            <div className="flex items-center gap-2 mb-1">
              <Cpu className="w-5 h-5 text-gray-500" />
              <h2 className="text-lg font-semibold text-gray-900">Model Selection</h2>
            </div>
            <p className="text-sm text-gray-500 mb-4">
              Override the default model for each agent role. Select "— global default —" to inherit
              from server config.
            </p>
            <div className="space-y-3">
              {ROLE_KEYS.map(({ key, label }) => (
                <div key={key}>
                  <label className="block text-sm font-medium text-gray-700 mb-1">{label}</label>
                  <select
                    value={modelOverrides[key] || ''}
                    onChange={(e) =>
                      setModelOverrides((prev) => ({
                        ...prev,
                        [key]: e.target.value || undefined,
                      }))
                    }
                    className="w-full rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] px-3 py-2 text-sm text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
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

          {/* ── 5. Prompt Customization ── */}
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

          {/* ── 6. Rate Limits ── */}
          <Card className="p-6">
            <div className="flex items-center gap-2 mb-1">
              <Gauge className="w-5 h-5 text-gray-500" />
              <h2 className="text-lg font-semibold text-gray-900">Rate Limits</h2>
            </div>
            <p className="text-sm text-gray-500 mb-5">
              Control the speed of agent LLM operations. When a limit is hit, the agent
              soft-pauses and polls every 5 seconds. Raising the limit here takes effect
              within one poll cycle — the agent resumes automatically without losing its
              session. Set to 0 to disable.
            </p>

            <div className="grid grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Calls / hour <span className="text-gray-400 font-normal">(0 = unlimited)</span>
                </label>
                <Input
                  type="number"
                  value={callsPerHour}
                  onChange={(e) => setCallsPerHour(Number(e.target.value))}
                  min={0}
                  step={10}
                />
                {usage && callsPerHour > 0 && (
                  <div className="mt-2">
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>Last 60 min: {hourlyCallsUsed.toLocaleString()} calls</span>
                      <span>{callsPerHour.toLocaleString()} limit</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                      <div
                        className={`h-1.5 rounded-full transition-all ${callsPct >= 90 ? 'bg-red-500' : callsPct >= 70 ? 'bg-amber-400' : 'bg-blue-500'}`}
                        style={{ width: `${callsPct}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Tokens / hour <span className="text-gray-400 font-normal">(0 = unlimited)</span>
                </label>
                <Input
                  type="number"
                  value={tokensPerHour}
                  onChange={(e) => setTokensPerHour(Number(e.target.value))}
                  min={0}
                  step={10000}
                />
                {usage && tokensPerHour > 0 && (
                  <div className="mt-2">
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>Last 60 min: {fmtTokens(hourlyTokensUsed)}</span>
                      <span>{fmtTokens(tokensPerHour)} limit</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                      <div
                        className={`h-1.5 rounded-full transition-all ${tokensPct >= 90 ? 'bg-red-500' : tokensPct >= 70 ? 'bg-amber-400' : 'bg-blue-500'}`}
                        style={{ width: `${tokensPct}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>

            {usage && (callsPerHour > 0 || tokensPerHour > 0) && (
              <p className="text-xs text-gray-400 mt-4">
                After 10 minutes of waiting (max pause), the agent ends its session. Send a new
                message once limits reset or are raised.
              </p>
            )}
          </Card>

          {/* ── 7. Token Budget & Cost ── */}
          <Card className="p-6">
            <div className="flex items-center gap-2 mb-1">
              <DollarSign className="w-5 h-5 text-gray-500" />
              <h2 className="text-lg font-semibold text-gray-900">Budget &amp; Cost</h2>
            </div>
            <p className="text-sm text-gray-500 mb-5">
              Set hard daily limits. When exhausted the agent session ends immediately.
              Costs are estimated using the pricing table in <code className="text-xs bg-gray-100 px-1 rounded">backend/config.py</code>.
            </p>

            <div className="grid grid-cols-2 gap-6 mb-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Daily token budget <span className="text-gray-400 font-normal">(0 = unlimited)</span>
                </label>
                <Input
                  type="number"
                  value={dailyTokenBudget}
                  onChange={(e) => setDailyTokenBudget(Number(e.target.value))}
                  min={0}
                  step={10000}
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Daily cost budget (USD) <span className="text-gray-400 font-normal">(0 = unlimited)</span>
                </label>
                <Input
                  type="number"
                  value={dailyCostBudget}
                  onChange={(e) => setDailyCostBudget(Number(e.target.value))}
                  min={0}
                  step={0.5}
                />
                {usage && dailyCostBudget > 0 && (
                  <div className="mt-2">
                    <div className="flex justify-between text-xs text-gray-500 mb-1">
                      <span>Today: {fmtCost(todayCost)}</span>
                      <span>{fmtCost(dailyCostBudget)} limit</span>
                    </div>
                    <div className="w-full bg-gray-100 rounded-full h-1.5">
                      <div
                        className={`h-1.5 rounded-full transition-all ${costPct >= 90 ? 'bg-red-500' : costPct >= 70 ? 'bg-amber-400' : 'bg-green-500'}`}
                        style={{ width: `${costPct}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Usage stats */}
            {usage && (
              <>
                {/* Today's rollup */}
                <h3 className="text-sm font-semibold text-gray-700 mb-3">Today's Usage</h3>
                <div className="grid grid-cols-4 gap-3 mb-5">
                  {[
                    { label: 'Input tokens',  value: fmtTokens(usage.today.total_input_tokens) },
                    { label: 'Output tokens', value: fmtTokens(usage.today.total_output_tokens) },
                    { label: 'Total tokens',  value: fmtTokens(usage.today.total_tokens) },
                    { label: 'Est. cost',     value: fmtCost(usage.today.estimated_cost_usd) },
                  ].map(({ label, value }) => (
                    <div key={label} className="bg-gray-50 rounded-lg p-3 text-center">
                      <div className="text-base font-semibold text-gray-900">{value}</div>
                      <div className="text-xs text-gray-500">{label}</div>
                    </div>
                  ))}
                </div>

                {/* Last-hour stats */}
                <h3 className="text-sm font-semibold text-gray-700 mb-3">Last 60 Minutes</h3>
                <div className="grid grid-cols-2 gap-3 mb-5">
                  {[
                    { label: 'Calls',  value: usage.last_hour.total_calls.toLocaleString() },
                    { label: 'Tokens', value: fmtTokens(usage.last_hour.total_tokens) },
                  ].map(({ label, value }) => (
                    <div key={label} className="bg-gray-50 rounded-lg p-3 text-center">
                      <div className="text-base font-semibold text-gray-900">{value}</div>
                      <div className="text-xs text-gray-500">{label}</div>
                    </div>
                  ))}
                </div>

                {/* Per-model breakdown */}
                {usage.today.by_model.length > 0 && (
                  <div className="mb-5">
                    <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                      By model — today
                    </h4>
                    <div className="overflow-auto">
                      <table className="w-full text-xs text-gray-600">
                        <thead>
                          <tr className="border-b border-gray-200 text-gray-500">
                            <th className="text-left py-1 pr-3">Model</th>
                            <th className="text-right pr-3">Calls</th>
                            <th className="text-right pr-3">Input</th>
                            <th className="text-right pr-3">Output</th>
                            <th className="text-right">Est. cost</th>
                          </tr>
                        </thead>
                        <tbody>
                          {usage.today.by_model.map((row) => (
                            <tr key={`${row.provider}-${row.model}`} className="border-b border-gray-100">
                              <td className="font-mono py-1 pr-3">{row.model}</td>
                              <td className="text-right pr-3">{row.calls}</td>
                              <td className="text-right pr-3">{fmtTokens(row.input_tokens)}</td>
                              <td className="text-right pr-3">{fmtTokens(row.output_tokens)}</td>
                              <td className="text-right text-green-700 font-medium">
                                {fmtCost(row.estimated_cost_usd)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                        <tfoot>
                          <tr className="text-gray-700 font-semibold border-t border-gray-300">
                            <td className="py-1 pr-3">Total</td>
                            <td />
                            <td className="text-right pr-3">{fmtTokens(usage.today.total_input_tokens)}</td>
                            <td className="text-right pr-3">{fmtTokens(usage.today.total_output_tokens)}</td>
                            <td className="text-right text-green-700">{fmtCost(usage.today.estimated_cost_usd)}</td>
                          </tr>
                        </tfoot>
                      </table>
                    </div>
                  </div>
                )}

                {/* Recent calls */}
                {usage.recent_calls.length > 0 && (
                  <div>
                    <h4 className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">
                      Recent calls
                    </h4>
                    <div className="overflow-auto max-h-48">
                      <table className="w-full text-xs text-gray-600">
                        <thead>
                          <tr className="border-b border-gray-200 text-gray-500">
                            <th className="text-left py-1 pr-3">Model</th>
                            <th className="text-right pr-3">In</th>
                            <th className="text-right pr-3">Out</th>
                            <th className="text-right pr-3">Cost</th>
                            <th className="text-right">Time</th>
                          </tr>
                        </thead>
                        <tbody>
                          {usage.recent_calls.map((c) => (
                            <tr key={c.id} className="border-b border-gray-100">
                              <td className="font-mono py-1 pr-3">{c.model}</td>
                              <td className="text-right pr-3">{fmtTokens(c.input_tokens)}</td>
                              <td className="text-right pr-3">{fmtTokens(c.output_tokens)}</td>
                              <td className="text-right pr-3 text-green-700">
                                {fmtCost(c.estimated_cost_usd)}
                              </td>
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
              </>
            )}
          </Card>

          {/* ── 8. Project secrets ── */}
          <Card className="p-6">
            <div className="flex items-center gap-2 mb-1">
              <Key className="w-5 h-5 text-gray-500" />
              <h2 className="text-lg font-semibold text-gray-900">Project secrets</h2>
            </div>
            <p className="text-sm text-gray-500 mb-4">
              Key-value secrets (e.g. API keys) that agents can read at runtime. Values are never shown after save.
              Enable the &quot;secrets&quot; block in Prompt Builder for each agent that should receive them.
            </p>

            <input
              ref={envFileInputRef}
              type="file"
              accept=".env,.env.development,.env.local,text/plain"
              className="hidden"
              onChange={async (e) => {
                const file = e.target.files?.[0];
                if (!file) return;
                try {
                  const text = await new Promise<string>((resolve, reject) => {
                    const r = new FileReader();
                    r.onload = () => resolve(String(r.result ?? ''));
                    r.onerror = () => reject(new Error('Failed to read file'));
                    r.readAsText(file);
                  });
                  const pairs = parseEnvFile(text);
                  if (pairs.length === 0) {
                    setError('No valid KEY=VALUE pairs found in file');
                    return;
                  }
                  setEnvPreview({
                    count: pairs.length,
                    names: pairs.map((p) => p.name),
                    pairs,
                  });
                  setError(null);
                } catch (err) {
                  setError(err instanceof Error ? err.message : 'Failed to parse .env file');
                }
                e.target.value = '';
              }}
            />

            <div className="space-y-4">
              <div className="flex flex-wrap gap-2 items-center">
                <Button
                  type="button"
                  variant="secondary"
                  disabled={secretsSaving || envUploading}
                  onClick={() => envFileInputRef.current?.click()}
                >
                  <Upload className="w-4 h-4" />
                  Upload .env file
                </Button>
                {envPreview && (
                  <>
                    <span className="text-sm text-gray-600">
                      Found {envPreview.count} variable{envPreview.count !== 1 ? 's' : ''}: {envPreview.names.slice(0, 5).join(', ')}
                      {envPreview.names.length > 5 ? ` …` : ''}
                    </span>
                    <Button
                      type="button"
                      disabled={!projectId || envUploading}
                      onClick={async () => {
                        if (!projectId || !envPreview.pairs.length) return;
                        setEnvUploading(true);
                        setError(null);
                        try {
                          for (const { name, value } of envPreview.pairs) {
                            const created = await upsertProjectSecret(projectId, { name, value });
                            setSecrets((prev) => {
                              const rest = prev.filter((s) => s.name !== created.name);
                              return [...rest, created].sort((a, b) => a.name.localeCompare(b.name));
                            });
                          }
                          setSuccess(`Imported ${envPreview.pairs.length} secret(s). Existing secrets with the same name were updated.`);
                          setEnvPreview(null);
                        } catch (err) {
                          setError(err instanceof Error ? err.message : 'Failed to import secrets');
                        } finally {
                          setEnvUploading(false);
                        }
                      }}
                    >
                      {envUploading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Add all'}
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      disabled={envUploading}
                      onClick={() => setEnvPreview(null)}
                    >
                      Cancel
                    </Button>
                  </>
                )}
              </div>
              {envPreview && (
                <p className="text-xs text-gray-500">
                  Existing secrets with the same name will be updated.
                </p>
              )}
              <div className="flex flex-wrap gap-2 items-end">
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Name</label>
                  <Input
                    value={secretName}
                    onChange={(e) => setSecretName(e.target.value)}
                    placeholder="e.g. GITHUB_TOKEN"
                    className="w-48"
                  />
                </div>
                <div>
                  <label className="block text-xs font-medium text-gray-500 mb-1">Value</label>
                  <Input
                    type="password"
                    value={secretValue}
                    onChange={(e) => setSecretValue(e.target.value)}
                    placeholder="••••••••"
                    className="w-56"
                  />
                </div>
                <Button
                  type="button"
                  disabled={!secretName.trim() || !secretValue.trim() || secretsSaving}
                  onClick={async () => {
                    if (!projectId || !secretName.trim() || !secretValue.trim()) return;
                    setSecretsSaving(true);
                    try {
                      const created = await upsertProjectSecret(projectId, {
                        name: secretName.trim(),
                        value: secretValue,
                      });
                      setSecrets((prev) => {
                        const rest = prev.filter((s) => s.name !== created.name);
                        return [...rest, created].sort((a, b) => a.name.localeCompare(b.name));
                      });
                      setSecretName('');
                      setSecretValue('');
                    } catch (err) {
                      setError(err instanceof Error ? err.message : 'Failed to save secret');
                    } finally {
                      setSecretsSaving(false);
                    }
                  }}
                >
                  {secretsSaving ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    'Add / Update'
                  )}
                </Button>
              </div>

              {secrets.length > 0 && (
                <div className="border border-gray-200 rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-gray-50">
                      <tr>
                        <th className="text-left py-2 px-3 font-medium text-gray-700">Name</th>
                        <th className="text-left py-2 px-3 font-medium text-gray-700">Hint</th>
                        <th className="w-10 py-2 px-2" />
                      </tr>
                    </thead>
                    <tbody>
                      {secrets.map((s) => (
                        <tr key={s.id} className="border-t border-gray-100 hover:bg-gray-50/50">
                          <td className="py-2 px-3 font-mono text-gray-900">{s.name}</td>
                          <td className="py-2 px-3 text-gray-500">
                            {s.hint ? `••••${s.hint}` : '—'}
                          </td>
                          <td className="py-2 px-2">
                            <button
                              type="button"
                              onClick={async () => {
                                if (!projectId) return;
                                try {
                                  await deleteProjectSecret(projectId, s.name);
                                  setSecrets((prev) => prev.filter((x) => x.id !== s.id));
                                } catch (err) {
                                  setError(err instanceof Error ? err.message : 'Failed to delete secret');
                                }
                              }}
                              className="p-1.5 text-gray-400 hover:text-red-600 rounded"
                              title="Delete"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
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

        {/* ── 9. Sandbox Management (outside form — has its own actions) ── */}
        <Card className="mt-8 p-6">
          <div className="flex items-center gap-2 mb-1">
            <Monitor className="w-5 h-5 text-gray-500" />
            <h2 className="text-lg font-semibold text-gray-900">Sandboxes</h2>
          </div>
          <p className="text-sm text-gray-500 mb-4">
            Manage sandbox containers for this project's agents. Persistent sandboxes
            survive session restarts — agents can install and use GUI applications long-term.
          </p>
          <SandboxManager projectId={projectId!} />
        </Card>

      </main>
    </div>
  );
}

export default SettingsPage;
