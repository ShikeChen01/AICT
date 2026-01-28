import { randomUUID } from "node:crypto";
import type {
  AgentMode,
  ApplyPatchParams,
  ApplyPatchResult,
  CancelJobResult,
  ExportBundleParams,
  ExportBundleResult,
  RepoIndexResult,
  RpcEvent,
  RpcMethod,
  RpcRequestPayloads,
  RpcResponsePayloads,
  RunTestsParams,
  RunTestsResult,
  StartWorkParams,
  StartWorkResult,
} from "src/shared/types/rpc";
import type { Job } from "src/shared/types/jobs";
import { buildContextBundle } from "src/extension/cloud/contextPackager";
import type { CloudGateway } from "src/extension/cloud/gatewayClient";
import type { PolicyEngine } from "src/extension/policy/policyEngine";
import type { PatchEngine } from "src/extension/patch/patchEngine";
import { discoverTestCommands } from "src/extension/repoIndex/testCommandDiscovery";
import type { RepoIndexService } from "src/extension/repoIndex/repoIndexer";
import type { CommandRunner } from "src/extension/runner/commandRunner";
import type { WorkspaceStore, CacheStore } from "src/extension/storage/storageTypes";

// Core RPC handlers: map RPC methods to policy-aware host operations.
export type RpcHandlerContext = {
  emitEvent: (event: RpcEvent) => void;
  now: () => string;
};

export type RpcHandler<M extends RpcMethod = RpcMethod> = (
  params: RpcRequestPayloads[M],
  ctx: RpcHandlerContext,
) => Promise<RpcResponsePayloads[M]>;

export type RpcHandlerRegistry = Map<RpcMethod, RpcHandler<any>>;

export type RpcHandlerDeps = {
  workspaceRoot: string;
  policy: PolicyEngine;
  runner: CommandRunner;
  patchEngine: PatchEngine;
  repoIndexer: RepoIndexService;
  workspaceStore: WorkspaceStore;
  cacheStore: CacheStore;
  cloud: CloudGateway;
};

type JobController = {
  job: Job;
  abort?: () => void;
};

const createJob = (type: Job["type"], now: string): Job => ({
  id: randomUUID(),
  type,
  status: "queued",
  created_at: now,
});

const emitJobStatus = (ctx: RpcHandlerContext, job: Job): void => {
  ctx.emitEvent({ type: "jobStatus", job });
};

const updateJob = (ctx: RpcHandlerContext, job: Job, update: Partial<Job>): Job => {
  const next: Job = { ...job, ...update };
  emitJobStatus(ctx, next);
  return next;
};

const buildDefaultPrompt = (mode: AgentMode, scopeId: string, prompt?: string): string => {
  const header = `Scope: ${scopeId}\nMode: ${mode}`;
  if (!prompt) {
    return `${header}\n\nProvide the requested output following the schema and constraints.`;
  }
  return `${header}\n\nUser prompt:\n${prompt}`;
};

export const registerCoreHandlers = (deps: RpcHandlerDeps): RpcHandlerRegistry => {
  const handlers: RpcHandlerRegistry = new Map();
  const jobControllers = new Map<string, JobController>();

  handlers.set("startWork", async (params: StartWorkParams, ctx): Promise<StartWorkResult> => {
    const decision = deps.policy.evaluate({
      kind: "startWork",
      scopeId: params.scope_id,
      guardrails: params.guardrails,
    });

    if (!decision.allow) {
      throw new Error(`Policy denied startWork: ${decision.reasons.join("; ")}`);
    }

    const job = createJob("work", ctx.now());
    jobControllers.set(job.id, { job });
    emitJobStatus(ctx, job);

    const runningJob = updateJob(ctx, job, {
      status: "running",
      started_at: ctx.now(),
      message: "Contacting Claude for plan output.",
    });

    const prompt = buildDefaultPrompt(params.mode, params.scope_id, params.prompt);
    let plan: StartWorkResult["plan"];

    try {
      const controller = new AbortController();
      jobControllers.set(job.id, { job: runningJob, abort: () => controller.abort() });

      if (params.mode === "plan" || params.mode === "code" || params.mode === "refactor") {
        const workspace = await deps.workspaceStore.loadWorkspaceState(deps.workspaceRoot);
        const context = await buildContextBundle({
          root: deps.workspaceRoot,
          scopeId: params.scope_id,
          workspace,
          byteLimit: 120_000,
        });

        plan = await deps.cloud.plan({
          prompt,
          scopeId: params.scope_id,
          context,
          signal: controller.signal,
        });
      }

      updateJob(ctx, runningJob, {
        status: "succeeded",
        finished_at: ctx.now(),
        message: "Plan generated.",
      });
    } catch (error) {
      updateJob(ctx, runningJob, {
        status: "failed",
        finished_at: ctx.now(),
        error: error instanceof Error ? error.message : "Unknown error",
      });
      throw error;
    } finally {
      jobControllers.delete(job.id);
    }

    return { job_id: job.id, plan };
  });

  handlers.set("runTests", async (params: RunTestsParams, ctx): Promise<RunTestsResult> => {
    const job = createJob("tests", ctx.now());
    jobControllers.set(job.id, { job });
    emitJobStatus(ctx, job);

    const runningJob = updateJob(ctx, job, {
      status: "running",
      started_at: ctx.now(),
      message: "Running tests.",
    });

    try {
      let commands = params.commands;
      if (!commands || commands.length === 0) {
        const index = await deps.repoIndexer.buildRepoIndex(deps.workspaceRoot);
        commands = discoverTestCommands(index.manifests).map((cmd) => cmd.command);
      }

      const results = [] as Array<{ command: string; code: number | null }>;

      for (const command of commands) {
        const decision = deps.policy.evaluate({ kind: "runTests", command });
        if (!decision.allow) {
          throw new Error(`Policy denied command: ${decision.reasons.join("; ")}`);
        }

        const result = await deps.runner.runCommand({
          command,
          cwd: deps.workspaceRoot,
          timeoutMs: 10 * 60 * 1000,
          maxOutputBytes: 64 * 1024,
          onOutput: (chunk, stream) => {
            ctx.emitEvent({
              type: "jobLog",
              job_id: job.id,
              stream,
              text: chunk,
            });
          },
        });

        results.push({ command, code: result.code });
      }

      const failed = results.find((result) => result.code !== 0);
      updateJob(ctx, runningJob, {
        status: failed ? "failed" : "succeeded",
        finished_at: ctx.now(),
        message: failed ? `Test failed: ${failed.command}` : "All tests passed.",
      });
    } catch (error) {
      updateJob(ctx, runningJob, {
        status: "failed",
        finished_at: ctx.now(),
        error: error instanceof Error ? error.message : "Unknown error",
      });
      throw error;
    } finally {
      jobControllers.delete(job.id);
    }

    return { job_id: job.id };
  });

  handlers.set("applyPatch", async (params: ApplyPatchParams, ctx): Promise<ApplyPatchResult> => {
    const job = createJob("patch", ctx.now());
    jobControllers.set(job.id, { job });
    emitJobStatus(ctx, job);

    const runningJob = updateJob(ctx, job, {
      status: "running",
      started_at: ctx.now(),
      message: "Applying patch.",
    });

    try {
      const decision = deps.policy.evaluate({ kind: "applyPatch", diff: params.diff });
      if (!decision.allow) {
        throw new Error(`Policy denied patch: ${decision.reasons.join("; ")}`);
      }

      await deps.patchEngine.applyPatch({
        diff: params.diff,
        root: deps.workspaceRoot,
        runFormatters: params.run_formatters ?? false,
      });

      updateJob(ctx, runningJob, {
        status: "succeeded",
        finished_at: ctx.now(),
        message: "Patch applied.",
      });
    } catch (error) {
      updateJob(ctx, runningJob, {
        status: "failed",
        finished_at: ctx.now(),
        error: error instanceof Error ? error.message : "Unknown error",
      });
      throw error;
    } finally {
      jobControllers.delete(job.id);
    }

    return { job_id: job.id };
  });

  handlers.set("repoIndex", async (_params, ctx): Promise<RepoIndexResult> => {
    const index = await deps.repoIndexer.buildRepoIndex(deps.workspaceRoot);
    await deps.cacheStore.saveCache(deps.workspaceRoot, {
      version: 1,
      repo_index: index,
      updated_at: ctx.now(),
    });
    ctx.emitEvent({ type: "repoIndex", index });
    return { index };
  });

  handlers.set("exportBundle", async (params: ExportBundleParams, ctx): Promise<ExportBundleResult> => {
    const workspace = await deps.workspaceStore.loadWorkspaceState(deps.workspaceRoot);
    const cache = await deps.cacheStore.loadCache(deps.workspaceRoot);

    const bundle = await buildContextBundle({
      root: deps.workspaceRoot,
      scopeId: params.scope_id,
      workspace,
      repoIndex: cache?.repo_index,
      includeLogs: params.include_logs ?? false,
      byteLimit: 120_000,
    });

    return { bundle };
  });

  handlers.set("cancelJob", async (params: RpcRequestPayloads["cancelJob"], ctx): Promise<CancelJobResult> => {
    const controller = jobControllers.get(params.job_id);
    if (!controller) {
      return { canceled: false };
    }

    controller.abort?.();
    updateJob(ctx, controller.job, {
      status: "canceled",
      finished_at: ctx.now(),
      message: "Canceled by user.",
    });

    jobControllers.delete(params.job_id);
    return { canceled: true };
  });

  return handlers;
};
