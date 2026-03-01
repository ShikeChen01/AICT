/**
 * PromptBlockRow — a single horizontal row representing one prompt block.
 *
 * Shows: kind badge, label, token count with proportional bar, enable/disable
 * toggle, edit button, and move-up/move-down reorder arrows.
 * Clicking the row (outside action buttons) opens the block editor.
 */

import { ChevronUp, ChevronDown, Pencil, Eye, EyeOff } from 'lucide-react';
import type { PromptBlockConfig, BlockMetaInfo } from '../../types';
import { estimateTokens } from './ContextBudgetChart';

// ── Block label / display name map ────────────────────────────────────────────

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

// ── Kind badge styles ─────────────────────────────────────────────────────────

const KIND_STYLES: Record<string, { badge: string; bar: string }> = {
  system: {
    badge: 'bg-blue-100 text-blue-700',
    bar: 'bg-blue-400',
  },
  conditional: {
    badge: 'bg-amber-100 text-amber-700',
    bar: 'bg-amber-400',
  },
  conversation: {
    badge: 'bg-gray-100 text-gray-600',
    bar: 'bg-gray-400',
  },
};

function kindInitial(kind: string) {
  return kind[0]?.toUpperCase() ?? '?';
}

// ── Component ─────────────────────────────────────────────────────────────────

interface PromptBlockRowProps {
  block: PromptBlockConfig;
  meta: BlockMetaInfo | undefined;
  totalSystemTokens: number;
  isFirst: boolean;
  isLast: boolean;
  onEdit: () => void;
  onToggle: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
}

export function PromptBlockRow({
  block,
  meta,
  totalSystemTokens,
  isFirst,
  isLast,
  onEdit,
  onToggle,
  onMoveUp,
  onMoveDown,
}: PromptBlockRowProps) {
  const kind = meta?.kind ?? 'system';
  const styles = KIND_STYLES[kind] ?? KIND_STYLES.system;
  const tokens = estimateTokens(block.content);
  const barPct = totalSystemTokens > 0 ? Math.min(100, (tokens / totalSystemTokens) * 100) : 0;

  const fmtTokens = (n: number) =>
    n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`;

  return (
    <div
      className={`
        group flex items-center gap-2 px-3 py-2 rounded-lg border transition-all cursor-pointer
        ${block.enabled
          ? 'bg-white border-gray-200 hover:border-gray-300 hover:shadow-sm'
          : 'bg-gray-50 border-gray-100 opacity-50'
        }
      `}
      onClick={onEdit}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => e.key === 'Enter' && onEdit()}
    >
      {/* Kind badge */}
      <span
        className={`text-xs font-mono font-semibold px-1.5 py-0.5 rounded flex-shrink-0 ${styles.badge}`}
        title={kind}
      >
        {kindInitial(kind)}
      </span>

      {/* Label + token bar */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center justify-between gap-2">
          <span className={`text-sm font-medium truncate ${block.enabled ? 'text-gray-800' : 'text-gray-400 line-through'}`}>
            {blockLabel(block.block_key)}
          </span>
          <span className="text-xs font-mono text-gray-400 tabular-nums flex-shrink-0">
            ~{fmtTokens(tokens)} tok
          </span>
        </div>
        {/* Proportional token bar */}
        <div className="mt-1 h-1 bg-gray-100 rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${styles.bar}`}
            style={{ width: `${barPct}%` }}
          />
        </div>
      </div>

      {/* Action buttons — stop propagation so they don't trigger row click/edit */}
      <div
        className="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Reorder */}
        <button
          type="button"
          className="p-1 rounded hover:bg-gray-100 disabled:opacity-20 text-gray-500 transition-colors"
          title="Move up"
          disabled={isFirst}
          onClick={onMoveUp}
        >
          <ChevronUp className="w-3.5 h-3.5" />
        </button>
        <button
          type="button"
          className="p-1 rounded hover:bg-gray-100 disabled:opacity-20 text-gray-500 transition-colors"
          title="Move down"
          disabled={isLast}
          onClick={onMoveDown}
        >
          <ChevronDown className="w-3.5 h-3.5" />
        </button>

        {/* Toggle enable/disable */}
        <button
          type="button"
          className="p-1 rounded hover:bg-gray-100 text-gray-500 transition-colors"
          title={block.enabled ? 'Disable block' : 'Enable block'}
          onClick={onToggle}
        >
          {block.enabled
            ? <Eye className="w-3.5 h-3.5" />
            : <EyeOff className="w-3.5 h-3.5" />
          }
        </button>

        {/* Edit */}
        <button
          type="button"
          className="p-1 rounded hover:bg-violet-50 text-violet-500 transition-colors"
          title="Edit block content"
          onClick={onEdit}
        >
          <Pencil className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
