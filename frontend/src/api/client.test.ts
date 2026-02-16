import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  healthCheck,
  getTasks,
  createTask,
  getChatHistory,
  replyToTicketAsUser,
  setAuthToken,
} from './client';
import { mockTasks, mockChatMessages, mockFetchResponse, mockProjectId } from '../test/mocks';

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

  describe('getChatHistory', () => {
    it('should fetch chat history', async () => {
      vi.mocked(global.fetch).mockResolvedValueOnce(
        mockFetchResponse(mockChatMessages)
      );

      const result = await getChatHistory(mockProjectId);
      
      expect(result).toEqual(mockChatMessages);
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining('/chat/history'),
        expect.objectContaining({
          method: 'GET',
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
});
