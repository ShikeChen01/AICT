/**
 * TaskCard Component
 * Individual task card in the Kanban board
 */

import type { Task, TaskStatus } from '../../types';

interface TaskCardProps {
  task: Task;
  onStatusChange?: (taskId: string, newStatus: TaskStatus) => void;
  onClick?: (task: Task) => void;
}

function getPriorityColor(critical: number, urgent: number): string {
  const priority = critical + urgent;
  if (priority <= 4) return 'border-l-red-500';
  if (priority <= 8) return 'border-l-amber-500';
  if (priority <= 12) return 'border-l-yellow-500';
  return 'border-l-green-500';
}

function getPriorityLabel(critical: number, urgent: number): string {
  const priority = critical + urgent;
  if (priority <= 4) return 'Critical';
  if (priority <= 8) return 'High';
  if (priority <= 12) return 'Medium';
  return 'Low';
}

function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString([], { month: 'short', day: 'numeric' });
}

export function TaskCard({ task, onClick }: TaskCardProps) {
  const priorityColor = getPriorityColor(task.critical, task.urgent);
  const priorityLabel = getPriorityLabel(task.critical, task.urgent);

  return (
    <div
      onClick={() => onClick?.(task)}
      className={`bg-white rounded-lg shadow-sm border-l-4 ${priorityColor} p-4 cursor-pointer hover:shadow-md transition-shadow`}
    >
      {/* Title */}
      <h4 className="font-medium text-gray-900 mb-2 line-clamp-2">{task.title}</h4>

      {/* Description */}
      {task.description && (
        <p className="text-sm text-gray-600 mb-3 line-clamp-2">{task.description}</p>
      )}

      {/* Metadata */}
      <div className="flex flex-wrap gap-2 text-xs">
        {/* Priority badge */}
        <span
          className={`px-2 py-1 rounded-full font-medium ${
            priorityLabel === 'Critical'
              ? 'bg-red-100 text-red-700'
              : priorityLabel === 'High'
              ? 'bg-amber-100 text-amber-700'
              : priorityLabel === 'Medium'
              ? 'bg-yellow-100 text-yellow-700'
              : 'bg-green-100 text-green-700'
          }`}
        >
          {priorityLabel}
        </span>

        {/* Module path */}
        {task.module_path && (
          <span className="px-2 py-1 rounded-full bg-blue-100 text-blue-700">
            {task.module_path.split('/').pop()}
          </span>
        )}

        {/* PR URL */}
        {task.pr_url && (
          <a
            href={task.pr_url}
            target="_blank"
            rel="noopener noreferrer"
            onClick={(e) => e.stopPropagation()}
            className="px-2 py-1 rounded-full bg-purple-100 text-purple-700 hover:bg-purple-200"
          >
            PR
          </a>
        )}
      </div>

      {/* Footer */}
      <div className="flex items-center justify-between mt-3 pt-3 border-t border-gray-100 text-xs text-gray-500">
        <span>Created {formatDate(task.created_at)}</span>
        {task.assigned_agent_id && (
          <span className="flex items-center gap-1">
            <div className="w-4 h-4 rounded-full bg-green-500" />
            Assigned
          </span>
        )}
      </div>
    </div>
  );
}

export default TaskCard;
