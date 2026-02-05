/**
 * RPC persistence wrapper for canvas state. Debounced save, load returns snapshot.
 */

import type { RpcClient } from '../../../rpcClient/rpcClient';
import type { CanvasLayout } from '../../../../shared/types/rpc';
import type { Entity } from '../../../../shared/types/entities';

export interface CanvasStateSnapshot {
  entities: Entity[];
  canvas: CanvasLayout;
}

export class CanvasStorage {
  private rpcClient: RpcClient;
  private saveTimeout: ReturnType<typeof setTimeout> | null = null;
  private readonly debounceMs: number;

  constructor(rpcClient: RpcClient, debounceMs = 800) {
    this.rpcClient = rpcClient;
    this.debounceMs = debounceMs;
  }

  async load(): Promise<CanvasStateSnapshot> {
    const result = await this.rpcClient.loadWorkspaceState();
    return {
      entities: result.entities ?? [],
      canvas:
        result.canvas ?? {
          nodes: [],
          edges: [],
          viewport: { x: 0, y: 0, zoom: 1 },
        },
    };
  }

  save(snapshot: CanvasStateSnapshot): void {
    if (this.saveTimeout) clearTimeout(this.saveTimeout);
    this.saveTimeout = setTimeout(() => {
      this.rpcClient.saveWorkspaceState({
        entities: snapshot.entities,
        canvas: snapshot.canvas,
      });
    }, this.debounceMs);
  }

  saveImmediate(snapshot: CanvasStateSnapshot): Promise<{ ok: boolean }> {
    if (this.saveTimeout) clearTimeout(this.saveTimeout);
    return this.rpcClient.saveWorkspaceState({
      entities: snapshot.entities,
      canvas: snapshot.canvas,
    });
  }

  dispose(): void {
    if (this.saveTimeout) clearTimeout(this.saveTimeout);
  }
}
