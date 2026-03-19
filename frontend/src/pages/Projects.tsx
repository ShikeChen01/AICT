/**
 * Projects dashboard page.
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
  Loader2,
  AlertCircle,
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
import { AppLayout } from '../components/Layout';

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
        code_repo_url: formRepoUrl.trim() || undefined,
      });
      setProjects((prev) => [project, ...prev]);
      await onProjectsUpdated?.();
      closeModal();
      navigate(`/project/${project.id}/workspace`);
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
      navigate(`/project/${project.id}/workspace`);
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
    setError(null);
  };

  const openCreateModal = () => setModal('create');
  const openImportModal = () => setModal('import');

  return (
    <AppLayout>
    <div className="min-h-screen bg-[var(--app-bg)]">
      <div className="mx-auto max-w-7xl px-6 pt-6 pb-2">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-[var(--text-primary)]">Projects</h1>
            <p className="mt-1 text-sm text-[var(--text-muted)]">
              Design, deploy, and manage your AI agent teams.
            </p>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="secondary" onClick={openImportModal}>
              <GitBranch className="h-4 w-4" />
              Import Project
            </Button>
            <Button onClick={openCreateModal}>
              <Plus className="h-4 w-4" />
              New Project
            </Button>
          </div>
        </div>
      </div>

      <main className="mx-auto max-w-7xl px-6 py-8">
        {error && (
          <Card className="mb-6 flex items-center gap-3 border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] px-4 py-3 text-[var(--color-danger)]">
            <AlertCircle className="h-5 w-5 flex-shrink-0" />
            <span className="text-sm">{error}</span>
            <button onClick={() => setError(null)} className="ml-auto text-[var(--color-danger)] hover:opacity-70 transition-opacity">
              &times;
            </button>
          </Card>
        )}

        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <Loader2 className="h-8 w-8 animate-spin text-[var(--color-primary)]" />
          </div>
        ) : projects.length === 0 ? (
          <Card className="py-16 text-center">
            <FolderOpen className="mx-auto mb-4 h-16 w-16 text-[var(--text-faint)]" />
            <h3 className="mb-2 text-lg font-medium text-[var(--text-primary)]">No projects yet</h3>
            <p className="mb-6 text-[var(--text-muted)]">
              Create a new project or import an existing one to start building with AI agents.
            </p>
            <div className="flex justify-center gap-3">
              <Button variant="secondary" onClick={openImportModal}>
                <GitBranch className="h-4 w-4" />
                Import Project
              </Button>
              <Button onClick={openCreateModal}>
                <Plus className="h-4 w-4" />
                New Project
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
                        onClick={() => navigate(`/project/${project.id}/workspace`)}
                        className="text-lg font-semibold text-[var(--text-primary)] truncate cursor-pointer hover:text-[var(--color-primary)]"
                      >
                        {project.name}
                      </h3>
                      {project.description && (
                        <p className="text-sm text-[var(--text-muted)] mt-1 line-clamp-2">{project.description}</p>
                      )}
                    </div>
                    <Button
                      onClick={() => handleDelete(project.id, project.name)}
                      variant="ghost"
                      size="sm"
                      className="ml-2 p-1 text-[var(--text-faint)] hover:text-[var(--color-danger)] transition-colors"
                      title="Delete project"
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  </div>

                  <div className="mt-4 flex items-center gap-3 text-xs text-[var(--text-muted)]">
                    {project.code_repo_url && (
                      <a
                        href={project.code_repo_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center gap-1 hover:text-[var(--color-primary)]"
                      >
                        <GitBranch className="w-3 h-3" />
                        <span className="truncate max-w-[120px]">
                          {project.code_repo_url.replace(/^https?:\/\//, '').replace(/\.git$/, '')}
                        </span>
                        <ExternalLink className="w-3 h-3" />
                      </a>
                    )}
                  </div>

                  <div className="mt-4 pt-4 border-t border-[var(--border-color)] flex items-center justify-between">
                    <span className="text-xs text-[var(--text-faint)]">
                      Created {format(new Date(project.created_at), 'MMM d, yyyy')}
                    </span>
                    <button
                      onClick={() => navigate(`/project/${project.id}/workspace`)}
                      className="text-xs font-medium text-[var(--color-primary)] hover:text-[var(--color-primary-hover)]"
                    >
                      Open Project &rarr;
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
            <h2 className="text-xl font-semibold text-[var(--text-primary)] mb-4">
              {modal === 'create' ? 'Create New Project' : 'Import Project'}
            </h2>

            <form onSubmit={modal === 'create' ? handleCreate : handleImport}>
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                    Project Name *
                  </label>
                  <Input
                    type="text"
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="my-project"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                    Description
                  </label>
                  <Textarea
                    value={formDescription}
                    onChange={(e) => setFormDescription(e.target.value)}
                    rows={3}
                    placeholder="Brief description of the project..."
                  />
                </div>

                {modal === 'import' && (
                <div>
                  <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                    Project URL *
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
                <div>
                  <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1">
                    Repository URL (optional)
                  </label>
                  <Input
                    type="url"
                    value={formRepoUrl}
                    onChange={(e) => setFormRepoUrl(e.target.value)}
                    placeholder="https://github.com/user/repo"
                  />
                </div>
                )}
              </div>

              {error && (
                <div className="mt-4 text-sm text-[var(--color-danger)]">{error}</div>
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
                  {modal === 'create' ? 'Create Project' : 'Import Project'}
                </Button>
              </div>
            </form>
          </Card>
        </div>
      )}
    </div>
    </AppLayout>
  );
}

export default ProjectsPage;
