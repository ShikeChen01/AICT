/**
 * PromptBlockNode — Custom React Flow node for a single prompt block.
 *
 * Interaction callbacks (onEdit, onToggle, onMoveUp, onMoveDown) are read
 * from PromptBuilderContext rather than from node.data, avoiding stale-
 * closure issues with React Flow's internal node data memoization.
 *
 * Interactive elements use the React Flow "nopan nodrag" CSS classes to
 * prevent React Flow from interpreting pointer events on buttons as pan/drag
 * gestures. This is the officially supported approach — see:
 * https://reactflow.dev/learn/customization/custom-nodes#preventing-dragging-panning-on-elements
 */

import { memo, useContext, useCallback } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { ChevronUp, ChevronDown, Pencil, Eye, EyeOff } from 'lucide-react';
import { PromptBuilderContext } from './PromptBuilderPage';

// ── Block kind classification ──────────────────────────────────────────────

const SYSTEM_BLOCKS = new Set([
  'rules', 'history_rules', 'incoming_msg_rules', 'incoming_message_rules',
  'tool_result_rules', 'tool_io', 'memory', 'identity',
  'thinking_stage', 'execution_stage',
]);

const CONDITIONAL_BLOCKS = new Set([
  'loopback', 'end_solo_warning', 'summarization',
]);

function blockKind(key: string): 'system' | 'conditional' | 'conversation' {
  if (SYSTEM_BLOCKS.has(key)) return 'system';
  if (CONDITIONAL_BLOCKS.has(key)) return 'conditional';
  return 'conversation';
}

const KIND_STYLES = {
  system: {
    border: 'border-blue-300',
    bg: 'bg-blue-50',
    header: 'bg-blue-100 text-blue-800',
    badge: 'bg-blue-200 text-blue-700',
  },
  conditional: {
    border: 'border-amber-300',
    bg: 'bg-amber-50',
    header: 'bg-amber-100 text-amber-800',
    badge: 'bg-amber-200 text-amber-700',
  },
  conversation: {
    border: 'border-gray-300',
    bg: 'bg-gray-50',
    header: 'bg-gray-100 text-gray-700',
    badge: 'bg-gray-200 text-gray-600',
  },
};

const BLOCK_LABELS: Record<string, string> = {
  rules: 'Rules',
  history_rules: 'History Rules',
  incoming_msg_rules: 'Incoming Msg Rules',
  incoming_message_rules: 'Incoming Msg Rules',
  tool_result_rules: 'Tool Result Rules',
  tool_io: 'Tool I/O',
  memory: 'Memory',
  identity: 'Identity',
  thinking_stage: 'Thinking Stage',
  execution_stage: 'Execution Stage',
  loopback: 'Loopback',
  end_solo_warning: 'End Solo Warning',
  summarization: 'Summarization',
};

function blockLabel(key: string): string {
  return BLOCK_LABELS[key] ?? key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

// ── Node data interface ────────────────────────────────────────────────────

export interface PromptBlockNodeData {
  blockId: string;
  blockKey: string;
  content: string;
  position: number;
  enabled: boolean;
  isFirst: boolean;
  isLast: boolean;
}

// ── Component ──────────────────────────────────────────────────────────────

function PromptBlockNodeComponent({ data }: NodeProps) {
  const d = data as unknown as PromptBlockNodeData;
  const ctx = useContext(PromptBuilderContext);

  const kind = blockKind(d.blockKey);
  const styles = KIND_STYLES[kind];
  const preview = d.content.trim().slice(0, 72).replace(/\n/g, ' ');
  const hasMore = d.content.trim().length > 72;

  const onToggle = useCallback(() => ctx.onToggle(d.blockId), [ctx, d.blockId]);
  const onEdit = useCallback(() => ctx.onEdit(d.blockId), [ctx, d.blockId]);
  const onMoveUp = useCallback(() => { if (!d.isFirst) ctx.onMoveUp(d.blockId); }, [ctx, d.blockId, d.isFirst]);
  const onMoveDown = useCallback(() => { if (!d.isLast) ctx.onMoveDown(d.blockId); }, [ctx, d.blockId, d.isLast]);

  return (
    <div
      className={`
        rounded-lg border-2 shadow-sm w-64 transition-all duration-150
        ${styles.border} ${styles.bg}
        ${d.enabled ? '' : 'opacity-40'}
      `}
    >
      <Handle type="target" position={Position.Top} className="!bg-gray-400 !w-2 !h-2" />

      {/* Header row */}
      <div className={`flex items-center justify-between px-3 py-2 rounded-t-md ${styles.header}`}>
        <div className="flex items-center gap-2 min-w-0">
          <span className={`text-xs font-mono px-1.5 py-0.5 rounded ${styles.badge}`}>
            {kind[0].toUpperCase()}
          </span>
          <span className="text-sm font-semibold truncate">{blockLabel(d.blockKey)}</span>
        </div>

        {/* Toggle + Edit — "nopan nodrag" prevents React Flow from capturing */}
        <div className="nopan nodrag flex items-center gap-1 flex-shrink-0 ml-1">
          <button
            type="button"
            className="p-1 rounded hover:bg-black/10 transition-colors cursor-pointer"
            title={d.enabled ? 'Disable block' : 'Enable block'}
            onClick={onToggle}
          >
            {d.enabled
              ? <Eye className="w-3.5 h-3.5" />
              : <EyeOff className="w-3.5 h-3.5" />
            }
          </button>
          <button
            type="button"
            className="p-1 rounded hover:bg-black/10 transition-colors cursor-pointer"
            title="Edit block content"
            onClick={onEdit}
          >
            <Pencil className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Content preview */}
      <div className="px-3 py-2">
        <p className="text-xs text-gray-500 font-mono leading-relaxed line-clamp-2">
          {preview || <em className="text-gray-300">empty</em>}
          {hasMore ? '…' : ''}
        </p>
      </div>

      {/* Footer: reorder buttons — also "nopan nodrag" */}
      <div className="flex items-center justify-between px-3 pb-2">
        <span className="text-xs text-gray-400">pos {d.position}</span>
        <div className="nopan nodrag flex gap-0.5">
          <button
            type="button"
            className="p-1 rounded hover:bg-black/10 disabled:opacity-30 transition-colors cursor-pointer disabled:cursor-not-allowed"
            title="Move up"
            disabled={d.isFirst}
            onClick={onMoveUp}
          >
            <ChevronUp className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            className="p-1 rounded hover:bg-black/10 disabled:opacity-30 transition-colors cursor-pointer disabled:cursor-not-allowed"
            title="Move down"
            disabled={d.isLast}
            onClick={onMoveDown}
          >
            <ChevronDown className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      <Handle type="source" position={Position.Bottom} className="!bg-gray-400 !w-2 !h-2" />
    </div>
  );
}

export const PromptBlockNode = memo(PromptBlockNodeComponent);
export default PromptBlockNode;
