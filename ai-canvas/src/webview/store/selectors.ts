import type { AppState } from "src/webview/store/appStore";

export const selectActiveEntity = (state: AppState) =>
  state.entities.find((entity) => entity.id === state.selectedEntityId) ?? null;

export const selectJobById = (jobId: string) => (state: AppState) =>
  state.jobs.find((job) => job.id === jobId) ?? null;
