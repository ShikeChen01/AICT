/**
 * Tool definitions for LLM agents (schemas for canvas manipulation).
 */

import type { ToolDefinition } from './types';

export const toolDefinitions: ToolDefinition[] = [
  {
    name: 'get_architecture',
    description: 'Get the complete architecture snapshot (entities, edges, positions, sizes).',
    parameters: {},
  },
  {
    name: 'create_entity',
    description: 'Create a new bucket, module, block, or api_contract.',
    parameters: {
      type: {
        type: 'string',
        required: true,
        enum: ['bucket', 'module', 'block', 'api_contract'],
      },
      name: { type: 'string', required: true },
      purpose: { type: 'string', required: true },
      parentId: { type: 'string', required: false },
    },
  },
  {
    name: 'update_entity_status',
    description: 'Update the status of an entity (todo, doing, review, done).',
    parameters: {
      id: { type: 'string', required: true },
      status: {
        type: 'string',
        required: true,
        enum: ['todo', 'doing', 'review', 'done'],
      },
    },
  },
  {
    name: 'create_edge',
    description: 'Create a connection between two nodes.',
    parameters: {
      nodes: { type: 'array', required: true },
      type: { type: 'string', required: true, enum: ['dependency', 'api'] },
    },
  },
  {
    name: 'undo',
    description: 'Undo the last operation.',
    parameters: {},
  },
  {
    name: 'redo',
    description: 'Redo the last undone operation.',
    parameters: {},
  },
];
