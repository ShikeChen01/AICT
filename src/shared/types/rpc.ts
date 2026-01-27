export type RpcMethod =
  | "startWork"
  | "runTests"
  | "applyPatch"
  | "repoIndex"
  | "exportBundle"
  | "cancelJob";

export interface RpcError {
  code: string;
  message: string;
  data?: unknown;
}

export interface RpcRequest<T = unknown> {
  id: string;
  method: RpcMethod;
  params: T;
}

export interface RpcResponse<T = unknown> {
  id: string;
  ok: boolean;
  result?: T;
  error?: RpcError;
}

export interface RpcEvent<T = unknown> {
  event: string;
  payload: T;
}
