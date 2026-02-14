/**
 * KanbanBoard Component
 * Main Kanban board with all columns and task management
 */

import { useState, useCallback, useMemo } from 'react';
import type { Task, TaskStatus, TaskCreate, TaskUpdate } from '../../types';
import { useAgents, useTasks } from '../../hooks';
import { Column } from './Column';
import { TaskModal } from './TaskModal';
import { CreateTaskModal } from './CreateTaskModal';
import { TaskCard } from './TaskCard';

interface KanbanBoardProps {
  projectId: string;
}

const STATUSES: TaskStatus[] = [
  'backlog',
  'specifying',
  'assigned',
  'in_progress',
  'in_review',
  'done',
];

type BoardViewMode = 'status' | 'swimlane';

export function KanbanBoard({ projectId }: KanbanBoardProps) {
  const { tasks, tasksByStatus, isLoading, error, createTask, updateTask, deleteTask } = useTasks(projectId);
  const { agents } = useAgents(projectId);
  const [selectedTask, setSelectedTask] = useState<Task | null>(null);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [viewMode, setViewMode] = useState<BoardViewMode>('status');

  const agentNameById = useMemo(() => {
    return agents.reduce<Record<string, string>>((acc, agent) => {
      acc[agent.id] = agent.display_name;
      return acc;
    }, {});
  }, [agents]);

  const swimlaneColumns = useMemo(() => {
    const lanes = [
      { id: 'unassigned', display_name: 'Unassigned', role: 'none' },
      ...agents.map((agent) => ({
        id: agent.id,
        display_name: agent.display_name,
        role: agent.role,
      })),
    ];

    return lanes.map((lane) => {
      const laneTasks = tasks
        .filter((task) =>
          lane.id === 'unassigned'
            ? !task.assigned_agent_id
            : task.assigned_agent_id === lane.id
        )
        .sort((a, b) => {
          const statusIndex = STATUSES.indexOf(a.status) - STATUSES.indexOf(b.status);
          if (statusIndex !== 0) return statusIndex;
          return (a.critical + a.urgent) - (b.critical + b.urgent);
        });

      return {
        ...lane,
        tasks: laneTasks,
      };
    });
  }, [agents, tasks]);

  const handleTaskClick = useCallback((task: Task) => {
    setSelectedTask(task);
  }, []);

  const handleTaskUpdate = useCallback(
    async (taskId: string, update: TaskUpdate) => {
      await updateTask(taskId, update);
      setSelectedTask(null);
    },
    [updateTask]
  );

  const handleTaskDelete = useCallback(
    async (taskId: string) => {
      await deleteTask(taskId);
      setSelectedTask(null);
    },
    [deleteTask]
  );

  const handleTaskCreate = useCallback(
    async (taskData: TaskCreate) => {
      await createTask(taskData);
      setShowCreateModal(false);
    },
    [createTask]
  );

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="text-center text-gray-500">
          <svg
            className="animate-spin h-8 w-8 mx-auto mb-4 text-blue-500"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
              fill="none"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <p>Loading tasks...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-gray-100">
      {/* Header */}
      <header className="bg-white border-b border-gray-200 px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-gray-900">Kanban Board</h1>
          <p className="text-sm text-gray-500">Manage project tasks</p>
        </div>
        <div className="flex items-center gap-3">
          <div className="inline-flex rounded-lg border border-gray-200 bg-gray-50 p-1">
            <button
              type="button"
              onClick={() => setViewMode('status')}
              className={`px-3 py-1 text-sm rounded ${
                viewMode === 'status' ? 'bg-white shadow text-gray-900' : 'text-gray-600'
              }`}
            >
              Status View
            </button>
            <button
              type="button"
              onClick={() => setViewMode('swimlane')}
              className={`px-3 py-1 text-sm rounded ${
                viewMode === 'swimlane' ? 'bg-white shadow text-gray-900' : 'text-gray-600'
              }`}
            >
              Swimlane View
            </button>
          </div>

          <button
            onClick={() => setShowCreateModal(true)}
            className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            New Task
          </button>
        </div>
      </header>

      {/* Error banner */}
      {error && (
        <div className="bg-red-50 border-b border-red-200 px-6 py-3 text-red-700 text-sm">
          <strong>Error:</strong> {error.message}
        </div>
      )}

      {/* Board */}
      <div className="flex-1 overflow-x-auto p-6">
        {viewMode === 'status' ? (
          <div className="flex gap-4 h-full">
            {STATUSES.map((status) => (
              <Column
                key={status}
                status={status}
                tasks={tasksByStatus[status]}
                agentNameById={agentNameById}
                onTaskClick={handleTaskClick}
              />
            ))}
          </div>
        ) : (
          <div className="flex gap-4 h-full">
            {swimlaneColumns.map((lane) => (
              <section
                key={lane.id}
                className="flex flex-col bg-gray-50 rounded-xl min-w-[320px] max-w-[320px]"
              >
                <div className="p-4 border-b border-gray-200">
                  <p className="text-sm font-semibold text-gray-900">{lane.display_name}</p>
                  <p className="text-xs text-gray-500 uppercase">
                    {lane.role === 'none' ? 'unassigned' : lane.role} · {lane.tasks.length} task(s)
                  </p>
                </div>
                <div className="flex-1 p-2 space-y-3 overflow-y-auto min-h-[200px] max-h-[calc(100vh-260px)]">
                  {lane.tasks.length === 0 ? (
                    <div className="flex items-center justify-center h-24 text-gray-400 text-sm">
                      No tasks
                    </div>
                  ) : (
                    lane.tasks.map((task) => (
                      <TaskCard
                        key={task.id}
                        task={task}
                        assignedAgentName={
                          task.assigned_agent_id ? agentNameById[task.assigned_agent_id] : null
                        }
                        onClick={handleTaskClick}
                      />
                    ))
                  )}
                </div>
              </section>
            ))}
          </div>
        )}
      </div>

      {/* Task detail modal */}
      {selectedTask && (
        <TaskModal
          task={selectedTask}
          agents={agents}
          onClose={() => setSelectedTask(null)}
          onUpdate={handleTaskUpdate}
          onDelete={handleTaskDelete}
        />
      )}

      {/* Create task modal */}
      {showCreateModal && (
        <CreateTaskModal
          onClose={() => setShowCreateModal(false)}
          onCreate={handleTaskCreate}
        />
      )}
    </div>
  );
}

export default KanbanBoard;
