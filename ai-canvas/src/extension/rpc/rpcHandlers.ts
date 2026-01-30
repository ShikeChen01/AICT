import type { RpcHandler } from './rpcServer';
import type { LoadWorkspaceStateResult, SaveWorkspaceStateParams, ListWorkspaceFilesResult } from '../../shared/types/rpc';
import type { WorkspaceState } from '../storage/storageTypes';
import { loadWorkspaceState, saveWorkspaceState } from '../storage/workspaceStore';

export interface Mvp0HandlerDeps {
  getWorkspaceRoot: () => string;
}

export type RpcHandlerRegistry = Map<string, RpcHandler>;

/**
 * Register MVP-0 RPC handlers: loadWorkspaceState, saveWorkspaceState, listWorkspaceFiles.
 */
export function registerMvp0Handlers(deps: Mvp0HandlerDeps): RpcHandlerRegistry {
  const registry = new Map<string, RpcHandler>();

  registry.set('loadWorkspaceState', async (): Promise<LoadWorkspaceStateResult> => {
    const root = deps.getWorkspaceRoot();
    if (!root) {
      return { entities: [], canvas: undefined };
    }
    const state = await loadWorkspaceState(root);
    return {
      entities: state.entities,
      canvas: state.canvas
    };
  });

  registry.set('saveWorkspaceState', async (params: unknown): Promise<{ ok: boolean }> => {
    const root = deps.getWorkspaceRoot();
    if (!root) {
      throw new Error('No workspace folder open');
    }
    const p = params as SaveWorkspaceStateParams;
    if (!p?.entities || !Array.isArray(p.entities)) {
      throw new Error('saveWorkspaceState requires { entities }');
    }
    const state: WorkspaceState = {
      entities: p.entities,
      canvas: p.canvas
    };
    await saveWorkspaceState(root, state);
    return { ok: true };
  });

  registry.set('listWorkspaceFiles', async (): Promise<ListWorkspaceFilesResult> => {
    if (!deps.getWorkspaceRoot()) {
      return { files: [] };
    }
    const { workspace } = await import('vscode');
    const folders = workspace.workspaceFolders;
    if (!folders?.length) {
      return { files: [] };
    }
    const uris = await workspace.findFiles(
      '**/*',
      '{**/node_modules/**,**/.git/**}'
    );
    const files: ListWorkspaceFilesResult['files'] = [];
    for (const uri of uris) {
      const relative = workspace.asRelativePath(uri);
      const name = relative.split(/[/\\]/).pop() ?? relative;
      files.push({ path: relative, name, kind: 'file' });
    }
    return { files };
  });

  return registry;
}
