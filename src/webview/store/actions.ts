import type { Entity, Job, JobStatus } from "../../shared/types";
import { useAppStore } from "./appStore";

export function createEntity(entity: Entity): void {
  useAppStore.setState((state) => ({ entities: [...state.entities, entity] }));
}

export function updateEntity(entityId: string, updates: Partial<Entity>): void {
  useAppStore.setState((state) => ({
    entities: state.entities.map((entity) => (entity.id === entityId ? { ...entity, ...updates } : entity)),
  }));
}

export function setJobStatus(jobId: string, status: JobStatus, message?: string): void {
  useAppStore.setState((state) => {
    const existing = state.jobs.find((job) => job.id === jobId);
    const updated: Job = {
      id: jobId,
      type: existing?.type ?? "patch",
      status,
      createdAt: existing?.createdAt ?? new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      message: message ?? existing?.message,
    };
    return {
      jobs: existing
        ? state.jobs.map((job) => (job.id === jobId ? updated : job))
        : [...state.jobs, updated],
    };
  });
}
