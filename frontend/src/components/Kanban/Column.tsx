/**
 * Column Component
 * Single column in the Kanban board
 */

import type { Task, TaskStatus } from '../../types';
import { TaskCard } from './TaskCard';

interface ColumnProps {
  status: TaskStatus;
  tasks: Task[];
  agentNameById?: Record<string, string>;
  onTaskClick?: (task: Task) => void;
  onTaskStatusChange?: (taskId: string, newStatus: TaskStatus) => void;
}

const STATUS_CONFIG: Record<TaskStatus, { label: string; color: string; bgColor: string }> = {
  backlog: { label: 'Backlog', color: 'text-gray-700', bgColor: 'bg-gray-100' },
  specifying: { label: 'Specifying', color: 'text-purple-700', bgColor: 'bg-purple-100' },
  assigned: { label: 'Assigned', color: 'text-blue-700', bgColor: 'bg-blue-100' },
  in_progress: { label: 'In Progress', color: 'text-amber-700', bgColor: 'bg-amber-100' },
  in_review: { label: 'In Review', color: 'text-cyan-700', bgColor: 'bg-cyan-100' },
  done: { label: 'Done', color: 'text-green-700', bgColor: 'bg-green-100' },
  aborted: { label: 'Aborted', color: 'text-red-700', bgColor: 'bg-red-100' },
};

export function Column({
  status,
  tasks,
  agentNameById,
  onTaskClick,
  onTaskStatusChange,
}: ColumnProps) {
  const config = STATUS_CONFIG[status];

  return (
    <div className="flex flex-col bg-gray-50 rounded-xl min-w-[300px] max-w-[300px]">
      {/* Column header */}
      <div className="p-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className={`px-3 py-1 rounded-full text-sm font-medium ${config.bgColor} ${config.color}`}>
            {config.label}
          </span>
          <span className="text-sm text-gray-500">({tasks.length})</span>
        </div>
      </div>

      {/* Task list */}
      <div className="flex-1 p-2 space-y-3 overflow-y-auto min-h-[200px] max-h-[calc(100vh-220px)]">
        {tasks.length === 0 ? (
          <div className="flex items-center justify-center h-24 text-gray-400 text-sm">
            No tasks
          </div>
        ) : (
          tasks.map((task) => (
            <TaskCard
              key={task.id}
              task={task}
              assignedAgentName={task.assigned_agent_id ? agentNameById?.[task.assigned_agent_id] : null}
              onClick={onTaskClick}
              onStatusChange={onTaskStatusChange}
            />
          ))
        )}
      </div>
    </div>
  );
}

export default Column;
