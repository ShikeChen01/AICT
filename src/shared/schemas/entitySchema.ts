import { z } from "zod";

const EntityTestsSchema = z
  .object({
    block_test: z.string().optional(),
    module_test: z.string().optional(),
  })
  .optional();

const BaseEntitySchema = z.object({
  id: z.string(),
  type: z.enum(["bucket", "module", "block"]),
  name: z.string(),
  purpose: z.string(),
  exports: z.array(z.string()).default([]),
  imports: z.array(z.string()).default([]),
  deps: z.array(z.string()).default([]),
  children: z.array(z.string()).default([]),
  tests: EntityTestsSchema,
  size_hint: z.enum(["xs", "s", "m", "l", "xl"]).optional(),
  status: z.enum(["todo", "doing", "review", "done"]).optional(),
  path: z.string().optional(),
});

export const BucketSchema = BaseEntitySchema.extend({
  type: z.literal("bucket"),
});

export const ModuleSchema = BaseEntitySchema.extend({
  type: z.literal("module"),
});

export const BlockSchema = BaseEntitySchema.extend({
  type: z.literal("block"),
  path: z.string(),
});

export const EntitySchema = z.union([BucketSchema, ModuleSchema, BlockSchema]);
