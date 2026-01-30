import { useAppStore } from './appStore';
import type { Entity, EntityId } from '../../shared/types/entities';

export function selectActiveEntity(): Entity | null {
  const { entities, selectedEntityId } = useAppStore.getState();
  if (!selectedEntityId) return null;
  return entities.find((e) => e.id === selectedEntityId) ?? null;
}

export function selectEntityById(id: EntityId): Entity | null {
  const { entities } = useAppStore.getState();
  return entities.find((e) => e.id === id) ?? null;
}
