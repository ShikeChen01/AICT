import type { AppState } from "./appStore";

export function selectActiveEntity(state: AppState) {
  if (!state.selectedEntityId) {
    return undefined;
  }
  return state.entities.find((entity) => entity.id === state.selectedEntityId);
}

export function selectJobById(state: AppState, jobId: string) {
  return state.jobs.find((job) => job.id === jobId);
}
