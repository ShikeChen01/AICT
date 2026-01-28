import { create } from "zustand";
import type { Entity, Job, Plan, UnifiedDiff } from "src/shared/types";

export type WorkspaceEdge = {
  id: string;
  type: "contains" | "depends_on" | "implements" | "verifies";
  from: string;
  to: string;
};

export type JobLog = {
  job_id: string;
  stream: "stdout" | "stderr";
  text: string;
};

export type AppState = {
  entities: Entity[];
  edges: WorkspaceEdge[];
  jobs: Job[];
  jobLogs: JobLog[];
  plan?: Plan;
  diff?: UnifiedDiff;
  selectedEntityId: string | null;
  chat: Array<{ id: string; role: "user" | "assistant"; text: string }>;
};

export type AppActions = {
  setEntities: (entities: Entity[]) => void;
  updateEntity: (entity: Entity) => void;
  setEdges: (edges: WorkspaceEdge[]) => void;
  setJobs: (jobs: Job[]) => void;
  upsertJob: (job: Job) => void;
  addJobLog: (log: JobLog) => void;
  setPlan: (plan?: Plan) => void;
  setDiff: (diff?: UnifiedDiff) => void;
  setSelectedEntityId: (entityId: string | null) => void;
  addChatMessage: (role: "user" | "assistant", text: string) => void;
};

export const useAppStore = create<AppState & AppActions>((set, get) => ({
  entities: [],
  edges: [],
  jobs: [],
  jobLogs: [],
  selectedEntityId: null,
  chat: [],
  setEntities: (entities) => set({ entities }),
  updateEntity: (entity) =>
    set((state) => ({
      entities: state.entities.map((item) => (item.id === entity.id ? entity : item)),
    })),
  setEdges: (edges) => set({ edges }),
  setJobs: (jobs) => set({ jobs }),
  upsertJob: (job) =>
    set((state) => {
      const existing = state.jobs.find((item) => item.id === job.id);
      if (!existing) {
        return { jobs: [...state.jobs, job] };
      }
      return { jobs: state.jobs.map((item) => (item.id === job.id ? job : item)) };
    }),
  addJobLog: (log) => set((state) => ({ jobLogs: [...state.jobLogs, log] })),
  setPlan: (plan) => set({ plan }),
  setDiff: (diff) => set({ diff }),
  setSelectedEntityId: (entityId) => set({ selectedEntityId: entityId }),
  addChatMessage: (role, text) =>
    set((state) => ({
      chat: [...state.chat, { id: `${Date.now()}-${state.chat.length}`, role, text }],
    })),
}));
