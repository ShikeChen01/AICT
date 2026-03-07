/**
 * ThinkingStagesGroup — collapsible section for thinking_stage and execution_stage blocks.
 *
 * These blocks are mutually exclusive at runtime: only the block matching the
 * current thinking stage is included in the system prompt. Which stage is
 * active is controlled by agent.thinking_enabled:
 *   - thinking_enabled=false → both excluded (normal loop)
 *   - thinking_enabled=true  → thinking_stage active first, then execution_stage
 *                              after the agent calls thinking_done
 */

import { useState } from 'react';
import { ChevronRight, ChevronDown, Pencil, Eye, EyeOff, Brain } from 'lucide-react';
import type { PromptBlockConfig } from '../../types';
import { estimateTokens } from './ContextBudgetChart';

const THINKING_BLOCK_KEYS = new Set(['thinking_stage', 'execution_stage']);

const STAGE_LABELS: Record<string, string> = {
  thinking_stage: 'Thinking Stage',
  execution_stage: 'Execution Stage',
};

const STAGE_DESC: Record<string, string> = {
  thinking_stage: 'Active at loop start — agent plans without executing tools',
  execution_stage: 'Active after thinking_done — agent executes with full tool access',
};

interface ThinkingStagesGroupProps {
  blocks: PromptBlockConfig[];
  thinkingEnabled: boolean;
  mutationsDisabled?: boolean;
  onEdit: (blockId: string) => void;
  onToggle: (blockId: string) => void;
}

export function ThinkingStagesGroup({
  blocks,
  thinkingEnabled,
  mutationsDisabled = false,
  onEdit,
  onToggle,
}: ThinkingStagesGroupProps) {
  const [open, setOpen] = useState(false);

  const stageBlocks = blocks.filter((b) => THINKING_BLOCK_KEYS.has(b.block_key));
  if (stageBlocks.length === 0) return null;

  const fmtTokens = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`);

  return (
    <div className="border border-[var(--color-accent)]/20 rounded-lg overflow-hidden bg-[var(--color-accent)]/5">
      {/* Header */}
      <button
        type="button"
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-[var(--color-accent)]/10 transition-colors"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? (
          <ChevronDown className="w-4 h-4 text-[var(--color-accent)] flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-[var(--color-accent)] flex-shrink-0" />
        )}
        <Brain className="w-3.5 h-3.5 text-[var(--color-accent)] flex-shrink-0" />
        <span className="text-sm font-semibold text-[var(--color-accent)]">Thinking Stages</span>
        <span className="text-xs text-[var(--color-accent)] ml-1">({stageBlocks.length})</span>
        <span className={`ml-auto text-xs px-1.5 py-0.5 rounded-full font-medium ${
          thinkingEnabled
            ? 'bg-[var(--color-accent)]/15 text-[var(--color-accent)]'
            : 'bg-[var(--surface-muted)] text-[var(--text-muted)]'
        }`}>
          {thinkingEnabled ? 'Active' : 'Disabled'}
        </span>
      </button>

      {/* Stage blocks */}
      {open && (
        <div className="border-t border-[var(--color-accent)]/20 divide-y divide-[var(--color-accent)]/10">
          {!thinkingEnabled && (
            <p className="px-3 py-2 text-xs text-[var(--color-accent)] bg-[var(--color-accent)]/5">
              Enable thinking in Agent Config to activate these stages.
            </p>
          )}
          {stageBlocks.map((block) => {
            const tokens = estimateTokens(block.content);
            const isActiveStage = thinkingEnabled && block.enabled;
            return (
              <div
                key={block.id}
                className={`flex items-start gap-3 px-3 py-2.5 group cursor-pointer hover:bg-[var(--color-accent)]/10 transition-colors ${
                  isActiveStage ? '' : 'opacity-50'
                }`}
                onClick={() => onEdit(block.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === 'Enter' && onEdit(block.id)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-medium ${isActiveStage ? 'text-[var(--text-primary)]' : 'text-[var(--text-muted)]'}`}>
                      {STAGE_LABELS[block.block_key] ?? block.block_key}
                    </span>
                    <span className="text-xs font-mono text-[var(--color-accent)] tabular-nums">
                      ~{fmtTokens(tokens)} tok
                    </span>
                  </div>
                  <p className="text-xs text-[var(--color-accent)] mt-0.5">
                    {STAGE_DESC[block.block_key]}
                  </p>
                </div>

                <div
                  className="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    type="button"
                    className="p-1 rounded hover:bg-[var(--color-accent)]/15 text-[var(--color-accent)] transition-colors disabled:opacity-50"
                    title={block.enabled ? 'Disable' : 'Enable'}
                    disabled={mutationsDisabled}
                    onClick={() => onToggle(block.id)}
                  >
                    {block.enabled ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                  </button>
                  <button
                    type="button"
                    className="p-1 rounded hover:bg-[var(--color-accent)]/15 text-[var(--color-accent)] transition-colors"
                    title="Edit"
                    onClick={() => onEdit(block.id)}
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
