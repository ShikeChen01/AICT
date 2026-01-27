import type { Job } from "../../shared/types";

export interface JobStatusListProps {
  jobs: Job[];
}

export function JobStatusList({ jobs }: JobStatusListProps) {
  if (jobs.length === 0) {
    return <div>No active jobs.</div>;
  }

  return (
    <ul style={{ margin: 0, paddingLeft: 16, display: "grid", gap: 6 }}>
      {jobs.map((job) => (
        <li key={job.id}>
          <strong>{job.type}</strong> ? {job.status} {job.message ? `(${job.message})` : ""}
        </li>
      ))}
    </ul>
  );
}
