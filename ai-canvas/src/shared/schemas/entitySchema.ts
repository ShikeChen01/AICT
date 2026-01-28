import { z } from "zod";

const AcceptanceCriterionSchema = z.object({
  id: z.string().min(1),
  text: z.string().min(1),
  done: z.boolean(),
});

const EntityTestsSchema = z.object({
  block_test: z.string().min(1).optional(),
  module_test: z.string().min(1).optional(),
});

const BaseEntitySchema = z.object({
  id: z.string().min(1),
  type: z.enum(["bucket", "module", "block"]),
  name: z.string().min(1),
  purpose: z.string().min(1),
  path: z.string().min(1).optional(),
  exports: z.array(z.string()).optional(),
  imports: z.array(z.string()).optional(),
  deps: z.array(z.string()).optional(),
  children: z.array(z.string()).optional(),
  tests: EntityTestsSchema.optional(),
  size_hint: z.enum(["xs", "s", "m", "l", "xl"]).optional(),
  status: z.enum(["todo", "doing", "review", "done"]).optional(),
  acceptance_criteria: z.array(AcceptanceCriterionSchema).optional(),
  tags: z.array(z.string()).optional(),
});

const BucketSchema = BaseEntitySchema.extend({
  type: z.literal("bucket"),
  external_apis: z.array(z.string()).optional(),
});

const ModuleSchema = BaseEntitySchema.extend({
  type: z.literal("module"),
});

const BlockSchema = BaseEntitySchema.extend({
  type: z.literal("block"),
  path: z.string().min(1),
});

const EntitySchema = z.discriminatedUnion("type", [
  BucketSchema,
  ModuleSchema,
  BlockSchema,
]);

export { EntitySchema, BucketSchema, ModuleSchema, BlockSchema };
