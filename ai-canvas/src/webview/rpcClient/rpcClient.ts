import type { RpcRequest, RpcResponse, LoadWorkspaceStateResult, SaveWorkspaceStateParams, ListWorkspaceFilesResult } from '../../shared/types/rpc';
import { isRpcError } from '../../shared/types/rpc';
import { createMessageChannel } from './messageChannel';
import { RequestTracker } from './requestTracker';
import type { MessageChannelApi } from './messageChannel';

function randomId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

export interface RpcClient {
  loadWorkspaceState(): Promise<LoadWorkspaceStateResult>;
  saveWorkspaceState(params: SaveWorkspaceStateParams): Promise<{ ok: boolean }>;
  listWorkspaceFiles(): Promise<ListWorkspaceFilesResult>;
  dispose(): void;
}

export function createRpcClient(getApi: () => MessageChannelApi): RpcClient {
  const tracker = new RequestTracker();
  const channelResult = createMessageChannel({
    getApi,
    onMessage(payload: unknown) {
      const response = payload as RpcResponse;
      if (response?.id != null) {
        tracker.resolve(response.id, response);
      }
    }
  });

  const sendRequest = <T>(method: RpcRequest['method'], params?: unknown): Promise<T> => {
    const id = randomId();
    const request: RpcRequest = { id, method, params };
    const promise = tracker.register(id).then((response) => {
      if (isRpcError(response)) {
        throw new Error(response.error.message || response.error.code);
      }
      return response.result as T;
    });
    channelResult.send(request);
    return promise;
  };

  return {
    loadWorkspaceState(): Promise<LoadWorkspaceStateResult> {
      return sendRequest<LoadWorkspaceStateResult>('loadWorkspaceState');
    },
    saveWorkspaceState(params: SaveWorkspaceStateParams): Promise<{ ok: boolean }> {
      return sendRequest<{ ok: boolean }>('saveWorkspaceState', params);
    },
    listWorkspaceFiles(): Promise<ListWorkspaceFilesResult> {
      return sendRequest<ListWorkspaceFilesResult>('listWorkspaceFiles');
    },
    dispose(): void {
      tracker.rejectAll('RPC client disposed');
    }
  };
}
