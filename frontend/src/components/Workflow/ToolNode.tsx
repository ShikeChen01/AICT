/**
 * ToolNode Component
 * Custom node for tool visualization in the workflow graph
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Cog } from 'lucide-react';

interface ToolNodeData {
  label: string;
}

function ToolNodeComponent({ data }: NodeProps) {
  const nodeData = data as unknown as ToolNodeData;
  const { label } = nodeData;

  return (
    <div
      className="
        px-3 py-2 rounded-md border-2 border-amber-400 bg-amber-50
        shadow-sm min-w-[100px] text-amber-700
      "
    >
      <Handle type="target" position={Position.Top} className="!bg-amber-400" />
      
      <div className="flex items-center gap-2">
        <Cog className="w-4 h-4 flex-shrink-0" />
        <span className="text-xs font-medium">{label}</span>
      </div>

      <Handle type="source" position={Position.Bottom} className="!bg-amber-400" />
    </div>
  );
}

export const ToolNode = memo(ToolNodeComponent);
export default ToolNode;
