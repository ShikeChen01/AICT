import { z } from 'zod';

const sizeHintSchema = z.enum(['xs', 's', 'm', 'l', 'xl']);
const entityStatusSchema = z.enum(['todo', 'doing', 'review', 'done']);
const entityTestsSchema = z.object({
  block_test: z.string().optional(),
  module_test: z.string().optional()
});

const baseEntitySchema = z.object({
  id: z.string().min(1),
  name: z.string().min(1),
  purpose: z.string(),
  exports: z.array(z.string()),
  imports: z.array(z.string()),
  deps: z.array(z.string()),
  children: z.array(z.string().uuid()),
  tests: entityTestsSchema.default({}),
  size_hint: sizeHintSchema.default('m'),
  status: entityStatusSchema.default('todo')
});

export const BucketSchema = baseEntitySchema.extend({
  type: z.literal('bucket'),
  path: z.string().optional()
});
export type BucketSchemaType = z.infer<typeof BucketSchema>;

export const ModuleSchema = baseEntitySchema.extend({
  type: z.literal('module'),
  path: z.string().optional()
});
export type ModuleSchemaType = z.infer<typeof ModuleSchema>;

export const BlockSchema = baseEntitySchema.extend({
  type: z.literal('block'),
  path: z.string().min(1)
});
export type BlockSchemaType = z.infer<typeof BlockSchema>;

export const EntitySchema = z.discriminatedUnion('type', [
  BucketSchema,
  ModuleSchema,
  BlockSchema
]);
export type EntitySchemaType = z.infer<typeof EntitySchema>;

const canvasLayoutSchema = z.object({
  nodes: z.array(
    z.object({
      id: z.string(),
      position: z.object({ x: z.number(), y: z.number() }),
      type: z.string().optional()
    })
  ),
  edges: z.array(
    z.object({
      id: z.string(),
      source: z.string(),
      target: z.string(),
      type: z.string().optional()
    })
  ),
  viewport: z
    .object({ x: z.number(), y: z.number(), zoom: z.number() })
    .optional()
});

export const WorkspaceStateSchema = z.object({
  entities: z.array(EntitySchema),
  canvas: canvasLayoutSchema.optional()
});
export type WorkspaceStateSchemaType = z.infer<typeof WorkspaceStateSchema>;
