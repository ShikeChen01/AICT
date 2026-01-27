export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type JobType = "plan" | "patch" | "test" | "review" | "index";

export interface Job {
  id: string;
  type: JobType;
  status: JobStatus;
  createdAt: string;
  updatedAt?: string;
  message?: string;
}
