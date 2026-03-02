/**
 * AllocationEditor — inline panel for editing per-agent dynamic pool token allocations.
 *
 * Shown in the left column of PromptBuilderPage below the ContextBudgetChart.
 * Each row displays "computed tokens / total window" and an editable % or token count.
 * Saving calls PATCH /agents/{id} with { token_allocations: {...} }.
 * "Reset to defaults" sends an empty token_allocations to restore system constants.
 *
 * The image cap row (max_images_per_turn) is visible only for Claude models because
 * the backend only allows this override for Claude (1–20, validated server-side).
 */

import { useState, useEffect, useCallback } from 'react';
import { Pencil, RotateCcw, Check, X } from 'lucide-react';
import type { PromptMeta } from '../../types';
import { updateAgent } from '../../api/client';

interface AllocationEditorProps {
  agentId: string;
  meta: PromptMeta;
  model?: string;
  onSaved: () => void;
}

interface DraftAllocations {
  incoming_msg_tokens: number;
  memory_pct: number;
  past_session_pct: number;
  current_session_pct: number;
  max_images_per_turn: number;
}

const fmt = (n: number) =>
  n >= 1_000_000
    ? `${(n / 1_000_000).toFixed(1)}M`
    : n >= 1000
    ? `${(n / 1000).toFixed(1)}k`
    : `${n}`;

function isClaude(model: string | undefined): boolean {
  if (!model) return false;
  const m = model.toLowerCase();
  return m.startsWith('claude-opus') || m.startsWith('claude-sonnet') || m.startsWith('claude-haiku');
}

export function AllocationEditor({ agentId, meta, model, onSaved }: AllocationEditorProps) {
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const showImageCap = meta.model_supports_vision && isClaude(model);

  const [draft, setDraft] = useState<DraftAllocations>({
    incoming_msg_tokens: meta.incoming_msg_budget_tokens,
    memory_pct: meta.memory_pct,
    past_session_pct: meta.past_session_pct,
    current_session_pct: meta.current_session_pct,
    max_images_per_turn: meta.image_effective_max_images,
  });

  // Sync draft when meta changes (e.g. after a save)
  useEffect(() => {
    setDraft({
      incoming_msg_tokens: meta.incoming_msg_budget_tokens,
      memory_pct: meta.memory_pct,
      past_session_pct: meta.past_session_pct,
      current_session_pct: meta.current_session_pct,
      max_images_per_turn: meta.image_effective_max_images,
    });
  }, [meta]);

  const isDefault =
    meta.incoming_msg_budget_tokens === meta.default_incoming_msg_tokens &&
    meta.memory_pct === meta.default_memory_pct &&
    meta.past_session_pct === meta.default_past_session_pct &&
    meta.current_session_pct === meta.default_current_session_pct &&
    meta.image_effective_max_images === meta.image_default_max_images;

  const totalDynPct = draft.memory_pct + draft.past_session_pct + draft.current_session_pct;
  const pctError = Math.abs(totalDynPct - 100) > 0.1;

  const handleSave = useCallback(async () => {
    if (pctError) return;
    setSaving(true);
    setError(null);
    try {
      const payload: Record<string, number> = {
        incoming_msg_tokens: draft.incoming_msg_tokens,
        memory_pct: draft.memory_pct,
        past_session_pct: draft.past_session_pct,
        current_session_pct: draft.current_session_pct,
      };
      if (showImageCap) {
        payload.max_images_per_turn = draft.max_images_per_turn;
      }
      await updateAgent(agentId, { token_allocations: payload });
      setEditing(false);
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  }, [agentId, draft, pctError, showImageCap, onSaved]);

  const handleReset = useCallback(async () => {
    setSaving(true);
    setError(null);
    try {
      await updateAgent(agentId, { token_allocations: null });
      setEditing(false);
      onSaved();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Reset failed');
    } finally {
      setSaving(false);
    }
  }, [agentId, onSaved]);

  const handleCancel = useCallback(() => {
    setDraft({
      incoming_msg_tokens: meta.incoming_msg_budget_tokens,
      memory_pct: meta.memory_pct,
      past_session_pct: meta.past_session_pct,
      current_session_pct: meta.current_session_pct,
      max_images_per_turn: meta.image_effective_max_images,
    });
    setError(null);
    setEditing(false);
  }, [meta]);

  const total = meta.context_window_tokens;
  // Estimated image reserve with current draft cap (for preview during edit)
  const draftImageReserve = showImageCap
    ? draft.max_images_per_turn * meta.image_tokens_per_image
    : meta.image_reserve_tokens;

  return (
    <div className="space-y-1">
      {/* Header row */}
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">
          Dynamic Pool ({fmt(meta.dynamic_pool_tokens)})
        </p>
        <div className="flex items-center gap-1">
          {!isDefault && !editing && (
            <button
              type="button"
              title="Reset allocations to system defaults"
              className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
              onClick={handleReset}
              disabled={saving}
            >
              <RotateCcw className="w-3 h-3" />
            </button>
          )}
          {!editing && (
            <button
              type="button"
              title="Edit allocations"
              className="p-1 rounded hover:bg-gray-100 text-gray-400 hover:text-violet-600 transition-colors"
              onClick={() => setEditing(true)}
            >
              <Pencil className="w-3 h-3" />
            </button>
          )}
          {editing && (
            <>
              <button
                type="button"
                title="Save"
                className="p-1 rounded hover:bg-green-50 text-green-600 transition-colors disabled:opacity-40"
                onClick={handleSave}
                disabled={saving || pctError}
              >
                <Check className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                title="Cancel"
                className="p-1 rounded hover:bg-gray-100 text-gray-400 transition-colors"
                onClick={handleCancel}
                disabled={saving}
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </>
          )}
        </div>
      </div>

      {error && (
        <p className="text-[10px] text-red-600 bg-red-50 rounded px-2 py-1">{error}</p>
      )}

      {/* Incoming messages (token count) */}
      <AllocationRow
        label="Incoming Msgs"
        computed={meta.incoming_msg_budget_tokens}
        total={total}
        unit="tokens"
        editing={editing}
        value={draft.incoming_msg_tokens}
        defaultValue={meta.default_incoming_msg_tokens}
        onChange={(v) => setDraft((d) => ({ ...d, incoming_msg_tokens: v }))}
        min={1000}
        max={32000}
        step={500}
      />

      {/* Image cap — Claude only */}
      {showImageCap && (
        <AllocationRow
          label="Image Cap"
          computed={draftImageReserve}
          total={total}
          unit="images"
          editing={editing}
          value={draft.max_images_per_turn}
          defaultValue={meta.image_default_max_images}
          onChange={(v) => setDraft((d) => ({ ...d, max_images_per_turn: Math.round(v) }))}
          min={1}
          max={20}
          step={1}
          hint={`${fmt(meta.image_tokens_per_image)} tok/img`}
        />
      )}

      {/* Memory % */}
      <AllocationRow
        label="Memory"
        computed={meta.memory_budget_tokens}
        total={total}
        unit="%"
        editing={editing}
        value={draft.memory_pct}
        defaultValue={meta.default_memory_pct}
        onChange={(v) => setDraft((d) => ({ ...d, memory_pct: v }))}
        min={1}
        max={50}
        step={1}
      />

      {/* Past sessions % */}
      <AllocationRow
        label="Past Sessions"
        computed={meta.past_session_budget_tokens}
        total={total}
        unit="%"
        editing={editing}
        value={draft.past_session_pct}
        defaultValue={meta.default_past_session_pct}
        onChange={(v) => setDraft((d) => ({ ...d, past_session_pct: v }))}
        min={1}
        max={50}
        step={1}
      />

      {/* Current session % */}
      <AllocationRow
        label="Current Session"
        computed={meta.current_session_budget_tokens}
        total={total}
        unit="%"
        editing={editing}
        value={draft.current_session_pct}
        defaultValue={meta.default_current_session_pct}
        onChange={(v) => setDraft((d) => ({ ...d, current_session_pct: v }))}
        min={10}
        max={95}
        step={1}
      />

      {/* Dynamic % sum validation */}
      {editing && (
        <div className={`text-[10px] text-right tabular-nums ${pctError ? 'text-red-500' : 'text-gray-400'}`}>
          Dynamic %: {totalDynPct.toFixed(1)}% {pctError ? '— must sum to 100%' : '✓'}
        </div>
      )}
    </div>
  );
}

// ── Individual row ─────────────────────────────────────────────────────────────

interface AllocationRowProps {
  label: string;
  computed: number;
  total: number;
  unit: '%' | 'tokens' | 'images';
  editing: boolean;
  value: number;
  defaultValue: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
  hint?: string;
}

function AllocationRow({
  label,
  computed,
  total,
  unit,
  editing,
  value,
  defaultValue,
  onChange,
  min,
  max,
  step,
  hint,
}: AllocationRowProps) {
  const isModified = value !== defaultValue;

  const fmt = (n: number) =>
    n >= 1_000_000
      ? `${(n / 1_000_000).toFixed(1)}M`
      : n >= 1000
      ? `${(n / 1000).toFixed(1)}k`
      : `${n}`;

  return (
    <div className="flex items-center justify-between text-xs gap-2">
      <span className={`text-gray-600 ${isModified && !editing ? 'font-medium text-violet-700' : ''}`}>
        {label}
        {unit === '%' && !editing && (
          <span className="text-gray-400 ml-1">({value.toFixed(0)}%)</span>
        )}
        {unit === 'images' && !editing && (
          <span className="text-gray-400 ml-1">({value} img)</span>
        )}
      </span>

      {editing ? (
        <div className="flex items-center gap-1 flex-shrink-0">
          <input
            type="number"
            min={min}
            max={max}
            step={step}
            value={value}
            onChange={(e) => onChange(Number(e.target.value))}
            className="w-16 text-right font-mono text-xs border border-gray-300 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-violet-400"
          />
          <span className="text-gray-400 text-[10px]">{unit}</span>
          {hint && <span className="text-gray-300 text-[10px]">{hint}</span>}
        </div>
      ) : (
        <span className="font-mono text-gray-700 tabular-nums flex-shrink-0">
          {unit === 'images' ? `${fmt(computed)} rsv` : `${fmt(computed)} / ${fmt(total)}`}
        </span>
      )}
    </div>
  );
}
