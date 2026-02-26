/**
 * useTasks Hook
 * Manages task state with real-time updates
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import type { Task, TaskCreate, TaskUpdate, TaskStatus } from '../types';
import * as api from '../api/client';
import { useWebSocket } from './useWebSocket';

interface UseTasksReturn {
  tasks: Task[];
  tasksByStatus: Record<TaskStatus, Task[]>;
  isLoading: boolean;
  error: Error | null;
  createTask: (task: TaskCreate) => Promise<Task>;
  updateTask: (taskId: string, update: TaskUpdate) => Promise<Task>;
  deleteTask: (taskId: string) => Promise<void>;
  refreshTasks: () => Promise<void>;
}

const TASK_STATUSES: TaskStatus[] = [
  'backlog',
  'specifying',
  'assigned',
  'in_progress',
  'review',
  'done',
  'aborted',
];

export function useTasks(projectId: string | null): UseTasksReturn {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<Error | null>(null);

  const { subscribe } = useWebSocket(projectId);

  // Fetch tasks
  const refreshTasks = useCallback(async () => {
    if (!projectId) return;

    setIsLoading(true);
    setError(null);

    try {
      const fetchedTasks = await api.getTasks(projectId);
      setTasks(fetchedTasks);
    } catch (err) {
      setError(err instanceof Error ? err : new Error('Failed to fetch tasks'));
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  // Initial fetch
  useEffect(() => {
    refreshTasks();
  }, [refreshTasks]);

  // Subscribe to real-time updates
  useEffect(() => {
    if (!projectId) return;

    const unsubscribeCreated = subscribe<Task>('task_created', (task) => {
      setTasks((prev) => {
        if (prev.some((existing) => existing.id === task.id)) {
          return prev;
        }
        return [...prev, task];
      });
    });

    const unsubscribeUpdated = subscribe<Task>('task_update', (updatedTask) => {
      setTasks((prev) => {
        const hasExisting = prev.some((task) => task.id === updatedTask.id);
        if (!hasExisting) {
          return [...prev, updatedTask];
        }
        return prev.map((task) => (task.id === updatedTask.id ? updatedTask : task));
      });
    });

    return () => {
      unsubscribeCreated();
      unsubscribeUpdated();
    };
  }, [projectId, subscribe]);

  // Group tasks by status
  const tasksByStatus = useMemo(() => {
    const grouped: Record<TaskStatus, Task[]> = {
      backlog: [],
      specifying: [],
      assigned: [],
      in_progress: [],
      review: [],
      done: [],
      aborted: [],
    };

    for (const task of tasks) {
      if (grouped[task.status]) {
        grouped[task.status].push(task);
      }
    }

    // Sort tasks within each status by priority (critical + urgent)
    for (const status of TASK_STATUSES) {
      grouped[status].sort((a, b) => {
        const priorityA = a.critical + a.urgent;
        const priorityB = b.critical + b.urgent;
        return priorityA - priorityB; // Lower = higher priority
      });
    }

    return grouped;
  }, [tasks]);

  // Create task
  const createTask = useCallback(
    async (taskData: TaskCreate): Promise<Task> => {
      if (!projectId) throw new Error('No project selected');

      const newTask = await api.createTask(projectId, taskData);
      setTasks((prev) => {
        if (prev.some((task) => task.id === newTask.id)) {
          return prev;
        }
        return [...prev, newTask];
      });
      return newTask;
    },
    [projectId]
  );

  // Update task
  const updateTask = useCallback(
    async (taskId: string, update: TaskUpdate): Promise<Task> => {
      if (!projectId) throw new Error('No project selected');

      const updatedTask = await api.updateTask(taskId, update);
      setTasks((prev) => {
        const hasExisting = prev.some((task) => task.id === taskId);
        if (!hasExisting) {
          return [...prev, updatedTask];
        }
        return prev.map((task) => (task.id === taskId ? updatedTask : task));
      });
      return updatedTask;
    },
    [projectId]
  );

  // Delete task
  const deleteTask = useCallback(
    async (taskId: string): Promise<void> => {
      if (!projectId) throw new Error('No project selected');

      await api.deleteTask(taskId);
      // Optimistic update
      setTasks((prev) => prev.filter((task) => task.id !== taskId));
    },
    [projectId]
  );

  return {
    tasks,
    tasksByStatus,
    isLoading,
    error,
    createTask,
    updateTask,
    deleteTask,
    refreshTasks,
  };
}

export default useTasks;
