import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { useEffect } from 'react';
import { ProjectProvider, useProjectContext } from './ProjectContext';
import * as client from '../api/client';

const mockRepos = [
  {
    id: 'repo-1',
    owner_id: 'user-1',
    name: 'Test Repo',
    description: 'A test repo',
    spec_repo_path: '/spec',
    code_repo_url: 'https://github.com/example/repo',
    code_repo_path: '/code',
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-01-01T00:00:00Z',
  },
];

function Consumer({ triggerRefresh = false }: { triggerRefresh?: boolean }) {
  const { projects, loading, error, refreshProjects } = useProjectContext();
  useEffect(() => {
    if (triggerRefresh) void refreshProjects();
  }, [triggerRefresh, refreshProjects]);
  return (
    <div>
      <span data-testid="loading">{String(loading)}</span>
      <span data-testid="error">{error ?? 'none'}</span>
      <span data-testid="count">{projects.length}</span>
      <button type="button" onClick={() => void refreshProjects()}>
        Refresh
      </button>
    </div>
  );
}

describe('ProjectContext', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    vi.spyOn(client, 'getRepositories').mockResolvedValue(mockRepos as never);
  });

  it('provides projects after refreshProjects is called', async () => {
    render(
      <ProjectProvider>
        <Consumer triggerRefresh />
      </ProjectProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false');
    });

    expect(client.getRepositories).toHaveBeenCalled();
    expect(screen.getByTestId('count').textContent).toBe('1');
  });

  it('refreshProjects fetches again when Refresh is clicked', async () => {
    render(
      <ProjectProvider>
        <Consumer triggerRefresh />
      </ProjectProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('count').textContent).toBe('1');
    });

    screen.getByRole('button', { name: 'Refresh' }).click();

    await waitFor(() => {
      expect(client.getRepositories).toHaveBeenCalledTimes(2);
    });
  });
});
