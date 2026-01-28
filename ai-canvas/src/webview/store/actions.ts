import type { Entity, JobStatus } from "src/shared/types";
import type { AppActions } from "src/webview/store/appStore";

export const createEntity = (actions: AppActions, entity: Entity) => {
  actions.setEntities([entity]);
};

export const updateEntity = (actions: AppActions, entity: Entity) => {
  actions.updateEntity(entity);
};

export const setJobStatus = (actions: AppActions, jobId: string, status: JobStatus) => {
  actions.upsertJob({
    id: jobId,
    type: "work",
    status,
    created_at: new Date().toISOString(),
  });
};
