/**
 * Projects Page Tests
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ProjectsPage } from './Projects';
import * as api from '../api/client';

vi.mock('../api/client', () => ({
  getProjects: vi.fn(),
  createProject: vi.fn(),
  importProject: vi.fn(),
  deleteProject: vi.fn(),
}));

const mockProjects = [
  {
    id: 'project-1',
    name: 'Test Project 1',
    description: 'First test project',
    spec_repo_path: '/data/specs/project-1',
    code_repo_url: 'https://github.com/user/repo1',
    code_repo_path: '/data/project/project-1',
    git_token_set: true,
    created_at: '2026-02-14T10:00:00Z',
    updated_at: '2026-02-14T10:00:00Z',
  },
  {
    id: 'project-2',
    name: 'Test Project 2',
    description: null,
    spec_repo_path: '/data/specs/project-2',
    code_repo_url: '',
    code_repo_path: '/data/project/project-2',
    git_token_set: false,
    created_at: '2026-02-13T10:00:00Z',
    updated_at: '2026-02-13T10:00:00Z',
  },
];

describe('ProjectsPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    (api.getProjects as ReturnType<typeof vi.fn>).mockResolvedValue(mockProjects);
  });

  it('renders loading state initially', () => {
    (api.getProjects as ReturnType<typeof vi.fn>).mockImplementation(
      () => new Promise(() => {})
    );

    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    );

    // The loading spinner should be present
    expect(document.querySelector('.animate-spin')).toBeInTheDocument();
  });

  it('renders project list after loading', async () => {
    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Test Project 1')).toBeInTheDocument();
      expect(screen.getByText('Test Project 2')).toBeInTheDocument();
    });
  });

  it('displays project description when available', async () => {
    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('First test project')).toBeInTheDocument();
    });
  });

  it('shows git token indicator for projects with token', async () => {
    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Token')).toBeInTheDocument();
    });
  });

  it('opens create modal when New Project button is clicked', async () => {
    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Test Project 1')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('New Project'));

    expect(screen.getByText('Create New Project')).toBeInTheDocument();
  });

  it('opens import modal when Import Repository button is clicked', async () => {
    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Test Project 1')).toBeInTheDocument();
    });

    // Click the first Import Repository button (in header)
    const importButtons = screen.getAllByText('Import Repository');
    fireEvent.click(importButtons[0]);

    // Modal should now be open with the PAT field
    expect(screen.getByText('Personal Access Token (for private repos)')).toBeInTheDocument();
  });

  it('renders empty state when no projects', async () => {
    (api.getProjects as ReturnType<typeof vi.fn>).mockResolvedValue([]);

    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('No projects yet')).toBeInTheDocument();
    });
  });

  it('displays error message on fetch failure', async () => {
    (api.getProjects as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Network error')
    );

    render(
      <MemoryRouter>
        <ProjectsPage />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });
});
