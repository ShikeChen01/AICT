import { EventEmitter } from "node:events";
import type { RpcError, RpcEvent, RpcRequest, RpcResponse } from "../../shared/types/rpc";
import type { RpcHandlerContext, RpcHandlerRegistry } from "./rpcHandlers";
import type { RpcTransport } from "./rpcTransport";
import { validateRpcRequest } from "./rpcValidation";

export interface RpcServerOptions {
  transport: RpcTransport;
  handlers: RpcHandlerRegistry;
  timeoutMs?: number;
}

export class RpcServer extends EventEmitter {
  private readonly transport: RpcTransport;
  private readonly handlers: RpcHandlerRegistry;
  private readonly timeoutMs: number;
  private readonly inFlight = new Map<string, NodeJS.Timeout>();
  private readonly disposable: { dispose: () => void };

  constructor(options: RpcServerOptions) {
    super();
    this.transport = options.transport;
    this.handlers = options.handlers;
    this.timeoutMs = options.timeoutMs ?? 30_000;
    this.disposable = this.transport.onRequest((request) => {
      void this.handleRequest(request);
    });
  }

  emitEvent(event: string, payload: unknown): void {
    const message: RpcEvent = { event, payload };
    this.transport.send(message);
    this.emit(event, payload);
  }

  dispose(): void {
    this.disposable.dispose();
    this.transport.dispose();
    for (const timeout of this.inFlight.values()) {
      clearTimeout(timeout);
    }
    this.inFlight.clear();
    this.removeAllListeners();
  }

  private async handleRequest(raw: unknown): Promise<void> {
    const validation = validateRpcRequest(raw);
    if (!validation.ok) {
      this.transport.send(this.buildErrorResponse("invalid_request", validation.error, raw));
      return;
    }

    const request = validation.data;
    const handler = this.handlers.get(request.method);
    if (!handler) {
      this.transport.send(this.buildErrorResponse("unknown_method", `Unknown method: ${request.method}`, request));
      return;
    }

    let settled = false;
    const finalize = (response: RpcResponse) => {
      if (settled) {
        return;
      }
      settled = true;
      const timeout = this.inFlight.get(request.id);
      if (timeout) {
        clearTimeout(timeout);
        this.inFlight.delete(request.id);
      }
      this.transport.send(response);
    };

    const timeout = setTimeout(() => {
      finalize(this.buildErrorResponse("timeout", "Request timed out", request));
    }, this.timeoutMs);
    this.inFlight.set(request.id, timeout);

    try {
      const context: RpcHandlerContext = {
        method: request.method,
        emitEvent: (event, payload) => this.emitEvent(event, payload),
      };
      const result = await handler(request.params, context);
      finalize({ id: request.id, ok: true, result });
    } catch (error) {
      finalize(this.buildErrorResponse("handler_error", this.formatError(error), request));
    }
  }

  private buildErrorResponse(code: string, message: string, request: unknown): RpcResponse {
    const id = typeof request === "object" && request !== null && "id" in request ? (request as RpcRequest).id : "unknown";
    const error: RpcError = { code, message };
    return { id, ok: false, error };
  }

  private formatError(error: unknown): string {
    if (error instanceof Error) {
      return error.message;
    }
    return String(error);
  }
}

export function createRpcServer(options: RpcServerOptions): RpcServer {
  return new RpcServer(options);
}
