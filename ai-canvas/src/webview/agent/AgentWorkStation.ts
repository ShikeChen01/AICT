/**
 * Interface between cloud LLM agents and the canvas. Provides tool definitions,
 * command execution via CommandRegistry, and query methods.
 */

import type { CommandRegistry } from '../commands/CommandRegistry';
import type { RootState } from '../store/store';
import type { CanvasCommand, CommandResult } from '../commands/types';
import type { ToolDefinition, AgentError, ArchitectureSnapshot } from './types';
import type { Entity } from '../../shared/types/entities';
import { toolDefinitions } from './toolDefinitions';

export class AgentWorkStation {
  private commandRegistry: CommandRegistry;
  private getState: () => RootState;
  private onError?: (error: AgentError) => void;

  constructor(config: {
    commandRegistry: CommandRegistry;
    getState: () => RootState;
    onError?: (error: AgentError) => void;
  }) {
    this.commandRegistry = config.commandRegistry;
    this.getState = config.getState;
    this.onError = config.onError;
  }

  getToolDefinitions(): ToolDefinition[] {
    return toolDefinitions;
  }

  executeCommand(command: CanvasCommand): CommandResult {
    const result = this.commandRegistry.execute(command);
    if (!result.success && result.error && this.onError) {
      this.onError({
        code: result.error.code,
        message: result.error.message,
        suggestion: result.error.suggestion,
      });
    }
    return result;
  }

  getArchitecture(): ArchitectureSnapshot {
    const state = this.getState();
    const entities = state.entities.allIds
      .map((id) => state.entities.byId[id])
      .filter((e): e is Entity => e != null);
    return {
      entities,
      edges: state.canvas.edges,
      nodePositions: state.canvas.nodePositions,
      nodeSizes: state.canvas.nodeSizes,
    };
  }

  getEntity(id: string): Entity | null {
    const state = this.getState();
    return state.entities.byId[id] ?? null;
  }

  getChildren(parentId: string): Entity[] {
    const state = this.getState();
    const parent = state.entities.byId[parentId];
    if (!parent) return [];
    return parent.children
      .map((id: string) => state.entities.byId[id])
      .filter((e: Entity | undefined): e is Entity => e != null);
  }

  undo(): CommandResult {
    const result = this.commandRegistry.undo();
    if (!result.success && result.error && this.onError) {
      this.onError({
        code: result.error.code,
        message: result.error.message,
      });
    }
    return result;
  }

  redo(): CommandResult {
    const result = this.commandRegistry.redo();
    if (!result.success && result.error && this.onError) {
      this.onError({
        code: result.error.code,
        message: result.error.message,
      });
    }
    return result;
  }
}
