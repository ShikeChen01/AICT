/**
 * BlockEditorPanel — slide-in right panel for editing a prompt block's
 * markdown content.
 *
 * Save: calls PUT /prompt-blocks/agents/{id}/blocks (full block list, updated content).
 * Reset: calls POST /prompt-blocks/agents/{id}/blocks/{blockId}/reset, then
 *        re-fetches the full block list from the server so the parent always
 *        has fresh data. Does NOT rely on the stale allBlocks snapshot.
 */

import { useState, useEffect } from 'react';
import { X, RotateCcw, Save, AlertCircle } from 'lucide-react';
import type { PromptBlockConfig, PromptBlockConfigItem } from '../../types';
import { saveAgentBlocks, resetAgentBlock, listAgentBlocks } from '../../api/client';

interface BlockEditorPanelProps {
  agentId: string;
  block: PromptBlockConfig | null;
  onClose: () => void;
  /** Called with the authoritative updated block list after save or reset. */
  onSaved: (updated: PromptBlockConfig[]) => void;
}

export function BlockEditorPanel({
  agentId,
  block,
  onClose,
  onSaved,
}: BlockEditorPanelProps) {
  const [content, setContent] = useState('');
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);

  // Sync local content state whenever the target block changes
  useEffect(() => {
    if (block) {
      setContent(block.content);
      setDirty(false);
      setError(null);
    }
  }, [block?.id, block?.content]);

  if (!block) return null;

  const labelText = block.block_key
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());

  // ── Save ──────────────────────────────────────────────────────────────────
  // Re-fetch blocks from the server so we never send a stale list (e.g. after a
  // reorder that returned new IDs). We update only the block matching by block_key.

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const fresh = await listAgentBlocks(agentId);
      const items: PromptBlockConfigItem[] = fresh.map((b) => ({
        block_key: b.block_key,
        content: b.block_key === block.block_key ? content : b.content,
        position: b.position,
        enabled: b.enabled,
      }));
      const updated = await saveAgentBlocks(agentId, items);
      onSaved(updated);
      setDirty(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to save');
    } finally {
      setSaving(false);
    }
  };

  // ── Reset ─────────────────────────────────────────────────────────────────
  //
  // After calling the reset endpoint we re-fetch the full block list from the
  // server instead of using the stale `allBlocks` snapshot. This guarantees the
  // parent receives authoritative data and avoids a double-fetch race.

  const handleReset = async () => {
    if (!confirm('Reset this block to its default content? Your edits will be lost.')) return;
    setResetting(true);
    setError(null);
    try {
      await resetAgentBlock(agentId, block.id);
      const fresh = await listAgentBlocks(agentId);
      onSaved(fresh);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reset');
    } finally {
      setResetting(false);
    }
  };

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <>
      {/* Backdrop — clicking it closes the panel */}
      <div
        className="fixed inset-0 bg-black/20 z-40"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="fixed right-0 top-0 h-full w-[480px] bg-[var(--surface-card)] shadow-2xl z-50 flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between px-5 py-4 border-b border-[var(--border-color)]">
          <div>
            <p className="text-xs text-[var(--text-muted)] uppercase font-semibold tracking-wide">
              Block Editor
            </p>
            <h2 className="text-base font-bold text-[var(--text-primary)]">{labelText}</h2>
            <p className="text-xs text-[var(--text-secondary)] font-mono">{block.block_key}</p>
          </div>
          <button
            type="button"
            className="p-2 rounded-lg hover:bg-[var(--surface-hover)] transition-colors"
            onClick={onClose}
            title="Close"
          >
            <X className="w-5 h-5 text-[var(--text-muted)]" />
          </button>
        </div>

        {error && (
          <div className="mx-5 mt-3 flex items-center gap-2 bg-[var(--color-danger-light)] border border-[var(--color-danger)]/20 text-[var(--color-danger)] text-sm rounded-lg px-3 py-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            {error}
          </div>
        )}

        {/* Textarea */}
        <div className="flex-1 p-5 overflow-hidden">
          <textarea
            className="w-full h-full resize-none font-mono text-sm text-[var(--text-primary)] border border-[var(--border-color)] bg-[var(--surface-muted)] rounded-lg p-3 focus:outline-none focus:ring-2 focus:ring-[var(--color-accent)] leading-relaxed"
            value={content}
            onChange={(e) => {
              setContent(e.target.value);
              setDirty(true);
            }}
            placeholder="Enter markdown content for this block…"
            spellCheck={false}
          />
        </div>

        {/* Footer actions */}
        <div className="px-5 py-4 border-t border-[var(--border-color)] flex items-center gap-3">
          <button
            type="button"
            className="flex items-center gap-2 px-3 py-2 text-sm text-[var(--text-secondary)] border border-[var(--border-color)] rounded-lg hover:bg-[var(--surface-hover)] disabled:opacity-50 transition-colors"
            onClick={handleReset}
            disabled={resetting || saving}
            title="Reset to default content from codebase"
          >
            <RotateCcw className={`w-4 h-4 ${resetting ? 'animate-spin' : ''}`} />
            {resetting ? 'Resetting…' : 'Reset to default'}
          </button>

          <button
            type="button"
            className={`
              ml-auto flex items-center gap-2 px-4 py-2 text-sm font-semibold rounded-lg transition-colors
              ${dirty && !saving
                ? 'bg-[var(--color-accent)] text-white hover:opacity-90'
                : 'bg-[var(--surface-muted)] text-[var(--text-muted)] cursor-default'
              }
            `}
            onClick={handleSave}
            disabled={!dirty || saving}
          >
            <Save className={`w-4 h-4 ${saving ? 'animate-pulse' : ''}`} />
            {saving ? 'Saving…' : 'Save'}
          </button>
        </div>
      </div>
    </>
  );
}

export default BlockEditorPanel;
