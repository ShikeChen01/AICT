/**
 * Undo/redo stack for canvas commands.
 */

import type { ExecutedCommand, CanvasCommand } from './types';

export class CommandHistory {
  private undoStack: ExecutedCommand[] = [];
  private redoStack: ExecutedCommand[] = [];
  private maxSize: number;

  constructor(maxSize = 100) {
    this.maxSize = maxSize;
  }

  push(executed: ExecutedCommand): void {
    this.undoStack.push(executed);
    this.redoStack = [];

    if (this.undoStack.length > this.maxSize) {
      this.undoStack.shift();
    }
  }

  popUndo(): ExecutedCommand | null {
    const executed = this.undoStack.pop();
    if (executed) {
      this.redoStack.push(executed);
    }
    return executed ?? null;
  }

  popRedo(): ExecutedCommand | null {
    const executed = this.redoStack.pop();
    if (executed) {
      this.undoStack.push(executed);
    }
    return executed ?? null;
  }

  canUndo(): boolean {
    return this.undoStack.length > 0;
  }

  canRedo(): boolean {
    return this.redoStack.length > 0;
  }

  clear(): void {
    this.undoStack = [];
    this.redoStack = [];
  }

  getUndoStackSize(): number {
    return this.undoStack.length;
  }

  getRedoStackSize(): number {
    return this.redoStack.length;
  }
}
