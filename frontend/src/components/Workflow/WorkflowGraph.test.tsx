/**
 * WorkflowGraph Component Tests
 */

import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { WorkflowGraph } from './WorkflowGraph';

// Mock ReactFlow since it requires browser context
vi.mock('@xyflow/react', () => ({
  ReactFlow: ({ children }: { children?: React.ReactNode }) => (
    <div data-testid="react-flow">{children}</div>
  ),
  Background: () => <div data-testid="background" />,
  Controls: () => <div data-testid="controls" />,
  MiniMap: () => <div data-testid="minimap" />,
  useNodesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
  useEdgesState: (initial: unknown[]) => [initial, vi.fn(), vi.fn()],
  Position: { Top: 'top', Bottom: 'bottom' },
  MarkerType: { ArrowClosed: 'arrowclosed' },
}));

describe('WorkflowGraph', () => {
  it('renders the workflow graph container', () => {
    render(<WorkflowGraph projectId="test-project-id" />);
    expect(screen.getByTestId('react-flow')).toBeInTheDocument();
  });

  it('renders with background and controls', () => {
    render(<WorkflowGraph projectId="test-project-id" />);
    expect(screen.getByTestId('background')).toBeInTheDocument();
    expect(screen.getByTestId('controls')).toBeInTheDocument();
    expect(screen.getByTestId('minimap')).toBeInTheDocument();
  });

  it('accepts currentNode prop', () => {
    render(<WorkflowGraph projectId="test-project-id" currentNode="manager" />);
    expect(screen.getByTestId('react-flow')).toBeInTheDocument();
  });

  it('accepts workflowUpdate prop', () => {
    const workflowUpdate = {
      project_id: 'test-project-id',
      thread_id: 'thread-1',
      previous_node: 'manager',
      current_node: 'cto',
      node_status: 'started' as const,
    };
    render(<WorkflowGraph projectId="test-project-id" workflowUpdate={workflowUpdate} />);
    expect(screen.getByTestId('react-flow')).toBeInTheDocument();
  });

  it('accepts onNodeClick callback', () => {
    const onNodeClick = vi.fn();
    render(<WorkflowGraph projectId="test-project-id" onNodeClick={onNodeClick} />);
    expect(screen.getByTestId('react-flow')).toBeInTheDocument();
  });
});
