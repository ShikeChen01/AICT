import { useAppStore } from './appStore';
import { useCanvasStore } from './canvasStore';
import type { Entity, EntityId } from '../../shared/types/entities';

export function createEntity(entity: Entity): void {
  useAppStore.getState().createEntity(entity);
}

export function updateEntity(id: EntityId, patch: Partial<Entity>): void {
  useAppStore.getState().updateEntity(id, patch);
}

export function setJobStatus(_jobId: string, _status: string): void {
  // Stub for MVP-0; no jobs yet
}

export function getStateForSave(): { entities: Entity[]; canvas: ReturnType<ReturnType<typeof useCanvasStore.getState>['getLayout']> } {
  const entities = useAppStore.getState().entities;
  const canvas = useCanvasStore.getState().getLayout();
  return { entities, canvas };
}
