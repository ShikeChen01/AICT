import { z } from 'zod';
import { WorkspaceStateSchema } from './entitySchema';

const rpcMethodSchema = z.enum([
  'loadWorkspaceState',
  'saveWorkspaceState',
  'listWorkspaceFiles'
]);

export const RpcRequestSchema = z.object({
  id: z.string(),
  method: rpcMethodSchema,
  params: z.unknown().optional()
});
export type RpcRequestSchemaType = z.infer<typeof RpcRequestSchema>;

export const RpcResponseSuccessSchema = z.object({
  id: z.string(),
  result: z.unknown(),
  error: z.undefined().optional()
});
export const RpcResponseErrorSchema = z.object({
  id: z.string(),
  result: z.undefined().optional(),
  error: z.object({ code: z.string(), message: z.string() })
});
export const RpcResponseSchema = z.union([
  RpcResponseSuccessSchema,
  RpcResponseErrorSchema
]);
export type RpcResponseSchemaType = z.infer<typeof RpcResponseSchema>;

export const LoadWorkspaceStateResultSchema = z.object({
  entities: WorkspaceStateSchema.shape.entities,
  canvas: WorkspaceStateSchema.shape.canvas.optional()
});
export const SaveWorkspaceStateParamsSchema = z.object({
  entities: WorkspaceStateSchema.shape.entities,
  canvas: WorkspaceStateSchema.shape.canvas.optional()
});
export const ListWorkspaceFilesResultSchema = z.object({
  files: z.array(
    z.object({
      path: z.string(),
      name: z.string(),
      kind: z.enum(['file', 'directory'])
    })
  )
});
