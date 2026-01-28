import { randomUUID } from "src/webview/utils/ids";
import type { RpcEvent, RpcMethod, RpcRequest, RpcRequestPayloads, RpcResponse } from "src/shared/types";
import { createMessageChannel } from "src/webview/rpcClient/messageChannel";
import { RequestTracker } from "src/webview/rpcClient/requestTracker";

export type RpcClient = {
  request: <M extends RpcMethod>(method: M, params: RpcRequestPayloads[M]) => Promise<unknown>;
  onEvent: (handler: (event: RpcEvent) => void) => () => void;
};

export const createRpcClient = (): RpcClient => {
  const channel = createMessageChannel();
  const tracker = new RequestTracker({ timeoutMs: 120_000 });
  const eventHandlers = new Set<(event: RpcEvent) => void>();

  channel.onMessage((message) => {
    const payload = message as RpcResponse | RpcEvent | RpcRequest;
    if (payload && typeof payload === "object" && "ok" in payload && "id" in payload) {
      const response = payload as RpcResponse;
      if (response.ok) {
        tracker.resolve(response.id, response.result);
      } else {
        tracker.reject(response.id, new Error(response.error.message));
      }
      return;
    }

    if (payload && typeof payload === "object" && "type" in payload) {
      eventHandlers.forEach((handler) => handler(payload as RpcEvent));
    }
  });

  return {
    request: async (method, params) => {
      const id = randomUUID();
      const request: RpcRequest = { id, method, params };
      const pending = tracker.create(id);
      channel.send(request);
      return pending;
    },
    onEvent: (handler) => {
      eventHandlers.add(handler);
      return () => eventHandlers.delete(handler);
    },
  };
};
