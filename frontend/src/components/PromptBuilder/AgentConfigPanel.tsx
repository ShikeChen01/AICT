/**
 * AgentConfigPanel — floating card in the Prompt Builder that lets the user
 * configure model, provider, and thinking_enabled for the selected agent.
 * Calls PATCH /agents/{id} on every change.
 */

import { useState, useEffect, useCallback } from 'react';
import { Brain } from 'lucide-react';
import type { Agent, UpdateAgentRequest } from '../../types';
import { updateAgent } from '../../api/client';

// ── Model / Provider options (mirrors AgentTemplatesSection) ───────────────

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

const PROVIDER_OPTIONS = [
  { value: '', label: 'Auto (infer from model)' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'openai', label: 'OpenAI' },
  { value: 'google', label: 'Google' },
  { value: 'moonshot', label: 'Moonshot' },
];

interface AgentConfigPanelProps {
  agent: Agent;
  onAgentUpdated: (updated: Agent) => void;
}

export function AgentConfigPanel({ agent, onAgentUpdated }: AgentConfigPanelProps) {
  const [model, setModel] = useState(agent.model || '');
  const [provider, setProvider] = useState(agent.provider || '');
  const [thinking, setThinking] = useState(agent.thinking_enabled);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Sync state when a different agent is selected
  useEffect(() => {
    setModel(agent.model || '');
    setProvider(agent.provider || '');
    setThinking(agent.thinking_enabled);
    setError(null);
  }, [agent.id, agent.model, agent.provider, agent.thinking_enabled]);

  const save = useCallback(async (patch: UpdateAgentRequest) => {
    setSaving(true);
    setError(null);
    try {
      const updated = await updateAgent(agent.id, patch);
      onAgentUpdated(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  }, [agent.id, onAgentUpdated]);

  const handleModelChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const v = e.target.value;
    setModel(v);
    save({ model: v, provider: provider || null });
  };

  const handleProviderChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const v = e.target.value;
    setProvider(v);
    save({ model, provider: v || null });
  };

  const handleThinkingChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const v = e.target.checked;
    setThinking(v);
    save({ thinking_enabled: v });
  };

  return (
    <div className="bg-[var(--surface-card)] border border-[var(--border-color)] rounded-xl shadow-lg p-4 w-72 space-y-4">
      {/* Header */}
      <div className="flex items-center gap-2">
        <Brain className="w-4 h-4 text-violet-600" aria-hidden="true" />
        <div className="min-w-0">
          <p className="text-xs text-[var(--text-muted)] uppercase font-semibold tracking-wide">Agent Config</p>
          <p className="text-sm font-semibold text-[var(--text-primary)] truncate">{agent.display_name}</p>
        </div>
        {saving && (
          <span className="ml-auto text-xs text-[var(--text-muted)] animate-pulse" role="status">saving…</span>
        )}
      </div>

      {error && (
        <p className="text-xs text-[var(--color-danger)] bg-[var(--color-danger-light)] rounded px-2 py-1" role="alert">{error}</p>
      )}

      {/* Model */}
      <div>
        <label htmlFor="agent-config-model" className="block text-xs font-medium text-[var(--text-secondary)] mb-1">Model</label>
        <select
          id="agent-config-model"
          className="w-full text-sm border border-[var(--border-color)] rounded-lg px-2 py-1.5 bg-[var(--surface-card)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
          value={model}
          onChange={handleModelChange}
        >
          <option value="">— select model —</option>
          {MODEL_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {/* Provider */}
      <div>
        <label htmlFor="agent-config-provider" className="block text-xs font-medium text-[var(--text-secondary)] mb-1">Provider</label>
        <select
          id="agent-config-provider"
          className="w-full text-sm border border-[var(--border-color)] rounded-lg px-2 py-1.5 bg-[var(--surface-card)] text-[var(--text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)]"
          value={provider}
          onChange={handleProviderChange}
        >
          {PROVIDER_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {/* Thinking toggle */}
      <label className="flex items-center gap-3 cursor-pointer select-none">
        <div className="relative">
          <input
            type="checkbox"
            className="sr-only peer"
            checked={thinking}
            onChange={handleThinkingChange}
            aria-label="Enable thinking mode"
          />
          <div
            className={`w-9 h-5 rounded-full transition-colors ${thinking ? 'bg-[var(--color-accent)]' : 'bg-[var(--surface-muted)]'} peer-focus-visible:ring-2 peer-focus-visible:ring-[var(--color-accent)] peer-focus-visible:ring-offset-2`}
            aria-hidden="true"
          />
          <div
            className={`absolute top-0.5 left-0.5 w-4 h-4 bg-white rounded-full shadow transition-transform ${thinking ? 'translate-x-4' : ''}`}
            aria-hidden="true"
          />
        </div>
        <span className="text-sm text-[var(--text-secondary)]">Thinking enabled</span>
      </label>
    </div>
  );
}

export default AgentConfigPanel;
