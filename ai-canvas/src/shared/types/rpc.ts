import type { EntityId } from "src/shared/types/entities";
import type { Plan } from "src/shared/types/plan";
import type { UnifiedDiff } from "src/shared/types/diff";
import type { ContextBundle } from "src/shared/types/context";
import type { Job } from "src/shared/types/jobs";

type AgentMode = "plan" | "code" | "tests" | "refactor";

type Guardrails = {
  enforce_scope?: boolean;
  block_deps?: boolean;
  block_network?: boolean;
};

type StartWorkParams = {
  scope_id: EntityId;
  mode: AgentMode;
  prompt?: string;
  guardrails?: Guardrails;
};

type RunTestsParams = {
  scope_id: EntityId;
  commands?: string[];
};

type ApplyPatchParams = {
  diff: UnifiedDiff;
  run_formatters?: boolean;
};

type RepoIndexParams = {
  refresh?: boolean;
};

type ExportBundleParams = {
  scope_id: EntityId;
  include_logs?: boolean;
};

type CancelJobParams = {
  job_id: string;
};

type StartWorkResult = {
  job_id: string;
  plan?: Plan;
};

type RunTestsResult = {
  job_id: string;
};

type ApplyPatchResult = {
  job_id: string;
};

type RepoIndexResult = {
  index: RepoIndex;
};

type ExportBundleResult = {
  bundle: ContextBundle;
};

type CancelJobResult = {
  canceled: boolean;
};

type RpcError = {
  code: string;
  message: string;
  details?: string;
};

type ManifestInfo = {
  path: string;
  kind: string;
  scripts: Record<string, string>;
};

type SymbolInfo = {
  path: string;
  exports: string[];
};

type RepoIndex = {
  root: string;
  files: string[];
  manifests: ManifestInfo[];
  import_graph: Record<string, string[]>;
  symbols: SymbolInfo[];
  updated_at: string;
};

export type RpcRequestPayloads = {
  startWork: StartWorkParams;
  runTests: RunTestsParams;
  applyPatch: ApplyPatchParams;
  repoIndex: RepoIndexParams;
  exportBundle: ExportBundleParams;
  cancelJob: CancelJobParams;
};

export type RpcResponsePayloads = {
  startWork: StartWorkResult;
  runTests: RunTestsResult;
  applyPatch: ApplyPatchResult;
  repoIndex: RepoIndexResult;
  exportBundle: ExportBundleResult;
  cancelJob: CancelJobResult;
};

export type RpcMethod = keyof RpcRequestPayloads;

export type RpcRequest<M extends RpcMethod = RpcMethod> = {
  id: string;
  method: M;
  params: RpcRequestPayloads[M];
};

type RpcSuccessResponse<M extends RpcMethod = RpcMethod> = {
  id: string;
  method: M;
  ok: true;
  result: RpcResponsePayloads[M];
};

type RpcErrorResponse<M extends RpcMethod = RpcMethod> = {
  id: string;
  method: M;
  ok: false;
  error: RpcError;
};

export type RpcResponse<M extends RpcMethod = RpcMethod> =
  | RpcSuccessResponse<M>
  | RpcErrorResponse<M>;

export type RpcEvent =
  | { type: "jobStatus"; job: Job }
  | { type: "jobLog"; job_id: string; stream: "stdout" | "stderr"; text: string }
  | { type: "repoIndex"; index: RepoIndex };

export type {
  AgentMode,
  Guardrails,
  StartWorkParams,
  RunTestsParams,
  ApplyPatchParams,
  RepoIndexParams,
  ExportBundleParams,
  CancelJobParams,
  StartWorkResult,
  RunTestsResult,
  ApplyPatchResult,
  RepoIndexResult,
  ExportBundleResult,
  CancelJobResult,
  RpcError,
  ManifestInfo,
  SymbolInfo,
  RepoIndex,
};
