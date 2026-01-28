import { EventEmitter } from "node:events";
import type { RpcEvent, RpcMethod, RpcRequest, RpcResponse } from "src/shared/types/rpc";
import type { RpcHandler, RpcHandlerContext, RpcHandlerRegistry } from "src/extension/rpc/rpcHandlers";
import { validateRpcRequest } from "src/extension/rpc/rpcValidation";
import type { RpcTransport } from "src/extension/rpc/rpcTransport";

// RPC server: validate incoming messages, dispatch handlers, and emit events back to the UI.
export type RpcServerOptions = {
  transport: RpcTransport;
  handlers: RpcHandlerRegistry;
  requestTimeoutMs?: number;
};

export class RpcServer extends EventEmitter {
  private readonly transport: RpcTransport;
  private readonly handlers: RpcHandlerRegistry;
  private readonly requestTimeoutMs: number;
  private readonly inflight = new Map<string, AbortController>();
  private disposable?: { dispose: () => void };

  constructor(options: RpcServerOptions) {
    super();
    this.transport = options.transport;
    this.handlers = options.handlers;
    this.requestTimeoutMs = options.requestTimeoutMs ?? 5 * 60 * 1000;
  }

  start(): void {
    if (this.disposable) {
      return;
    }
    this.disposable = this.transport.onMessage((message) => {
      void this.handleMessage(message);
    });
  }

  dispose(): void {
    this.disposable?.dispose();
    this.disposable = undefined;
    this.transport.dispose();
    this.inflight.forEach((controller) => controller.abort());
    this.inflight.clear();
    this.removeAllListeners();
  }

  emitEvent(event: RpcEvent): void {
    this.transport.send(event);
  }

  private async handleMessage(payload: unknown): Promise<void> {
    const validation = validateRpcRequest(payload);
    if (!validation.ok) {
      const response: RpcResponse = {
        id: "unknown",
        method: (payload as RpcRequest | undefined)?.method ?? "startWork",
        ok: false,
        error: validation.error,
      } as RpcResponse;
      this.transport.send(response);
      return;
    }

    const request = validation.data;
    const handler = this.handlers.get(request.method as RpcMethod) as RpcHandler | undefined;
    if (!handler) {
      this.transport.send({
        id: request.id,
        method: request.method,
        ok: false,
        error: {
          code: "RPC_UNKNOWN_METHOD",
          message: `Unknown RPC method: ${request.method}`,
        },
      } as RpcResponse);
      return;
    }

    const controller = new AbortController();
    this.inflight.set(request.id, controller);

    const timeout = new Promise<never>((_resolve, reject) => {
      const timer = setTimeout(() => {
        controller.abort();
        reject(new Error("RPC request timed out"));
      }, this.requestTimeoutMs);
      timer.unref?.();
    });

    const context: RpcHandlerContext = {
      emitEvent: (event) => this.emitEvent(event),
      now: () => new Date().toISOString(),
    };

    try {
      const result = await Promise.race([
        handler(request.params as never, context),
        timeout,
      ]);

      this.transport.send({
        id: request.id,
        method: request.method,
        ok: true,
        result,
      } as RpcResponse);
    } catch (error) {
      this.transport.send({
        id: request.id,
        method: request.method,
        ok: false,
        error: {
          code: "RPC_HANDLER_ERROR",
          message: error instanceof Error ? error.message : "Unknown handler error",
        },
      } as RpcResponse);
    } finally {
      this.inflight.delete(request.id);
    }
  }
}

export const createRpcServer = (options: RpcServerOptions): RpcServer => new RpcServer(options);
