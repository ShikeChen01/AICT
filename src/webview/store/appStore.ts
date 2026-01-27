import { create } from "zustand";
import type { Entity, Job } from "../../shared/types";

export interface AppState {
  entities: Entity[];
  jobs: Job[];
  selectedEntityId?: string;
  panel: "inspector" | "agent";
}

export interface AppActions {
  setEntities: (entities: Entity[]) => void;
  selectEntity: (id?: string) => void;
  setJobs: (jobs: Job[]) => void;
  upsertJob: (job: Job) => void;
  setPanel: (panel: "inspector" | "agent") => void;
}

export const useAppStore = create<AppState & AppActions>((set) => ({
  entities: [],
  jobs: [],
  selectedEntityId: undefined,
  panel: "inspector",
  setEntities: (entities) => set({ entities }),
  selectEntity: (id) => set({ selectedEntityId: id }),
  setJobs: (jobs) => set({ jobs }),
  upsertJob: (job) =>
    set((state) => ({
      jobs: state.jobs.some((existing) => existing.id === job.id)
        ? state.jobs.map((existing) => (existing.id === job.id ? job : existing))
        : [...state.jobs, job],
    })),
  setPanel: (panel) => set({ panel }),
}));
