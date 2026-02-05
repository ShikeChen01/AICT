/**
 * Agent layer types: tool definitions, errors, architecture snapshot.
 */

import type { Entity } from '../../shared/types/entities';
import type { CanvasEdge } from '../../shared/types/canvas';

export interface ToolDefinition {
  name: string;
  description: string;
  parameters: Record<string, { type: string; required?: boolean; enum?: string[] }>;
}

export interface AgentError {
  code: string;
  message: string;
  suggestion?: string;
}

export interface ArchitectureSnapshot {
  entities: Entity[];
  edges: CanvasEdge[];
  nodePositions: Record<string, { x: number; y: number }>;
  nodeSizes: Record<string, { width: number; height: number }>;
}
