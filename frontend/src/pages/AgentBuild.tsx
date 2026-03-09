/**
 * Agent Build Page — the prompt block editor, model config, context budget, tools.
 *
 * Dashboard has been promoted to its own top-level route (/dashboard).
 * AgentConfigPanel now lives in a top-bar inline section instead of being
 * buried inside the left sidebar's scrollable area.
 */

import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { Loader2, AlertCircle } from 'lucide-react';
import { getProject } from '../api/client';
import type { Project } from '../types';
import { AppLayout } from '../components/Layout';
import { PromptBuilderPage } from '../components/PromptBuilder/PromptBuilderPage';

export function AgentBuildPage() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();

  const [project, setProject] = useState<Project | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchProject = useCallback(async () => {
    if (!projectId) return;
    try {
      setIsLoading(true);
      const proj = await getProject(projectId);
      setProject(proj);
    } catch (_err) {
      setProject(null);
    } finally {
      setIsLoading(false);
    }
  }, [projectId]);

  useEffect(() => { fetchProject(); }, [fetchProject]);

  if (isLoading) {
    return (
      <AppLayout>
        <div className="flex flex-1 items-center justify-center" role="status">
          <Loader2 className="w-8 h-8 animate-spin text-[var(--color-primary)]" aria-hidden="true" />
          <span className="sr-only">Loading agent builder…</span>
        </div>
      </AppLayout>
    );
  }

  if (!project || !projectId) {
    return (
      <AppLayout>
        <div className="flex flex-1 items-center justify-center">
          <div className="text-center">
            <AlertCircle className="w-12 h-12 mx-auto text-[var(--color-danger)] mb-4" aria-hidden="true" />
            <h2 className="text-lg font-semibold text-[var(--text-primary)]">Project not found</h2>
            <button
              onClick={() => navigate('/projects')}
              className="mt-4 text-[var(--color-primary)] hover:underline"
            >
              Back to Projects
            </button>
          </div>
        </div>
      </AppLayout>
    );
  }

  return (
    <AppLayout>
      <div className="flex flex-1 flex-col min-h-0 overflow-hidden bg-[var(--app-bg)]">
        <PromptBuilderPage projectId={projectId} />
      </div>
    </AppLayout>
  );
}

export default AgentBuildPage;
