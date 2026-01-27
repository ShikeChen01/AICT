import type { RpcEvent, RpcMethod, RpcRequest, RpcResponse } from "../../shared/types/rpc";
import { createMessageChannel } from "./messageChannel";
import { RequestTracker } from "./requestTracker";

export interface RpcClientOptions {
  timeoutMs?: number;
}

export interface RpcClient {
  request: <TResponse = unknown>(method: RpcMethod, params: unknown) => Promise<TResponse>;
  onEvent: (handler: (event: RpcEvent) => void) => () => void;
  dispose: () => void;
}

function isRpcResponse(message: unknown): message is RpcResponse {
  if (typeof message !== "object" || message === null) {
    return false;
  }
  const value = message as { id?: unknown; ok?: unknown };
  return typeof value.id === "string" && typeof value.ok === "boolean";
}

function isRpcEvent(message: unknown): message is RpcEvent {
  if (typeof message !== "object" || message === null) {
    return false;
  }
  const value = message as { event?: unknown };
  return typeof value.event === "string";
}

function generateId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now()}_${Math.random().toString(16).slice(2)}`;
}

export function createRpcClient(options: RpcClientOptions = {}): RpcClient {
  const channel = createMessageChannel();
  const tracker = new RequestTracker(options.timeoutMs);
  const eventHandlers = new Set<(event: RpcEvent) => void>();

  const unsubscribe = channel.onMessage((message) => {
    if (isRpcResponse(message)) {
      if (message.ok) {
        tracker.resolve(message.id, message.result);
      } else {
        tracker.reject(message.id, message.error ?? new Error("RPC error"));
      }
      return;
    }
    if (isRpcEvent(message)) {
      for (const handler of eventHandlers) {
        handler(message);
      }
    }
  });

  return {
    request: async (method, params) => {
      const id = generateId();
      const payload: RpcRequest = { id, method, params };
      const promise = tracker.create(id);
      channel.postMessage(payload);
      return promise as Promise<TResponse>;
    },
    onEvent: (handler) => {
      eventHandlers.add(handler);
      return () => eventHandlers.delete(handler);
    },
    dispose: () => {
      unsubscribe();
      eventHandlers.clear();
      tracker.clear();
    },
  };
}
