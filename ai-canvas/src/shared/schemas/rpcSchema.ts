import { z } from "zod";
import { ContextBundleSchema } from "src/shared/schemas/contextSchema";
import { UnifiedDiffSchema } from "src/shared/schemas/diffSchema";
import { JobSchema } from "src/shared/schemas/jobSchema";
import { PlanSchema } from "src/shared/schemas/planSchema";

const GuardrailsSchema = z.object({
  enforce_scope: z.boolean().optional(),
  block_deps: z.boolean().optional(),
  block_network: z.boolean().optional(),
});

const StartWorkParamsSchema = z.object({
  scope_id: z.string().min(1),
  mode: z.enum(["plan", "code", "tests", "refactor"]),
  prompt: z.string().optional(),
  guardrails: GuardrailsSchema.optional(),
});

const RunTestsParamsSchema = z.object({
  scope_id: z.string().min(1),
  commands: z.array(z.string()).optional(),
});

const ApplyPatchParamsSchema = z.object({
  diff: UnifiedDiffSchema,
  run_formatters: z.boolean().optional(),
});

const RepoIndexParamsSchema = z.object({
  refresh: z.boolean().optional(),
});

const ExportBundleParamsSchema = z.object({
  scope_id: z.string().min(1),
  include_logs: z.boolean().optional(),
});

const CancelJobParamsSchema = z.object({
  job_id: z.string().min(1),
});

const ManifestSchema = z.object({
  path: z.string().min(1),
  kind: z.string().min(1),
  scripts: z.record(z.string()),
});

const SymbolSchema = z.object({
  path: z.string().min(1),
  exports: z.array(z.string()),
});

const RepoIndexSchema = z.object({
  root: z.string().min(1),
  files: z.array(z.string()),
  manifests: z.array(ManifestSchema),
  import_graph: z.record(z.array(z.string())),
  symbols: z.array(SymbolSchema),
  updated_at: z.string().min(1),
});

const StartWorkResultSchema = z.object({
  job_id: z.string().min(1),
  plan: PlanSchema.optional(),
});

const RunTestsResultSchema = z.object({
  job_id: z.string().min(1),
});

const ApplyPatchResultSchema = z.object({
  job_id: z.string().min(1),
});

const RepoIndexResultSchema = z.object({
  index: RepoIndexSchema,
});

const ExportBundleResultSchema = z.object({
  bundle: ContextBundleSchema,
});

const CancelJobResultSchema = z.object({
  canceled: z.boolean(),
});

const RpcRequestSchema = z.discriminatedUnion("method", [
  z.object({
    id: z.string().min(1),
    method: z.literal("startWork"),
    params: StartWorkParamsSchema,
  }),
  z.object({
    id: z.string().min(1),
    method: z.literal("runTests"),
    params: RunTestsParamsSchema,
  }),
  z.object({
    id: z.string().min(1),
    method: z.literal("applyPatch"),
    params: ApplyPatchParamsSchema,
  }),
  z.object({
    id: z.string().min(1),
    method: z.literal("repoIndex"),
    params: RepoIndexParamsSchema,
  }),
  z.object({
    id: z.string().min(1),
    method: z.literal("exportBundle"),
    params: ExportBundleParamsSchema,
  }),
  z.object({
    id: z.string().min(1),
    method: z.literal("cancelJob"),
    params: CancelJobParamsSchema,
  }),
]);

const RpcErrorSchema = z.object({
  code: z.string().min(1),
  message: z.string().min(1),
  details: z.string().optional(),
});

const RpcSuccessResponseSchema = z.discriminatedUnion("method", [
  z.object({
    id: z.string().min(1),
    method: z.literal("startWork"),
    ok: z.literal(true),
    result: StartWorkResultSchema,
  }),
  z.object({
    id: z.string().min(1),
    method: z.literal("runTests"),
    ok: z.literal(true),
    result: RunTestsResultSchema,
  }),
  z.object({
    id: z.string().min(1),
    method: z.literal("applyPatch"),
    ok: z.literal(true),
    result: ApplyPatchResultSchema,
  }),
  z.object({
    id: z.string().min(1),
    method: z.literal("repoIndex"),
    ok: z.literal(true),
    result: RepoIndexResultSchema,
  }),
  z.object({
    id: z.string().min(1),
    method: z.literal("exportBundle"),
    ok: z.literal(true),
    result: ExportBundleResultSchema,
  }),
  z.object({
    id: z.string().min(1),
    method: z.literal("cancelJob"),
    ok: z.literal(true),
    result: CancelJobResultSchema,
  }),
]);

const RpcErrorResponseSchema = z.object({
  id: z.string().min(1),
  method: z.enum([
    "startWork",
    "runTests",
    "applyPatch",
    "repoIndex",
    "exportBundle",
    "cancelJob",
  ]),
  ok: z.literal(false),
  error: RpcErrorSchema,
});

const RpcResponseSchema = z.union([
  RpcSuccessResponseSchema,
  RpcErrorResponseSchema,
]);

const RpcEventSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("jobStatus"),
    job: JobSchema,
  }),
  z.object({
    type: z.literal("jobLog"),
    job_id: z.string().min(1),
    stream: z.enum(["stdout", "stderr"]),
    text: z.string(),
  }),
  z.object({
    type: z.literal("repoIndex"),
    index: RepoIndexSchema,
  }),
]);

export { RpcRequestSchema, RpcResponseSchema, RpcEventSchema, RepoIndexSchema };
