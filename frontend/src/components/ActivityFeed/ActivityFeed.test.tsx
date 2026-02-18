/**
 * ActivityFeed Component Tests
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { ActivityFeed } from './ActivityFeed';

const mockLogs = [
  {
    id: 'log-1',
    project_id: 'project-1',
    agent_id: 'agent-1',
    agent_role: 'manager' as const,
    log_type: 'thought' as const,
    content: 'Analyzing user request...',
    timestamp: '2026-02-14T12:00:00Z',
  },
  {
    id: 'log-2',
    project_id: 'project-1',
    agent_id: 'agent-2',
    agent_role: 'cto' as const,
    log_type: 'tool_call' as const,
    content: 'Creating task for implementation',
    tool_name: 'create_task',
    tool_input: { title: 'Implement feature', priority: 'high' },
    timestamp: '2026-02-14T12:01:00Z',
  },
  {
    id: 'log-3',
    project_id: 'project-1',
    agent_id: 'agent-3',
    agent_role: 'engineer' as const,
    log_type: 'tool_result' as const,
    content: 'File written successfully',
    tool_output: 'Created src/feature.ts',
    timestamp: '2026-02-14T12:02:00Z',
  },
];

describe('ActivityFeed', () => {
  it('renders empty state when no logs', () => {
    render(<ActivityFeed logs={[]} />);
    expect(screen.getByText('No activity yet...')).toBeInTheDocument();
  });

  it('renders log entries', () => {
    render(<ActivityFeed logs={mockLogs} />);
    expect(screen.getByText('Analyzing user request...')).toBeInTheDocument();
    expect(screen.getByText('Creating task for implementation')).toBeInTheDocument();
    expect(screen.getByText('File written successfully')).toBeInTheDocument();
  });

  it('displays agent role badges', () => {
    render(<ActivityFeed logs={mockLogs} />);
    expect(screen.getByText('manager')).toBeInTheDocument();
    expect(screen.getByText('cto')).toBeInTheDocument();
    expect(screen.getByText('engineer')).toBeInTheDocument();
  });

  it('displays tool name for tool calls', () => {
    render(<ActivityFeed logs={mockLogs} />);
    expect(screen.getByText('create_task')).toBeInTheDocument();
  });

  it('filters logs by agent role', () => {
    render(<ActivityFeed logs={mockLogs} filter="manager" />);
    expect(screen.getByText('Analyzing user request...')).toBeInTheDocument();
    expect(screen.queryByText('Creating task for implementation')).not.toBeInTheDocument();
  });

  it('shows all logs when filter is "all"', () => {
    render(<ActivityFeed logs={mockLogs} filter="all" />);
    expect(screen.getByText('Analyzing user request...')).toBeInTheDocument();
    expect(screen.getByText('Creating task for implementation')).toBeInTheDocument();
    expect(screen.getByText('File written successfully')).toBeInTheDocument();
  });

  it('calls onFilterChange when filter dropdown changes', () => {
    const onFilterChange = vi.fn();
    render(<ActivityFeed logs={mockLogs} filter="all" onFilterChange={onFilterChange} />);
    
    const select = screen.getByRole('combobox');
    fireEvent.change(select, { target: { value: 'manager' } });
    
    expect(onFilterChange).toHaveBeenCalledWith('manager');
  });

  it('renders header with title', () => {
    render(<ActivityFeed logs={mockLogs} />);
    expect(screen.getByText('Activity Feed')).toBeInTheDocument();
  });
});
