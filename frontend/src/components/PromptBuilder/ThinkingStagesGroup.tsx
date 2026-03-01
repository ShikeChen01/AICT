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
  onEdit: (blockId: string) => void;
  onToggle: (blockId: string) => void;
}

export function ThinkingStagesGroup({
  blocks,
  thinkingEnabled,
  onEdit,
  onToggle,
}: ThinkingStagesGroupProps) {
  const [open, setOpen] = useState(false);

  const stageBlocks = blocks.filter((b) => THINKING_BLOCK_KEYS.has(b.block_key));
  if (stageBlocks.length === 0) return null;

  const fmtTokens = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`);

  return (
    <div className="border border-violet-200 rounded-lg overflow-hidden bg-violet-50/30">
      {/* Header */}
      <button
        type="button"
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-violet-50 transition-colors"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? (
          <ChevronDown className="w-4 h-4 text-violet-600 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-violet-600 flex-shrink-0" />
        )}
        <Brain className="w-3.5 h-3.5 text-violet-500 flex-shrink-0" />
        <span className="text-sm font-semibold text-violet-800">Thinking Stages</span>
        <span className="text-xs text-violet-600 ml-1">({stageBlocks.length})</span>
        <span className={`ml-auto text-xs px-1.5 py-0.5 rounded-full font-medium ${
          thinkingEnabled
            ? 'bg-violet-100 text-violet-700'
            : 'bg-gray-100 text-gray-500'
        }`}>
          {thinkingEnabled ? 'Active' : 'Disabled'}
        </span>
      </button>

      {/* Stage blocks */}
      {open && (
        <div className="border-t border-violet-200 divide-y divide-violet-100">
          {!thinkingEnabled && (
            <p className="px-3 py-2 text-xs text-violet-500 bg-violet-50/50">
              Enable thinking in Agent Config to activate these stages.
            </p>
          )}
          {stageBlocks.map((block) => {
            const tokens = estimateTokens(block.content);
            const isActiveStage = thinkingEnabled && block.enabled;
            return (
              <div
                key={block.id}
                className={`flex items-start gap-3 px-3 py-2.5 group cursor-pointer hover:bg-violet-50 transition-colors ${
                  isActiveStage ? '' : 'opacity-50'
                }`}
                onClick={() => onEdit(block.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === 'Enter' && onEdit(block.id)}
              >
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-medium ${isActiveStage ? 'text-gray-800' : 'text-gray-400'}`}>
                      {STAGE_LABELS[block.block_key] ?? block.block_key}
                    </span>
                    <span className="text-xs font-mono text-violet-600 tabular-nums">
                      ~{fmtTokens(tokens)} tok
                    </span>
                  </div>
                  <p className="text-xs text-violet-500 mt-0.5">
                    {STAGE_DESC[block.block_key]}
                  </p>
                </div>

                <div
                  className="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    type="button"
                    className="p-1 rounded hover:bg-violet-100 text-violet-600 transition-colors"
                    title={block.enabled ? 'Disable' : 'Enable'}
                    onClick={() => onToggle(block.id)}
                  >
                    {block.enabled ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                  </button>
                  <button
                    type="button"
                    className="p-1 rounded hover:bg-violet-100 text-violet-600 transition-colors"
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
