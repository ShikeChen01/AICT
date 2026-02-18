/**
 * AgentNode Component
 * Custom node for agent visualization in the workflow graph
 */

import { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { User, Bot, Wrench } from 'lucide-react';
import type { AgentRole } from '../../types';

interface AgentNodeData {
  label: string;
  role: AgentRole;
  status: 'idle' | 'active' | 'completed';
}

const roleIcons: Record<AgentRole, React.ReactNode> = {
  manager: <User className="w-5 h-5" />,
  gm: <User className="w-5 h-5" />,
  cto: <Wrench className="w-5 h-5" />,
  engineer: <Bot className="w-5 h-5" />,
};

const roleColors: Record<AgentRole, string> = {
  manager: 'bg-purple-100 border-purple-400 text-purple-700',
  gm: 'bg-purple-100 border-purple-400 text-purple-700',
  cto: 'bg-cyan-100 border-cyan-400 text-cyan-700',
  engineer: 'bg-green-100 border-green-400 text-green-700',
};

const statusStyles: Record<string, string> = {
  idle: '',
  active: 'ring-2 ring-blue-500 ring-offset-2 animate-pulse',
  completed: 'ring-2 ring-green-500 ring-offset-2',
};

function AgentNodeComponent({ data }: NodeProps) {
  const nodeData = data as unknown as AgentNodeData;
  const { label, role, status } = nodeData;

  return (
    <div
      className={`
        px-4 py-3 rounded-lg border-2 shadow-sm min-w-[140px]
        transition-all duration-200 cursor-pointer
        ${roleColors[role]}
        ${statusStyles[status]}
        hover:shadow-md
      `}
    >
      <Handle type="target" position={Position.Top} className="!bg-gray-400" />
      
      <div className="flex items-center gap-2">
        <span className="flex-shrink-0">{roleIcons[role]}</span>
        <div className="flex flex-col">
          <span className="text-sm font-semibold">{label}</span>
          <span className="text-xs opacity-75 uppercase">{role}</span>
        </div>
      </div>

      {status === 'active' && (
        <div className="absolute -top-1 -right-1 w-3 h-3 bg-blue-500 rounded-full animate-ping" />
      )}

      <Handle type="source" position={Position.Bottom} className="!bg-gray-400" />
    </div>
  );
}

export const AgentNode = memo(AgentNodeComponent);
export default AgentNode;
