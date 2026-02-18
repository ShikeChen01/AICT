import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  healthCheck,
  getTasks,
  createTask,
  replyToTicketAsUser,
  sendMessage,
  getMessages,
  getAllMessages,
  setAuthToken,
} from './client';
import { mockTasks, mockFetchResponse, mockProjectId } from '../test/mocks';

describe('API Client', () => {
  beforeEach(() => {
    vi.resetAllMocks();
    setAuthToken('test-token');
  });

  describe('healthCheck', () => {
    it('should return status ok', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        mockFetchResponse({ status: 'ok' })
      );

      const result = await healthCheck();
      
      expect(result).toEqual({ status: 'ok' });
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/health',
        expect.objectContaining({
          method: 'GET',
        })
      );
    });
  });

  describe('getTasks', () => {
    it('should fetch tasks for a project', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        mockFetchResponse(mockTasks)
      );

      const result = await getTasks(mockProjectId);
      
      expect(result).toEqual(mockTasks);
      expect(global.fetch).toHaveBeenCalledWith(
        `/api/v1/tasks?project_id=${mockProjectId}`,
        expect.objectContaining({
          method: 'GET',
          headers: expect.objectContaining({
            Authorization: 'Bearer test-token',
          }),
        })
      );
    });

    it('should include status filter when provided', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        mockFetchResponse([mockTasks[0]])
      );

      await getTasks(mockProjectId, 'backlog');
      
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('status=backlog'),
        expect.any(Object)
      );
    });
  });

  describe('createTask', () => {
    it('should create a new task', async () => {
      const newTask = mockTasks[0];
      vi.mocked(global.fetch).mockResolvedValueOnce(
        mockFetchResponse(newTask, 201)
      );

      const result = await createTask(mockProjectId, {
        title: newTask.title,
        description: newTask.description,
      });
      
      expect(result).toEqual(newTask);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/tasks'),
        expect.objectContaining({
          method: 'POST',
          body: expect.any(String),
        })
      );
    });
  });

  describe('replyToTicketAsUser', () => {
    it('should POST user reply to ticket', async () => {
      const ticketId = '55555555-5555-5555-5555-555555555555';
      const content = 'Use env VAR API_KEY';
      vi.mocked(global.fetch).mockResolvedValueOnce(
        mockFetchResponse({ id: 'msg-1', ticket_id: ticketId, content }, 201)
      );

      await replyToTicketAsUser(ticketId, content);

      expect(global.fetch).toHaveBeenCalledWith(
        `/api/v1/tickets/${ticketId}/user-reply`,
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({ content }),
          headers: expect.objectContaining({
            Authorization: 'Bearer test-token',
          }),
        })
      );
    });
  });

  describe('messages API', () => {
    const agentId = '33333333-3333-3333-3333-333333333333';
    const channelMsg = {
      id: 'msg-001',
      project_id: mockProjectId,
      from_agent_id: null,
      target_agent_id: agentId,
      content: 'Hello agent',
      message_type: 'normal',
      status: 'sent',
      broadcast: false,
      created_at: '2026-02-01T12:00:00Z',
    };

    it('sendMessage should POST to /messages/send and return ChannelMessage', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        mockFetchResponse(channelMsg, 202)
      );

      const result = await sendMessage({
        project_id: mockProjectId,
        target_agent_id: agentId,
        content: 'Hello agent',
      });

      expect(result).toEqual(channelMsg);
      expect(global.fetch).toHaveBeenCalledWith(
        '/api/v1/messages/send',
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify({
            project_id: mockProjectId,
            target_agent_id: agentId,
            content: 'Hello agent',
          }),
        })
      );
    });

    it('getMessages should GET conversation with query params', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        mockFetchResponse([channelMsg])
      );

      const result = await getMessages(mockProjectId, agentId, 50, 0);

      expect(result).toEqual([channelMsg]);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/messages?'),
        expect.any(Object)
      );
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringMatching(new RegExp(`project_id=${mockProjectId}`)),
        expect.any(Object)
      );
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringMatching(new RegExp(`agent_id=${agentId}`)),
        expect.any(Object)
      );
    });

    it('getAllMessages should GET all user messages for project', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        mockFetchResponse([channelMsg])
      );

      const result = await getAllMessages(mockProjectId, 100, 0);

      expect(result).toEqual([channelMsg]);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/api/v1/messages/all?'),
        expect.any(Object)
      );
    });
  });
});
