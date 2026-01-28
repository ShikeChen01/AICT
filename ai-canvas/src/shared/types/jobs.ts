type JobStatus = "queued" | "running" | "succeeded" | "failed" | "canceled";
type JobType = "work" | "tests" | "patch" | "index" | "export" | "review";

type Job = {
  id: string;
  type: JobType;
  status: JobStatus;
  created_at: string;
  started_at?: string;
  finished_at?: string;
  progress?: number;
  message?: string;
  error?: string;
};

export type { Job, JobStatus, JobType };
