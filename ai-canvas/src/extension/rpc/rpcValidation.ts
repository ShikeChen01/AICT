import { RpcRequestSchema, RpcResponseSchema } from '../../shared/schemas/rpcSchema';
import type { RpcRequest, RpcResponse } from '../../shared/types/rpc';

export interface ValidationResult<T> {
  success: true;
  data: T;
}
export interface ValidationError {
  success: false;
  error: string;
}

export function validateRpcRequest(raw: unknown): ValidationResult<RpcRequest> | ValidationError {
  const parsed = RpcRequestSchema.safeParse(raw);
  if (!parsed.success) {
    const msg = parsed.error.issues.map((i) => i.message).join('; ') || 'Invalid request';
    return { success: false, error: msg };
  }
  return { success: true, data: parsed.data as RpcRequest };
}

export function validateRpcResponse(raw: unknown): ValidationResult<RpcResponse> | ValidationError {
  const parsed = RpcResponseSchema.safeParse(raw);
  if (!parsed.success) {
    const msg = parsed.error.issues.map((i) => i.message).join('; ') || 'Invalid response';
    return { success: false, error: msg };
  }
  return { success: true, data: parsed.data as RpcResponse };
}
