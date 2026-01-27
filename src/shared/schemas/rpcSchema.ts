import { z } from "zod";

export const RpcMethodSchema = z.enum([
  "startWork",
  "runTests",
  "applyPatch",
  "repoIndex",
  "exportBundle",
  "cancelJob",
]);

export const RpcRequestSchema = z.object({
  id: z.string(),
  method: RpcMethodSchema,
  params: z.unknown(),
});

export const RpcErrorSchema = z.object({
  code: z.string(),
  message: z.string(),
  data: z.unknown().optional(),
});

export const RpcResponseSchema = z.object({
  id: z.string(),
  ok: z.boolean(),
  result: z.unknown().optional(),
  error: RpcErrorSchema.optional(),
});

export const RpcEventSchema = z.object({
  event: z.string(),
  payload: z.unknown(),
});
