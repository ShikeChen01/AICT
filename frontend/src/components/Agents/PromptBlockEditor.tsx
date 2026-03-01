/**
 * Prompt Block Editor
 *
 * Lets users view, edit, reorder, duplicate, enable/disable, and reset
 * the prompt blocks of an agent. Changes are written back to the DB via the API.
 *
 * Usage:
 *   <PromptBlockEditor agentId={agent.id} baseRole="worker" />
 */

import { useState, useEffect, useCallback } from 'react';
import {
  GripVertical,
  ChevronDown,
  ChevronUp,
  Copy,
  RotateCcw,
  Trash2,
  Eye,
  EyeOff,
  Save,
  Loader2,
  Plus,
} from 'lucide-react';
import { listAgentBlocks, saveAgentBlocks, resetAgentBlock, getDefaultBlocks } from '../../api/client';
import type { PromptBlockConfig, PromptBlockConfigItem } from '../../types';
import { Button } from '../ui';

// ── Types ──────────────────────────────────────────────────────────────

type EditableBlock = PromptBlockConfigItem & {
  id: string; // original DB id (if loaded from DB) or temp id
  _tempId?: string; // for new duplicated blocks without a DB id yet
};

let _tempIdCounter = 0;
function newTempId() { return `temp-${++_tempIdCounter}`; }

function blockFromConfig(b: PromptBlockConfig): EditableBlock {
  return { id: b.id, block_key: b.block_key, content: b.content, position: b.position, enabled: b.enabled };
}

// ── BlockCard ─────────────────────────────────────────────────────────

interface BlockCardProps {
  block: EditableBlock;
  index: number;
  total: number;
  agentId: string;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onToggleEnabled: () => void;
  onContentChange: (content: string) => void;
  onDuplicate: () => void;
  onDelete: () => void;
  onReset: () => void;
  isNew: boolean;
}

function BlockCard({
  block,
  index,
  total,
  onMoveUp,
  onMoveDown,
  onToggleEnabled,
  onContentChange,
  onDuplicate,
  onDelete,
  onReset,
  isNew,
}: BlockCardProps) {
  const [expanded, setExpanded] = useState(false);

  const STAGE_KEYS = new Set(['thinking_stage', 'execution_stage']);
  const isStageBlock = STAGE_KEYS.has(block.block_key);

  return (
    <div className={`border rounded-lg overflow-hidden transition-opacity ${!block.enabled ? 'opacity-50' : ''}`}>
      <div className="flex items-center gap-2 px-3 py-2 bg-gray-50 border-b">
        {/* Drag handle placeholder */}
        <GripVertical className="w-4 h-4 text-gray-300 cursor-grab flex-shrink-0" />

        {/* Move up/down */}
        <div className="flex flex-col gap-0.5">
          <button
            type="button"
            onClick={onMoveUp}
            disabled={index === 0}
            className="text-gray-400 hover:text-gray-700 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronUp className="w-3 h-3" />
          </button>
          <button
            type="button"
            onClick={onMoveDown}
            disabled={index === total - 1}
            className="text-gray-400 hover:text-gray-700 disabled:opacity-30 disabled:cursor-not-allowed"
          >
            <ChevronDown className="w-3 h-3" />
          </button>
        </div>

        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono font-semibold text-gray-700">{block.block_key}</span>
            {isStageBlock && (
              <span className="text-xs bg-purple-100 text-purple-700 px-1.5 py-0.5 rounded">thinking</span>
            )}
            {isNew && (
              <span className="text-xs bg-yellow-100 text-yellow-700 px-1.5 py-0.5 rounded">duplicate</span>
            )}
          </div>
        </div>

        <div className="flex items-center gap-1.5 flex-shrink-0">
          <button
            type="button"
            onClick={onToggleEnabled}
            title={block.enabled ? 'Disable block' : 'Enable block'}
            className="text-gray-400 hover:text-gray-700"
          >
            {block.enabled ? <Eye className="w-4 h-4" /> : <EyeOff className="w-4 h-4" />}
          </button>
          <button
            type="button"
            onClick={onDuplicate}
            title="Duplicate block"
            className="text-gray-400 hover:text-blue-600"
          >
            <Copy className="w-4 h-4" />
          </button>
          {!isNew && (
            <button
              type="button"
              onClick={onReset}
              title="Reset to .md file default"
              className="text-gray-400 hover:text-orange-600"
            >
              <RotateCcw className="w-4 h-4" />
            </button>
          )}
          {isNew && (
            <button
              type="button"
              onClick={onDelete}
              title="Remove this block"
              className="text-gray-400 hover:text-red-600"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
          <button
            type="button"
            onClick={() => setExpanded(!expanded)}
            className="text-gray-400 hover:text-gray-700"
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="p-3">
          <textarea
            className="w-full border border-gray-300 rounded px-3 py-2 text-sm font-mono resize-y min-h-[150px] focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={block.content}
            onChange={(e) => onContentChange(e.target.value)}
          />
        </div>
      )}
    </div>
  );
}

// ── PromptBlockEditor ─────────────────────────────────────────────────

interface PromptBlockEditorProps {
  agentId: string;
  baseRole: 'manager' | 'cto' | 'worker';
}

export function PromptBlockEditor({ agentId, baseRole }: PromptBlockEditorProps) {
  const [blocks, setBlocks] = useState<EditableBlock[]>([]);
  const [originalBlocks, setOriginalBlocks] = useState<PromptBlockConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);

  const loadBlocks = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listAgentBlocks(agentId);
      setOriginalBlocks(data);
      setBlocks(data.map(blockFromConfig));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load blocks');
    } finally {
      setLoading(false);
    }
  }, [agentId]);

  useEffect(() => { loadBlocks(); }, [loadBlocks]);

  const move = (index: number, direction: -1 | 1) => {
    const newBlocks = [...blocks];
    const target = index + direction;
    if (target < 0 || target >= newBlocks.length) return;
    [newBlocks[index], newBlocks[target]] = [newBlocks[target], newBlocks[index]];
    setBlocks(newBlocks.map((b, i) => ({ ...b, position: i })));
  };

  const toggleEnabled = (index: number) => {
    setBlocks(blocks.map((b, i) => i === index ? { ...b, enabled: !b.enabled } : b));
  };

  const updateContent = (index: number, content: string) => {
    setBlocks(blocks.map((b, i) => i === index ? { ...b, content } : b));
  };

  const duplicate = (index: number) => {
    const source = blocks[index];
    const newBlock: EditableBlock = {
      ...source,
      id: newTempId(),
      _tempId: newTempId(),
      position: index + 1,
    };
    const newBlocks = [
      ...blocks.slice(0, index + 1),
      newBlock,
      ...blocks.slice(index + 1),
    ].map((b, i) => ({ ...b, position: i }));
    setBlocks(newBlocks);
  };

  const deleteBlock = (index: number) => {
    setBlocks(blocks.filter((_, i) => i !== index).map((b, i) => ({ ...b, position: i })));
  };

  const handleReset = async (index: number) => {
    const block = blocks[index];
    if (!block.id || block._tempId) return;
    try {
      const updated = await resetAgentBlock(agentId, block.id);
      setBlocks(blocks.map((b, i) => i === index ? blockFromConfig(updated) : b));
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Reset failed');
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    setSuccess(false);
    try {
      const payload: PromptBlockConfigItem[] = blocks.map((b, i) => ({
        block_key: b.block_key,
        content: b.content,
        position: i,
        enabled: b.enabled,
      }));
      const saved = await saveAgentBlocks(agentId, payload);
      setOriginalBlocks(saved);
      setBlocks(saved.map(blockFromConfig));
      setSuccess(true);
      setTimeout(() => setSuccess(false), 2000);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-gray-500 py-4">
        <Loader2 className="w-4 h-4 animate-spin" />
        <span>Loading blocks…</span>
      </div>
    );
  }

  const isNewBlock = (b: EditableBlock) => !!b._tempId;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-xs text-gray-500">
          {blocks.length} blocks • drag to reorder, click to expand and edit
        </p>
        <div className="flex gap-2">
          {error && <span className="text-xs text-red-600">{error}</span>}
          {success && <span className="text-xs text-green-600">Saved!</span>}
          <Button type="button" size="sm" onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            Save Blocks
          </Button>
        </div>
      </div>

      <div className="space-y-2">
        {blocks.map((block, index) => (
          <BlockCard
            key={block._tempId ?? block.id}
            block={block}
            index={index}
            total={blocks.length}
            agentId={agentId}
            onMoveUp={() => move(index, -1)}
            onMoveDown={() => move(index, 1)}
            onToggleEnabled={() => toggleEnabled(index)}
            onContentChange={(content) => updateContent(index, content)}
            onDuplicate={() => duplicate(index)}
            onDelete={() => deleteBlock(index)}
            onReset={() => handleReset(index)}
            isNew={isNewBlock(block)}
          />
        ))}
      </div>

      <p className="text-xs text-gray-400">
        Click <RotateCcw className="inline w-3 h-3" /> to reset a block to its .md file default.
        Click <Copy className="inline w-3 h-3" /> to duplicate a block (enables double-prompting).
        Click <EyeOff className="inline w-3 h-3" /> to disable without deleting.
      </p>
    </div>
  );
}
