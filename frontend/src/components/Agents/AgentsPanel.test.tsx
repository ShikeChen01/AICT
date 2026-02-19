import { act, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { AgentsPanel } from './AgentsPanel';

const useAgentsMock = vi.fn();
const subscribeHandlers: Record<string, (data: any) => void> = {};

vi.mock('../../hooks', () => ({
  useAgents: (...args: unknown[]) => useAgentsMock(...args),
}));

vi.mock('../../hooks/useWebSocket', () => ({
  useWebSocket: () => ({
    subscribe: (eventType: string, handler: (data: any) => void) => {
      subscribeHandlers[eventType] = handler;
      return () => {
        if (subscribeHandlers[eventType] === handler) {
          delete subscribeHandlers[eventType];
        }
      };
    },
  }),
}));

describe('AgentsPanel', () => {
  it('renders rolling agent activity lines from websocket events', () => {
    useAgentsMock.mockReturnValue({
      agents: [
        {
          id: 'agent-1',
          project_id: 'project-1',
          role: 'manager',
          display_name: 'Manager',
          model: 'test-model',
          status: 'active',
          current_task_id: null,
          sandbox_id: null,
          sandbox_persist: true,
          priority: 0,
          created_at: '2026-01-01T00:00:00Z',
          updated_at: '2026-01-01T00:00:00Z',
          queue_size: 0,
          pending_message_count: 0,
          task_queue: [],
        },
      ],
      isLoading: false,
      error: null,
    });

    render(<AgentsPanel projectId="project-1" />);

    act(() => {
      subscribeHandlers.agent_log?.({
        project_id: 'project-1',
        agent_id: 'agent-1',
        agent_role: 'manager',
        log_type: 'thought',
        content: 'Planning the next implementation steps.',
      });
    });

    expect(screen.getByText(/\[thought\] Planning the next implementation steps\./)).toBeInTheDocument();
  });
});
