/**
 * Repositories dashboard page.
 */

import { useState, useEffect, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { format } from 'date-fns';
import {
  Plus,
  GitBranch,
  Trash2,
  FolderOpen,
  ExternalLink,
  Loader2,
  AlertCircle,
  Settings,
} from 'lucide-react';
import {
  getProjects,
  createProject,
  importProject,
  deleteProject,
  getAuthToken,
} from '../api/client';
import type { Project } from '../types';
import { Button, Card, Input, Textarea } from '../components/ui';

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
  const [formPrivate, setFormPrivate] = useState(true);

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
    if (!getAuthToken()) return;
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
        private: formPrivate,
      });
      setProjects((prev) => [project, ...prev]);
      await onProjectsUpdated?.();
      closeModal();
      navigate(`/repository/${project.id}/workspace`);
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
      });
      setProjects((prev) => [project, ...prev]);
      await onProjectsUpdated?.();
      closeModal();
      navigate(`/repository/${project.id}/workspace`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import project');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleDelete = async (projectId: string, projectName: string) => {
    if (!confirm(`Delete repository "${projectName}"? This cannot be undone.`)) {
      return;
    }

    try {
      await deleteProject(projectId);
      setProjects((prev) => prev.filter((p) => p.id !== projectId));
      await onProjectsUpdated?.();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to delete repository');
    }
  };

  const closeModal = () => {
    setModal(null);
    setFormName('');
    setFormDescription('');
    setFormRepoUrl('');
    setFormPrivate(true);
    setError(null);
  };

  const openCreateModal = () => setModal('create');
  const openImportModal = () => setModal('import');

  return (
    <div className="min-h-screen bg-[var(--app-bg)]">
      <header className="border-b border-[var(--border-color)] bg-[var(--surface-card)]">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-6">
          <div>
            <h1 className="text-2xl font-bold text-[var(--text-primary)]">Repositories</h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Monitor and manage your AI-assisted workspaces.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Link to="/settings">
              <Button variant="secondary">
                <Settings className="h-4 w-4" />
                User Settings
              </Button>
            </Link>
            <Button variant="secondary" onClick={openImportModal}>
              <GitBranch className="h-4 w-4" />
              Import Repository
            </Button>
            <Button onClick={openCreateModal}>
              <Plus className="h-4 w-4" />
              New Repository
            </Button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-7xl px-6 py-8">
        {error && (
          <Card className="mb-6 flex items-center gap-3 border-red-200 bg-red-50 px-4 py-3 text-red-700">
            <AlertCircle className="h-5 w-5 flex-shrink-0" />
            <span className="text-sm">{error}</span>
            <button onClick={() => setError(null)} className="ml-auto text-red-500 hover:text-red-700">
              &times;
            </button>
          </Card>
        )}

        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-blue-500" />
          </div>
        ) : projects.length === 0 ? (
          <Card className="py-16 text-center">
            <FolderOpen className="mx-auto mb-4 h-16 w-16 text-gray-300" />
            <h3 className="mb-2 text-lg font-medium text-gray-900">No repositories yet</h3>
            <p className="mb-6 text-gray-500">
              Create a new repository or import an existing one to start monitoring agents.
            </p>
            <div className="flex justify-center gap-3">
              <Button variant="secondary" onClick={openImportModal}>
                <GitBranch className="h-4 w-4" />
                Import Repository
              </Button>
              <Button onClick={openCreateModal}>
                <Plus className="h-4 w-4" />
                New Repository
              </Button>
            </div>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {projects.map((project) => (
              <Card key={project.id} className="transition-shadow hover:shadow-md">
                <div className="p-5">
                  <div className="flex items-start justify-between">
                    <div className="flex-1 min-w-0">
                      <h3
                        onClick={() => navigate(`/repository/${project.id}/workspace`)}
                        className="text-lg font-semibold text-gray-900 truncate cursor-pointer hover:text-blue-600"
                      >
                        {project.name}
                      </h3>
                      {project.description && (
                        <p className="text-sm text-gray-500 mt-1 line-clamp-2">{project.description}</p>
                      )}
                    </div>
                    <Button
                      onClick={() => handleDelete(project.id, project.name)}
                      variant="ghost"
                      size="sm"
                      className="ml-2 p-1 text-gray-400 hover:text-red-500 transition-colors"
                      title="Delete repository"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
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
                  </div>

                  <div className="mt-4 pt-4 border-t border-gray-100 flex items-center justify-between">
                    <span className="text-xs text-gray-400">
                      Created {format(new Date(project.created_at), 'MMM d, yyyy')}
                    </span>
                    <button
                      onClick={() => navigate(`/repository/${project.id}/workspace`)}
                      className="text-xs font-medium text-blue-600 hover:text-blue-800"
                    >
                      Open Repository &rarr;
                    </button>
                  </div>
                </div>
              </Card>
            ))}
          </div>
        )}
      </main>

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div className="absolute inset-0 bg-black/50" onClick={closeModal} />
          <Card className="relative mx-4 w-full max-w-md p-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              {modal === 'create' ? 'Create New Repository' : 'Import Repository'}
            </h2>

            <form onSubmit={modal === 'create' ? handleCreate : handleImport}>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Repository Name *
                  </label>
                  <Input
                    type="text"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="my-repository"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Description
                  </label>
                  <Textarea
                    value={formDescription}
                    onChange={(e) => setFormDescription(e.target.value)}
                    rows={3}
                    placeholder="Brief description of the repository..."
                  />
                </div>

                {modal === 'import' && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Repository URL *
                  </label>
                  <Input
                    type="url"
                    value={formRepoUrl}
                    onChange={(e) => setFormRepoUrl(e.target.value)}
                    placeholder="https://github.com/user/repo"
                    required
                  />
                </div>
                )}
                {modal === 'create' && (
                  <label className="flex items-center gap-2 text-sm text-gray-700">
                    <input
                      type="checkbox"
                      checked={formPrivate}
                      onChange={(e) => setFormPrivate(e.target.checked)}
                    />
                    Create as private GitHub repository
                  </label>
                )}
              </div>

              {error && (
                <div className="mt-4 text-sm text-red-600">{error}</div>
              )}

              <div className="mt-6 flex gap-3 justify-end">
                <Button
                  type="button"
                  onClick={closeModal}
                  variant="secondary"
                  disabled={isSubmitting}
                >
                  Cancel
                </Button>
                <Button
                  type="submit"
                  disabled={isSubmitting}
                >
                  {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                  {modal === 'create' ? 'Create Repository' : 'Import Repository'}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
  );
}

export default ProjectsPage;
