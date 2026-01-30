import type { RpcTransport } from './rpcTransport';
import type { RpcRequest, RpcResponse, RpcResponseError } from '../../shared/types/rpc';
import { validateRpcRequest } from './rpcValidation';

export type RpcHandler = (params: unknown) => Promise<unknown>;

export interface RpcServerOptions {
  transport: RpcTransport;
  handlers: Map<string, RpcHandler>;
  requestTimeoutMs?: number;
}

export interface RpcServer {
  start(): void;
  stop(): void;
}

function errorResponse(id: string, code: string, message: string): RpcResponseError {
  return { id, error: { code, message } };
}

/**
 * Listen on transport, route by method, call handlers, return structured errors.
 */
export function createRpcServer(options: RpcServerOptions): RpcServer {
  const { transport, handlers, requestTimeoutMs = 30_000 } = options;
  let unsubscribe: (() => void) | null = null;

  return {
    start(): void {
      unsubscribe = transport.onRequest(async (request: RpcRequest) => {
        const validated = validateRpcRequest(request);
        if (!validated.success) {
          transport.send(
            errorResponse(request.id, 'INVALID_REQUEST', validated.error)
          );
          return;
        }
        const { id, method, params } = validated.data;
        const handler = handlers.get(method);
        if (!handler) {
          transport.send(errorResponse(id, 'UNKNOWN_METHOD', `Unknown method: ${method}`));
          return;
        }
        try {
          const result = await Promise.race([
            handler(params),
            new Promise<never>((_, reject) =>
              setTimeout(() => reject(new Error('Request timeout')), requestTimeoutMs)
            )
          ]);
          transport.send({ id, result });
        } catch (err) {
          const message = err instanceof Error ? err.message : String(err);
          transport.send(errorResponse(id, 'HANDLER_ERROR', message));
        }
      });
    },
    stop(): void {
      if (unsubscribe) {
        unsubscribe();
        unsubscribe = null;
      }
      transport.dispose();
    }
  };
}
