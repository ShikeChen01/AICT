import { create } from 'zustand';
import type { Entity, EntityId } from '../../shared/types/entities';
import type { LoadWorkspaceStateResult } from '../../shared/types/rpc';

export interface AppState {
  entities: Entity[];
  selectedEntityId: EntityId | null;
  workspaceRoot: string | null;
}

export interface AppActions {
  setEntities: (entities: Entity[]) => void;
  setSelectedEntity: (id: EntityId | null) => void;
  createEntity: (entity: Entity) => void;
  updateEntity: (id: EntityId, patch: Partial<Entity>) => void;
  deleteEntity: (id: EntityId) => void;
  loadState: (state: LoadWorkspaceStateResult) => void;
}

export type AppStore = AppState & AppActions;

export const useAppStore = create<AppStore>((set) => ({
  entities: [],
  selectedEntityId: null,
  workspaceRoot: null,

  setEntities: (entities) => set({ entities }),
  setSelectedEntity: (selectedEntityId) => set({ selectedEntityId }),
  createEntity: (entity) =>
    set((s): Partial<AppStore> => ({ entities: [...s.entities, entity] })),
  updateEntity: (id, patch) =>
    set((s) => ({
      entities: s.entities.map((e) =>
        e.id === id ? ({ ...e, ...patch } as Entity) : e
      )
    })),
  deleteEntity: (id) =>
    set((s) => ({
      entities: s.entities.filter((e) => e.id !== id),
      selectedEntityId: s.selectedEntityId === id ? null : s.selectedEntityId
    })),
  loadState: (state) =>
    set({
      entities: state.entities ?? [],
      // canvas state is applied in canvasStore
    })
}));
