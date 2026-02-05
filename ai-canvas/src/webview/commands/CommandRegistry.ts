/**
 * Central registry for canvas mutations. All mutations (user and agent) flow through here
 * for unified undo/redo and operation logging.
 */

import type { AppDispatch, RootState } from '../store/store';
import type { CanvasCommand, CommandResult, ExecutedCommand } from './types';
import type { Entity } from '../../shared/types/entities';
import { CommandHistory } from './CommandHistory';

import {
  addEntity,
  updateEntity,
  removeEntity,
  setParent,
  createBucket,
  createModule,
  createBlock,
} from '../store/slices/entitiesSlice';
import {
  addEdge,
  updateEdge,
  removeEdge,
  setNodePosition,
  setNodeSize,
  setViewport,
} from '../store/slices/canvasSlice';
import { setScope } from '../store/slices/uiSlice';

export class CommandRegistry {
  private dispatch: AppDispatch;
  private getState: () => RootState;
  private history: CommandHistory;

  constructor(
    dispatch: AppDispatch,
    getState: () => RootState,
    history?: CommandHistory
  ) {
    this.dispatch = dispatch;
    this.getState = getState;
    this.history = history ?? new CommandHistory();
  }

  execute(command: CanvasCommand): CommandResult {
    try {
      const inverse = this.computeInverse(command);
      const result = this.executeCommand(command);
      if (result.success && inverse) {
        this.history.push({
          command,
          inverse,
          timestamp: Date.now(),
        });
      }
      return result;
    } catch (e) {
      const err = e as Error;
      return {
        success: false,
        error: { code: 'EXECUTION_ERROR', message: err.message ?? 'Unknown error' },
      };
    }
  }

  undo(): CommandResult {
    const executed = this.history.popUndo();
    if (!executed) {
      return {
        success: false,
        error: { code: 'NOTHING_TO_UNDO', message: 'No commands to undo' },
      };
    }
    return this.executeCommand(executed.inverse);
  }

  redo(): CommandResult {
    const executed = this.history.popRedo();
    if (!executed) {
      return {
        success: false,
        error: { code: 'NOTHING_TO_REDO', message: 'No commands to redo' },
      };
    }
    return this.executeCommand(executed.command);
  }

  canUndo(): boolean {
    return this.history.canUndo();
  }

  canRedo(): boolean {
    return this.history.canRedo();
  }

  private executeCommand(command: CanvasCommand): CommandResult {
    switch (command.type) {
      case 'CREATE_ENTITY': {
        const { entityType, name, purpose, parentId } = command.payload;
        let entity: Entity;
        if (entityType === 'bucket') {
          entity = createBucket({ name, purpose });
        } else if (entityType === 'module' || entityType === 'api_contract') {
          entity = createModule({ name, purpose });
        } else {
          entity = createBlock({ name, purpose, path: 'untitled' });
        }
        this.dispatch(addEntity(entity));
        if (parentId) {
          this.dispatch(setParent({ childId: entity.id, parentId }));
        }
        return { success: true, data: entity };
      }
      case 'UPDATE_ENTITY': {
        this.dispatch(updateEntity({
          id: command.payload.id,
          changes: command.payload.updates,
        }));
        return { success: true };
      }
      case 'DELETE_ENTITY': {
        this.dispatch(removeEntity(command.payload.id));
        return { success: true };
      }
      case 'MOVE_ENTITY': {
        this.dispatch(setParent({
          childId: command.payload.id,
          parentId: command.payload.newParentId,
        }));
        return { success: true };
      }
      case 'SET_ENTITY_STATUS': {
        this.dispatch(updateEntity({
          id: command.payload.id,
          changes: { status: command.payload.status },
        }));
        return { success: true };
      }
      case 'CREATE_EDGE': {
        const id = `e-${command.payload.nodes[0]}-${command.payload.nodes[1]}-${Date.now()}`;
        this.dispatch(addEdge({
          id,
          nodes: command.payload.nodes,
          type: command.payload.type,
        }));
        return { success: true, data: { id } };
      }
      case 'UPDATE_EDGE': {
        this.dispatch(updateEdge(command.payload));
        return { success: true };
      }
      case 'DELETE_EDGE': {
        this.dispatch(removeEdge(command.payload.id));
        return { success: true };
      }
      case 'SET_NODE_POSITION': {
        this.dispatch(setNodePosition(command.payload));
        return { success: true };
      }
      case 'SET_NODE_SIZE': {
        this.dispatch(setNodeSize(command.payload));
        return { success: true };
      }
      case 'SET_VIEWPORT': {
        this.dispatch(setViewport(command.payload));
        return { success: true };
      }
      case 'SET_SCOPE': {
        this.dispatch(setScope(command.payload.entityId));
        return { success: true };
      }
      case 'BATCH': {
        for (const cmd of command.payload.commands) {
          const result = this.executeCommand(cmd);
          if (!result.success) return result;
        }
        return { success: true };
      }
      default: {
        const _: never = command;
        return {
          success: false,
          error: { code: 'UNKNOWN_COMMAND', message: 'Unknown command type' },
        };
      }
    }
  }

  private computeInverse(command: CanvasCommand): CanvasCommand | null {
    const state = this.getState();

    switch (command.type) {
      case 'CREATE_ENTITY':
        return null;

      case 'UPDATE_ENTITY': {
        const entity = state.entities.byId[command.payload.id] as Entity | undefined;
        if (!entity) return null;
        const previousValues: Partial<Entity> = {};
        for (const key of Object.keys(command.payload.updates) as (keyof Entity)[]) {
          (previousValues as Record<string, unknown>)[key] = entity[key];
        }
        return {
          type: 'UPDATE_ENTITY',
          payload: { id: command.payload.id, updates: previousValues },
        };
      }

      case 'MOVE_ENTITY': {
        const childId = command.payload.id;
        let prevParentId: string | null = null;
        for (const entity of Object.values(state.entities.byId)) {
          if (entity.children.includes(childId)) {
            prevParentId = entity.id;
            break;
          }
        }
        return {
          type: 'MOVE_ENTITY',
          payload: { id: childId, newParentId: prevParentId },
        };
      }

      case 'DELETE_ENTITY': {
        const entity = state.entities.byId[command.payload.id] as Entity | undefined;
        if (!entity) return null;
        return {
          type: 'CREATE_ENTITY',
          payload: {
            entityType: entity.type as 'bucket' | 'module' | 'block' | 'api_contract',
            name: entity.name,
            purpose: entity.purpose,
          },
        };
      }

      case 'SET_ENTITY_STATUS': {
        const entity = state.entities.byId[command.payload.id];
        if (!entity) return null;
        return {
          type: 'SET_ENTITY_STATUS',
          payload: { id: command.payload.id, status: entity.status },
        };
      }

      case 'CREATE_EDGE':
        return null;

      case 'UPDATE_EDGE': {
        const edge = state.canvas.edges.find((e) => e.id === command.payload.id);
        if (!edge) return null;
        return {
          type: 'UPDATE_EDGE',
          payload: { id: command.payload.id, nodes: edge.nodes },
        };
      }

      case 'DELETE_EDGE': {
        const edge = state.canvas.edges.find((e) => e.id === command.payload.id);
        if (!edge) return null;
        return {
          type: 'CREATE_EDGE',
          payload: { nodes: edge.nodes, type: edge.type },
        };
      }

      case 'SET_NODE_POSITION': {
        const pos = state.canvas.nodePositions[command.payload.id];
        return {
          type: 'SET_NODE_POSITION',
          payload: {
            id: command.payload.id,
            position: pos ?? { x: 0, y: 0 },
          },
        };
      }

      case 'SET_NODE_SIZE': {
        const size = state.canvas.nodeSizes[command.payload.id];
        return {
          type: 'SET_NODE_SIZE',
          payload: {
            id: command.payload.id,
            size: size ?? { width: 200, height: 150 },
          },
        };
      }

      case 'SET_VIEWPORT': {
        const viewport = state.canvas.viewport;
        return { type: 'SET_VIEWPORT', payload: viewport };
      }

      case 'SET_SCOPE': {
        const currentScope = state.ui.scopeEntityId;
        return { type: 'SET_SCOPE', payload: { entityId: currentScope } };
      }

      case 'BATCH': {
        const inverses = command.payload.commands
          .map((cmd) => this.computeInverse(cmd))
          .filter((c): c is CanvasCommand => c != null)
          .reverse();
        return { type: 'BATCH', payload: { commands: inverses } };
      }

      default:
        return null;
    }
  }
}
