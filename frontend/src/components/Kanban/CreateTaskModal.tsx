/**
 * CreateTaskModal Component
 * Modal for creating new tasks
 */

import { useState, useCallback } from 'react';
import type { TaskCreate, TaskStatus } from '../../types';

interface CreateTaskModalProps {
  onClose: () => void;
  onCreate: (task: TaskCreate) => Promise<void>;
}

const STATUSES: { value: TaskStatus; label: string }[] = [
  { value: 'backlog', label: 'Backlog' },
  { value: 'specifying', label: 'Specifying' },
];

export function CreateTaskModal({ onClose, onCreate }: CreateTaskModalProps) {
  const [isSaving, setIsSaving] = useState(false);
  const [task, setTask] = useState<TaskCreate>({
    title: '',
    description: '',
    status: 'backlog',
    critical: 5,
    urgent: 5,
    module_path: null,
  });

  const handleSubmit = useCallback(async () => {
    if (!task.title.trim()) return;

    setIsSaving(true);
    try {
      await onCreate(task);
      onClose();
    } catch (error) {
      console.error('Failed to create task:', error);
    } finally {
      setIsSaving(false);
    }
  }, [task, onCreate, onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />

      {/* Modal */}
      <div className="relative bg-white rounded-xl shadow-xl max-w-lg w-full mx-4">
        {/* Header */}
        <div className="flex items-center justify-between p-6 border-b border-gray-200">
          <h2 className="text-xl font-semibold text-gray-900">Create Task</h2>
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
        <div className="p-6 space-y-4">
          {/* Title */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Title <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              value={task.title}
              onChange={(e) => setTask((prev) => ({ ...prev, title: e.target.value }))}
              placeholder="Enter task title"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Description */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Description</label>
            <textarea
              value={task.description || ''}
              onChange={(e) => setTask((prev) => ({ ...prev, description: e.target.value }))}
              placeholder="Enter task description"
              rows={3}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
          </div>

          {/* Status */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Initial Status</label>
            <select
              value={task.status}
              onChange={(e) => setTask((prev) => ({ ...prev, status: e.target.value as TaskStatus }))}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            >
              {STATUSES.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>

          {/* Priority */}
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Critical (0=most, 10=least)
              </label>
              <input
                type="number"
                min={0}
                max={10}
                value={task.critical}
                onChange={(e) => setTask((prev) => ({ ...prev, critical: parseInt(e.target.value) || 5 }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">
                Urgent (0=most, 10=least)
              </label>
              <input
                type="number"
                min={0}
                max={10}
                value={task.urgent}
                onChange={(e) => setTask((prev) => ({ ...prev, urgent: parseInt(e.target.value) || 5 }))}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
              />
            </div>
          </div>

          {/* Module Path */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Module Path (optional)
            </label>
            <input
              type="text"
              value={task.module_path || ''}
              onChange={(e) => setTask((prev) => ({ ...prev, module_path: e.target.value || null }))}
              placeholder="e.g., src/components/auth"
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 font-mono text-sm"
            />
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 p-6 border-t border-gray-200 bg-gray-50">
          <button
            onClick={onClose}
            className="px-4 py-2 text-gray-700 hover:bg-gray-100 rounded-lg font-medium"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={isSaving || !task.title.trim()}
            className="px-4 py-2 bg-blue-500 text-white rounded-lg font-medium hover:bg-blue-600 disabled:bg-blue-300 disabled:cursor-not-allowed"
          >
            {isSaving ? 'Creating...' : 'Create Task'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default CreateTaskModal;
