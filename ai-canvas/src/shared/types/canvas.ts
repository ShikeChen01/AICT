/**
 * Canvas-specific types for nodes/edges and UI state.
 */

import type { Entity, EntityId } from './entities';

export type FocusMode = 'workspace' | 'bucket' | 'module';

export interface Viewport {
  x: number;
  y: number;
  zoom: number;
}

export interface BaseNodeData extends Record<string, unknown> {
  entity: Entity;
  isInScope: boolean;
  isDimmed: boolean;
}

export interface BucketNodeData extends BaseNodeData {
  modulesCount: number;
  blocksCount: number;
  progress: { done: number; total: number };
  activeAgents: number;
}

export interface ModuleNodeData extends BaseNodeData {
  depsCount: number;
  blocksCount: number;
  progress: { done: number; total: number };
}

export interface BlockNodeData extends BaseNodeData {
  fileIcon: string;
  testPassed: boolean;
}

export type NodeData = BucketNodeData | ModuleNodeData | BlockNodeData;

export type CanvasEdgeType = 'dependency' | 'api';

/** Custom canvas edge: bidirectional, stored as nodes tuple. */
export interface CanvasEdge {
  id: string;
  nodes: [string, string];
  type: CanvasEdgeType;
  data?: DependencyEdgeData;
}

export interface ApiContract {
  name: string;
  type: 'HTTP' | 'gRPC' | 'EVENT' | 'QUEUE';
  endpoint: string;
  auth: string;
  version: string;
}

export interface DependencyEdgeData extends Record<string, unknown> {
  dependencyType: 'depends_on';
  hasApiContract: boolean;
  apiContract?: ApiContract;
}


export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: number;
}

export type AgentMode = 'plan-only' | 'code+tests' | 'tests-only' | 'docs-only';

export type AgentStatus = 'idle' | 'planning' | 'writing' | 'testing';
