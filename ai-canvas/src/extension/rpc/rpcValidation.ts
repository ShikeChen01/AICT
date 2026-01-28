import { RpcRequestSchema, RpcResponseSchema } from "src/shared/schemas/rpcSchema";
import type { RpcError, RpcRequest, RpcResponse } from "src/shared/types/rpc";

export type ValidationResult<T> =
  | { ok: true; data: T }
  | { ok: false; error: RpcError };

const toRpcError = (code: string, message: string, details?: string): RpcError => ({
  code,
  message,
  details,
});

export const validateRpcRequest = (payload: unknown): ValidationResult<RpcRequest> => {
  const parsed = RpcRequestSchema.safeParse(payload);
  if (!parsed.success) {
    return {
      ok: false,
      error: toRpcError(
        "RPC_INVALID_REQUEST",
        "Invalid RPC request payload",
        parsed.error.message,
      ),
    };
  }

  return { ok: true, data: parsed.data };
};

export const validateRpcResponse = (payload: unknown): ValidationResult<RpcResponse> => {
  const parsed = RpcResponseSchema.safeParse(payload);
  if (!parsed.success) {
    return {
      ok: false,
      error: toRpcError(
        "RPC_INVALID_RESPONSE",
        "Invalid RPC response payload",
        parsed.error.message,
      ),
    };
  }

  return { ok: true, data: parsed.data };
};
