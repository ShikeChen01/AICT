/**
 * TaskModal Component
 * Modal for viewing and editing task details
 */

import { useState, useCallback } from 'react';
import type { Task, TaskStatus, TaskUpdate } from '../../types';

interface TaskModalProps {
  task: Task;
  onClose: () => void;
  onUpdate: (taskId: string, update: TaskUpdate) => Promise<void>;
  onDelete?: (taskId: string) => Promise<void>;
}

const STATUSES: { value: TaskStatus; label: string }[] = [
  { value: 'backlog', label: 'Backlog' },
  { value: 'specifying', label: 'Specifying' },
  { value: 'assigned', label: 'Assigned' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'in_review', label: 'In Review' },
  { value: 'done', label: 'Done' },
];

export function TaskModal({ task, onClose, onUpdate, onDelete }: TaskModalProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [editedTask, setEditedTask] = useState({
    title: task.title,
    description: task.description || '',
    status: task.status,
    critical: task.critical,
    urgent: task.urgent,
  });

  const handleSave = useCallback(async () => {
    setIsSaving(true);
    try {
      await onUpdate(task.id, {
        title: editedTask.title,
        description: editedTask.description || null,
        status: editedTask.status,
        critical: editedTask.critical,
        urgent: editedTask.urgent,
      });
      setIsEditing(false);
    } catch (error) {
      console.error('Failed to update task:', error);
    } finally {
      setIsSaving(false);
    }
  }, [task.id, editedTask, onUpdate]);

  const handleDelete = useCallback(async () => {
    if (!onDelete || !confirm('Are you sure you want to delete this task?')) return;
    
    try {
      await onDelete(task.id);
      onClose();
    } catch (error) {
      console.error('Failed to delete task:', error);
    }
  }, [task.id, onDelete, onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50"
        onClick={onClose}
      />

      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-xl max-w-2xl w-full mx-4 max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">Task Details</h2>
          <button
            onClick={onClose}
            className="p-2 text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-lg"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Content */}
        <div className="p-6 space-y-6">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Title</label>
            {isEditing ? (
              <input
                type="text"
                value={editedTask.title}
                onChange={(e) => setEditedTask((prev) => ({ ...prev, title: e.target.value }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            ) : (
              <p className="text-gray-900 font-medium">{task.title}</p>
            )}
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            {isEditing ? (
              <textarea
                value={editedTask.description}
                onChange={(e) => setEditedTask((prev) => ({ ...prev, description: e.target.value }))}
                rows={4}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            ) : (
              <p className="text-gray-600">{task.description || 'No description'}</p>
            )}
          </div>

          {/* Status */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
            {isEditing ? (
              <select
                value={editedTask.status}
                onChange={(e) => setEditedTask((prev) => ({ ...prev, status: e.target.value as TaskStatus }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              >
                {STATUSES.map((s) => (
                  <option key={s.value} value={s.value}>
                    {s.label}
                  </option>
                ))}
              </select>
            ) : (
              <span className="inline-block px-3 py-1 rounded-full bg-blue-100 text-blue-700 text-sm font-medium">
                {STATUSES.find((s) => s.value === task.status)?.label}
              </span>
            )}
          </div>

          {/* Priority */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Critical (0=most, 10=least)
              </label>
              {isEditing ? (
                <input
                  type="number"
                  min={0}
                  max={10}
                  value={editedTask.critical}
                  onChange={(e) => setEditedTask((prev) => ({ ...prev, critical: parseInt(e.target.value) || 0 }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              ) : (
                <p className="text-gray-900">{task.critical}</p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Urgent (0=most, 10=least)
              </label>
              {isEditing ? (
                <input
                  type="number"
                  min={0}
                  max={10}
                  value={editedTask.urgent}
                  onChange={(e) => setEditedTask((prev) => ({ ...prev, urgent: parseInt(e.target.value) || 0 }))}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                />
              ) : (
                <p className="text-gray-900">{task.urgent}</p>
              )}
            </div>
          </div>

          {/* Metadata */}
          <div className="grid grid-cols-2 gap-4 text-sm">
            {task.module_path && (
              <div>
                <label className="block font-medium text-gray-700 mb-1">Module Path</label>
                <p className="text-gray-600 font-mono text-xs bg-gray-100 px-2 py-1 rounded">
                  {task.module_path}
                </p>
              </div>
            )}
            {task.git_branch && (
              <div>
                <label className="block font-medium text-gray-700 mb-1">Git Branch</label>
                <p className="text-gray-600 font-mono text-xs bg-gray-100 px-2 py-1 rounded">
                  {task.git_branch}
                </p>
              </div>
            )}
            {task.pr_url && (
              <div>
                <label className="block font-medium text-gray-700 mb-1">Pull Request</label>
                <a
                  href={task.pr_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-blue-600 hover:underline"
                >
                  View PR
                </a>
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 border-t border-gray-200 bg-gray-50">
          <div>
            {onDelete && (
              <button
                onClick={handleDelete}
                className="px-4 py-2 text-red-600 hover:bg-red-50 rounded-lg font-medium"
              >
                Delete
              </button>
            )}
          </div>
          <div className="flex gap-2">
            {isEditing ? (
              <>
                <button
                  onClick={() => setIsEditing(false)}
                  className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg font-medium"
                >
                  Cancel
                </button>
                <button
                  onClick={handleSave}
                  disabled={isSaving}
                  className="px-4 py-2 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600 disabled:bg-blue-300"
                >
                  {isSaving ? 'Saving...' : 'Save'}
                </button>
              </>
            ) : (
              <button
                onClick={() => setIsEditing(true)}
                className="px-4 py-2 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600"
              >
                Edit
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export default TaskModal;
