/**
 * RPC request/response types for webview <-> extension host.
 * MVP-0: loadWorkspaceState, saveWorkspaceState, listWorkspaceFiles.
 */

import type { Entity } from './entities';

export type RpcMethod =
  | 'loadWorkspaceState'
  | 'saveWorkspaceState'
  | 'listWorkspaceFiles';

export interface RpcRequest {
  id: string;
  method: RpcMethod;
  params?: unknown;
}

export interface RpcResponseSuccess<T = unknown> {
  id: string;
  result: T;
  error?: never;
}

export interface RpcResponseError {
  id: string;
  result?: never;
  error: { code: string; message: string };
}

export type RpcResponse<T = unknown> = RpcResponseSuccess<T> | RpcResponseError;

export function isRpcError(r: RpcResponse): r is RpcResponseError {
  return 'error' in r && r.error !== undefined;
}

export interface CanvasLayout {
  nodes: Array<{
    id: string;
    position: { x: number; y: number };
    type?: string;
    size?: { width: number; height: number };
  }>;
  edges: Array<{ id: string; source: string; target: string; type?: string }>;
  viewport?: { x: number; y: number; zoom: number };
}

export interface LoadWorkspaceStateResult {
  entities: Entity[];
  canvas?: CanvasLayout;
}

export interface SaveWorkspaceStateParams {
  entities: Entity[];
  canvas?: CanvasLayout;
}

export interface ListWorkspaceFilesResult {
  files: Array<{ path: string; name: string; kind: 'file' | 'directory' }>;
}
