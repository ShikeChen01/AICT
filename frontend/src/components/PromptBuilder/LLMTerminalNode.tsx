/**
 * LLMTerminalNode — terminal React Flow node at the bottom of the prompt chain.
 * Shows the LLM provider + model that will receive the assembled prompt.
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Zap } from 'lucide-react';

export interface LLMTerminalNodeData {
  model: string;
  provider: string | null;
  thinking_enabled: boolean;
}

function LLMTerminalNodeComponent({ data }: NodeProps) {
  const d = data as unknown as LLMTerminalNodeData;
  const providerLabel = d.provider
    ? d.provider.charAt(0).toUpperCase() + d.provider.slice(1)
    : 'Auto';

  return (
    <div className="rounded-xl border-2 border-violet-400 bg-violet-50 shadow-md w-64">
      <Handle
        type="target"
        position={Position.Top}
        className="!bg-violet-400 !w-2 !h-2"
      />

      <div className="flex items-center gap-3 px-4 py-3">
        <div className="flex-shrink-0 w-8 h-8 rounded-full bg-violet-200 flex items-center justify-center">
          <Zap className="w-4 h-4 text-violet-700" />
        </div>
        <div className="min-w-0">
          <p className="text-xs font-semibold text-violet-700 uppercase tracking-wide">
            LLM Provider — {providerLabel}
          </p>
          <p className="text-sm font-mono text-violet-900 truncate">
            {d.model || 'no model selected'}
          </p>
          {d.thinking_enabled && (
            <p className="text-xs text-violet-500 mt-0.5">thinking enabled</p>
          )}
        </div>
      </div>
    </div>
  );
}

export const LLMTerminalNode = memo(LLMTerminalNodeComponent);
export default LLMTerminalNode;
