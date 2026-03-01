/**
 * RuntimeInjectionsGroup — collapsible section for conditional prompt blocks.
 *
 * These blocks are NOT included in the static system prompt. Instead they are
 * dynamically injected into the conversation messages by the agent loop at runtime:
 *   - loopback:        injected when the agent replies with text only (no tool calls)
 *   - end_solo_warning: injected when END is called alongside other tools
 *   - summarization:   injected when context pressure reaches ~70%
 *
 * Users can still edit their content (it IS stored in the DB and read by the loop).
 */

import { useState } from 'react';
import { ChevronRight, ChevronDown, Pencil, Eye, EyeOff, Zap } from 'lucide-react';
import type { PromptBlockConfig, BlockMetaInfo } from '../../types';
import { estimateTokens } from './ContextBudgetChart';

const CONDITIONAL_BLOCK_KEYS = new Set(['loopback', 'end_solo_warning', 'summarization']);

const TRIGGER_LABELS: Record<string, string> = {
  loopback: 'Injected when agent responds without tool calls',
  end_solo_warning: 'Injected when END is called with other tools',
  summarization: 'Injected when context window reaches ~70% capacity',
};

const BLOCK_LABELS: Record<string, string> = {
  loopback: 'Loopback',
  end_solo_warning: 'End Solo Warning',
  summarization: 'Summarization',
};

interface RuntimeInjectionsGroupProps {
  blocks: PromptBlockConfig[];
  blockRegistry: Record<string, BlockMetaInfo>;
  onEdit: (blockId: string) => void;
  onToggle: (blockId: string) => void;
}

export function RuntimeInjectionsGroup({
  blocks,
  blockRegistry,
  onEdit,
  onToggle,
}: RuntimeInjectionsGroupProps) {
  const [open, setOpen] = useState(false);

  const conditionalBlocks = blocks.filter((b) => CONDITIONAL_BLOCK_KEYS.has(b.block_key));
  if (conditionalBlocks.length === 0) return null;

  const fmtTokens = (n: number) => (n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`);

  return (
    <div className="border border-amber-200 rounded-lg overflow-hidden bg-amber-50/40">
      {/* Header */}
      <button
        type="button"
        className="w-full flex items-center gap-2 px-3 py-2.5 text-left hover:bg-amber-50 transition-colors"
        onClick={() => setOpen((o) => !o)}
      >
        {open ? (
          <ChevronDown className="w-4 h-4 text-amber-600 flex-shrink-0" />
        ) : (
          <ChevronRight className="w-4 h-4 text-amber-600 flex-shrink-0" />
        )}
        <Zap className="w-3.5 h-3.5 text-amber-500 flex-shrink-0" />
        <span className="text-sm font-semibold text-amber-800">Runtime Injections</span>
        <span className="text-xs text-amber-600 ml-1">({conditionalBlocks.length})</span>
        <span className="ml-auto text-xs text-amber-500">Dynamically inserted into messages</span>
      </button>

      {/* Rows */}
      {open && (
        <div className="border-t border-amber-200 divide-y divide-amber-100">
          {conditionalBlocks.map((block) => {
            const tokens = estimateTokens(block.content);
            const meta = blockRegistry[block.block_key];
            const maxChars = meta?.max_chars;
            return (
              <div
                key={block.id}
                className={`flex items-start gap-3 px-3 py-2.5 group cursor-pointer hover:bg-amber-50 transition-colors ${
                  block.enabled ? '' : 'opacity-50'
                }`}
                onClick={() => onEdit(block.id)}
                role="button"
                tabIndex={0}
                onKeyDown={(e) => e.key === 'Enter' && onEdit(block.id)}
              >
                {/* Label + trigger */}
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className={`text-sm font-medium ${block.enabled ? 'text-gray-800' : 'text-gray-400 line-through'}`}>
                      {BLOCK_LABELS[block.block_key] ?? block.block_key}
                    </span>
                    <span className="text-xs font-mono text-amber-600 tabular-nums">
                      ~{fmtTokens(tokens)} tok
                    </span>
                    {maxChars && (
                      <span className="text-xs text-gray-400">
                        / max {fmtTokens(Math.floor(maxChars / 4))} tok
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-amber-600 mt-0.5">
                    {TRIGGER_LABELS[block.block_key] ?? 'Runtime injected'}
                  </p>
                </div>

                {/* Actions */}
                <div
                  className="flex items-center gap-0.5 flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
                  onClick={(e) => e.stopPropagation()}
                >
                  <button
                    type="button"
                    className="p-1 rounded hover:bg-amber-100 text-amber-600 transition-colors"
                    title={block.enabled ? 'Disable' : 'Enable'}
                    onClick={() => onToggle(block.id)}
                  >
                    {block.enabled ? <Eye className="w-3.5 h-3.5" /> : <EyeOff className="w-3.5 h-3.5" />}
                  </button>
                  <button
                    type="button"
                    className="p-1 rounded hover:bg-amber-100 text-amber-600 transition-colors"
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
