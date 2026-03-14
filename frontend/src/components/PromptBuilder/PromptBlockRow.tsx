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
    badge: 'bg-[var(--color-primary)]/15 text-[var(--color-primary)]',
    bar: 'bg-[var(--color-primary)]',
  },
  conditional: {
    badge: 'bg-[var(--color-warning)]/15 text-[var(--color-warning)]',
    bar: 'bg-[var(--color-warning)]',
  },
  conversation: {
    badge: 'bg-[var(--surface-muted)] text-[var(--text-muted)]',
    bar: 'bg-[var(--text-muted)]',
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
  mutationsDisabled?: boolean;
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
  mutationsDisabled = false,
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
          ? 'bg-[var(--surface-card)] border-[var(--border-color)] hover:border-[var(--border-color-hover)] hover:shadow-sm'
          : 'bg-[var(--surface-muted)] border-[var(--border-color-subtle)] opacity-50'
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
          <span className={`text-sm font-medium truncate ${block.enabled ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)] line-through'}`}>
            {blockLabel(block.block_key)}
          </span>
          <span className="text-xs font-mono text-[var(--text-muted)] tabular-nums flex-shrink-0">
            ~{fmtTokens(tokens)} tok
          </span>
        </div>
        {/* Proportional token bar */}
        <div className="mt-1 h-1 bg-[var(--surface-muted)] rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-300 ${styles.bar}`}
            style={{ width: `${barPct}%` }}
          />
        </div>
      </div>

      {/* Action buttons — stop propagation so they don't trigger row click/edit.
           Always visible for keyboard/screen-reader users via focus-within. */}
      <div
        className="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Reorder */}
        <button
          type="button"
          className="p-1 rounded hover:bg-[var(--surface-hover)] disabled:opacity-20 text-[var(--text-muted)] transition-colors"
          aria-label={`Move ${blockLabel(block.block_key)} up`}
          disabled={isFirst || mutationsDisabled}
          onClick={onMoveUp}
        >
          <ChevronUp className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
        <button
          type="button"
          className="p-1 rounded hover:bg-[var(--surface-hover)] disabled:opacity-20 text-[var(--text-muted)] transition-colors"
          aria-label={`Move ${blockLabel(block.block_key)} down`}
          disabled={isLast || mutationsDisabled}
          onClick={onMoveDown}
        >
          <ChevronDown className="w-3.5 h-3.5" aria-hidden="true" />
        </button>

        {/* Toggle enable/disable */}
        <button
          type="button"
          className="p-1 rounded hover:bg-[var(--surface-hover)] text-[var(--text-muted)] transition-colors disabled:opacity-50"
          aria-label={block.enabled ? `Disable ${blockLabel(block.block_key)}` : `Enable ${blockLabel(block.block_key)}`}
          disabled={mutationsDisabled}
          onClick={onToggle}
        >
          {block.enabled
            ? <Eye className="w-3.5 h-3.5" aria-hidden="true" />
            : <EyeOff className="w-3.5 h-3.5" aria-hidden="true" />
          }
        </button>

        {/* Edit */}
        <button
          type="button"
          className="p-1 rounded hover:bg-[var(--color-accent)]/10 text-[var(--color-accent)] transition-colors"
          aria-label={`Edit ${blockLabel(block.block_key)}`}
          onClick={onEdit}
        >
          <Pencil className="w-3.5 h-3.5" aria-hidden="true" />
        </button>
      </div>
    </div>
  );
}
