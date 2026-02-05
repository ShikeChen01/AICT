/**
 * Command and result types for canvas mutations.
 * All canvas mutations flow through CommandRegistry for unified undo/redo.
 */

import type { Entity, EntityStatus } from '../../shared/types/entities';
import type { Viewport } from '../../shared/types/canvas';

// Re-export for command payloads
export type { Entity, EntityStatus };

export type EntityType = 'bucket' | 'module' | 'block' | 'api_contract';

export interface Position {
  x: number;
  y: number;
}

export interface Size {
  width: number;
  height: number;
}

export type EdgeType = 'dependency' | 'api';

export type CanvasCommand =
  | {
      type: 'CREATE_ENTITY';
      payload: {
        entityType: EntityType;
        name: string;
        purpose: string;
        parentId?: string;
      };
    }
  | { type: 'UPDATE_ENTITY'; payload: { id: string; updates: Partial<Entity> } }
  | { type: 'DELETE_ENTITY'; payload: { id: string } }
  | { type: 'MOVE_ENTITY'; payload: { id: string; newParentId: string | null } }
  | { type: 'SET_ENTITY_STATUS'; payload: { id: string; status: EntityStatus } }
  | {
      type: 'CREATE_EDGE';
      payload: { nodes: [string, string]; type: EdgeType };
    }
  | { type: 'UPDATE_EDGE'; payload: { id: string; nodes: [string, string] } }
  | { type: 'DELETE_EDGE'; payload: { id: string } }
  | {
      type: 'SET_NODE_POSITION';
      payload: { id: string; position: Position };
    }
  | { type: 'SET_NODE_SIZE'; payload: { id: string; size: Size } }
  | { type: 'SET_VIEWPORT'; payload: Viewport }
  | { type: 'SET_SCOPE'; payload: { entityId: string | null } }
  | { type: 'BATCH'; payload: { commands: CanvasCommand[] } };

export interface CommandResult {
  success: boolean;
  data?: unknown;
  error?: CommandError;
}

export interface CommandError {
  code: string;
  message: string;
  suggestion?: string;
}

export interface ExecutedCommand {
  command: CanvasCommand;
  inverse: CanvasCommand;
  timestamp: number;
}
