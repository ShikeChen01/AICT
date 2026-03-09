/**
 * ProjectContext — active project and project list from repositories API.
 * Used by workspace sidebar and project-scoped views.
 */

import { createContext, useCallback, useContext, useState } from 'react';
import { getRepositories } from '../api/client';
import type { Repository } from '../types';

interface ProjectContextValue {
  projects: Repository[];
  loading: boolean;
  error: string | null;
  refreshProjects: () => Promise<void>;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [projects, setProjects] = useState<Repository[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshProjects = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await getRepositories();
      setProjects(list);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load repositories');
    } finally {
      setLoading(false);
    }
  }, []);

  // Caller (e.g. AppShell) calls refreshProjects when auth is ready.

  const value: ProjectContextValue = {
    projects,
    loading,
    error,
    refreshProjects,
  };

  return (
    <ProjectContext.Provider value={value}>
      {children}
    </ProjectContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useProjectContext(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (!ctx) {
    throw new Error('useProjectContext must be used within ProjectProvider');
  }
  return ctx;
}
