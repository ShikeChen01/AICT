import { RpcRequestSchema, RpcResponseSchema } from "../../shared/schemas/rpcSchema";
import type { RpcRequest, RpcResponse } from "../../shared/types/rpc";

export type ValidationResult<T> = { ok: true; data: T } | { ok: false; error: string };

export function validateRpcRequest(payload: unknown): ValidationResult<RpcRequest> {
  const result = RpcRequestSchema.safeParse(payload);
  if (!result.success) {
    return { ok: false, error: result.error.message };
  }
  return { ok: true, data: result.data };
}

export function validateRpcResponse(payload: unknown): ValidationResult<RpcResponse> {
  const result = RpcResponseSchema.safeParse(payload);
  if (!result.success) {
    return { ok: false, error: result.error.message };
  }
  return { ok: true, data: result.data };
}
