import type { RpcMethod } from "../../shared/types/rpc";

export interface RpcHandlerContext {
  method: RpcMethod;
  emitEvent: (event: string, payload: unknown) => void;
}

export type RpcHandler = (params: unknown, context: RpcHandlerContext) => Promise<unknown>;
export type RpcHandlerRegistry = Map<RpcMethod, RpcHandler>;

export interface CoreHandlerDeps {
  startWork?: (params: unknown, context: RpcHandlerContext) => Promise<unknown>;
  runTests?: (params: unknown, context: RpcHandlerContext) => Promise<unknown>;
  applyPatch?: (params: unknown, context: RpcHandlerContext) => Promise<unknown>;
  repoIndex?: (params: unknown, context: RpcHandlerContext) => Promise<unknown>;
  exportBundle?: (params: unknown, context: RpcHandlerContext) => Promise<unknown>;
  cancelJob?: (params: unknown, context: RpcHandlerContext) => Promise<unknown>;
}

function buildMissingHandlerError(method: RpcMethod): Error {
  return new Error(`Handler not configured for ${method}`);
}

export function registerCoreHandlers(deps: CoreHandlerDeps): RpcHandlerRegistry {
  return new Map<RpcMethod, RpcHandler>([
    ["startWork", async (params, context) => {
      if (!deps.startWork) {
        throw buildMissingHandlerError("startWork");
      }
      return deps.startWork(params, context);
    }],
    ["runTests", async (params, context) => {
      if (!deps.runTests) {
        throw buildMissingHandlerError("runTests");
      }
      return deps.runTests(params, context);
    }],
    ["applyPatch", async (params, context) => {
      if (!deps.applyPatch) {
        throw buildMissingHandlerError("applyPatch");
      }
      return deps.applyPatch(params, context);
    }],
    ["repoIndex", async (params, context) => {
      if (!deps.repoIndex) {
        throw buildMissingHandlerError("repoIndex");
      }
      return deps.repoIndex(params, context);
    }],
    ["exportBundle", async (params, context) => {
      if (!deps.exportBundle) {
        throw buildMissingHandlerError("exportBundle");
      }
      return deps.exportBundle(params, context);
    }],
    ["cancelJob", async (params, context) => {
      if (!deps.cancelJob) {
        throw buildMissingHandlerError("cancelJob");
      }
      return deps.cancelJob(params, context);
    }],
  ]);
}
