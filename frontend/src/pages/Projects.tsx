/**
 * Projects Dashboard Page
 * Create, import, and manage projects
 */

import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import {
  Plus,
  GitBranch,
  Trash2,
  FolderOpen,
  ExternalLink,
  Key,
  Loader2,
  AlertCircle,
} from 'lucide-react';
import {
  getProjects,
  createProject,
  importProject,
  deleteProject,
} from '../api/client';
import type { Project } from '../types';

type ModalType = 'create' | 'import' | null;

interface ProjectsPageProps {
  onProjectsUpdated?: () => Promise<void> | void;
}

export function ProjectsPage({ onProjectsUpdated }: ProjectsPageProps) {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState<ModalType>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Form state
  const [formName, setFormName] = useState('');
  const [formDescription, setFormDescription] = useState('');
  const [formRepoUrl, setFormRepoUrl] = useState('');
  const [formGitToken, setFormGitToken] = useState('');

  const fetchProjects = useCallback(async () => {
    try {
      setIsLoading(true);
      const data = await getProjects();
      setProjects(data);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load projects');
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName.trim()) return;

    setIsSubmitting(true);
    try {
      const project = await createProject({
        name: formName.trim(),
        description: formDescription.trim() || null,
        code_repo_url: formRepoUrl.trim() || undefined,
      });
      setProjects((prev) => [project, ...prev]);
      await onProjectsUpdated?.();
      closeModal();
      navigate(`/project/${project.id}/chat`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create project');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleImport = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName.trim() || !formRepoUrl.trim()) return;

    setIsSubmitting(true);
    try {
      const project = await importProject({
        name: formName.trim(),
        description: formDescription.trim() || null,
        code_repo_url: formRepoUrl.trim(),
        git_token: formGitToken.trim() || null,
      });
      setProjects((prev) => [project, ...prev]);
      await onProjectsUpdated?.();
      closeModal();
      navigate(`/project/${project.id}/chat`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import project');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (projectId: string, projectName: string) => {
    if (!confirm(`Delete project "${projectName}"? This cannot be undone.`)) {
      return;
    }

    try {
      await deleteProject(projectId);
      setProjects((prev) => prev.filter((p) => p.id !== projectId));
      await onProjectsUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete project');
    }
  };

  const closeModal = () => {
    setModal(null);
    setFormName('');
    setFormDescription('');
    setFormRepoUrl('');
    setFormGitToken('');
    setError(null);
  };

  const openCreateModal = () => setModal('create');
  const openImportModal = () => setModal('import');

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
              <p className="text-sm text-gray-500 mt-1">
                Manage your AI-assisted software projects
              </p>
            </div>
            <div className="flex gap-3">
              <button
                onClick={openImportModal}
                className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 bg-white hover:bg-gray-50 transition-colors"
              >
                <GitBranch className="w-4 h-4" />
                Import Repository
              </button>
              <button
                onClick={openCreateModal}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
              >
                <Plus className="w-4 h-4" />
                New Project
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Content */}
      <main className="max-w-7xl mx-auto px-6 py-8">
        {error && (
          <div className="mb-6 flex items-center gap-3 px-4 py-3 bg-red-50 border border-red-200 rounded-lg text-red-700">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            <span className="text-sm">{error}</span>
            <button onClick={() => setError(null)} className="ml-auto text-red-500 hover:text-red-700">
              &times;
            </button>
          </div>
        )}

        {isLoading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
          </div>
        ) : projects.length === 0 ? (
          <div className="text-center py-16">
            <FolderOpen className="w-16 h-16 mx-auto text-gray-300 mb-4" />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No projects yet</h3>
            <p className="text-gray-500 mb-6">Get started by creating a new project or importing an existing repository.</p>
            <div className="flex justify-center gap-3">
              <button
                onClick={openImportModal}
                className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 bg-white hover:bg-gray-50"
              >
                <GitBranch className="w-4 h-4" />
                Import Repository
              </button>
              <button
                onClick={openCreateModal}
                className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
              >
                <Plus className="w-4 h-4" />
                New Project
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {projects.map((project) => (
              <div
                key={project.id}
                className="bg-white border border-gray-200 rounded-lg shadow-sm hover:shadow-md transition-shadow"
              >
                <div className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <h3
                        onClick={() => navigate(`/project/${project.id}/chat`)}
                        className="text-lg font-semibold text-gray-900 truncate cursor-pointer hover:text-blue-600"
                      >
                        {project.name}
                      </h3>
                      {project.description && (
                        <p className="text-sm text-gray-500 mt-1 line-clamp-2">{project.description}</p>
                      )}
                    </div>
                    <button
                      onClick={() => handleDelete(project.id, project.name)}
                      className="ml-2 p-1 text-gray-400 hover:text-red-500 transition-colors"
                      title="Delete project"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="mt-4 flex items-center gap-3 text-xs text-gray-500">
                    {project.code_repo_url && (
                      <a
                        href={project.code_repo_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 hover:text-blue-600"
                      >
                        <GitBranch className="w-3 h-3" />
                        <span className="truncate max-w-[120px]">
                          {project.code_repo_url.replace(/^https?:\/\//, '').replace(/\.git$/, '')}
                        </span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                    {project.git_token_set && (
                      <span className="flex items-center gap-1 text-green-600" title="Git token configured">
                        <Key className="w-3 h-3" />
                        Token
                      </span>
                    )}
                  </div>

                  <div className="mt-4 pt-4 border-t border-gray-100 flex items-center justify-between">
                    <span className="text-xs text-gray-400">
                      Created {format(new Date(project.created_at), 'MMM d, yyyy')}
                    </span>
                    <button
                      onClick={() => navigate(`/project/${project.id}/chat`)}
                      className="text-xs font-medium text-blue-600 hover:text-blue-800"
                    >
                      Open Project &rarr;
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Modal */}
      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={closeModal} />
          <div className="relative bg-white rounded-lg shadow-xl w-full max-w-md mx-4 p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              {modal === 'create' ? 'Create New Project' : 'Import Repository'}
            </h2>

            <form onSubmit={modal === 'create' ? handleCreate : handleImport}>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Project Name *
                  </label>
                  <input
                    type="text"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="My Project"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <textarea
                    value={formDescription}
                    onChange={(e) => setFormDescription(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    rows={3}
                    placeholder="Brief description of the project..."
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Repository URL {modal === 'import' && '*'}
                  </label>
                  <input
                    type="url"
                    value={formRepoUrl}
                    onChange={(e) => setFormRepoUrl(e.target.value)}
                    className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                    placeholder="https://github.com/user/repo"
                    required={modal === 'import'}
                  />
                </div>

                {modal === 'import' && (
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Personal Access Token (for private repos)
                    </label>
                    <input
                      type="password"
                      value={formGitToken}
                      onChange={(e) => setFormGitToken(e.target.value)}
                      className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
                      placeholder="ghp_xxxxxxxxxxxx"
                    />
                    <p className="mt-1 text-xs text-gray-500">
                      Required for private repositories. Token will be stored securely.
                    </p>
                  </div>
                )}
              </div>

              {error && (
                <div className="mt-4 text-sm text-red-600">{error}</div>
              )}

              <div className="mt-6 flex gap-3 justify-end">
                <button
                  type="button"
                  onClick={closeModal}
                  className="px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50"
                  disabled={isSubmitting}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                  {modal === 'create' ? 'Create Project' : 'Import Repository'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default ProjectsPage;
