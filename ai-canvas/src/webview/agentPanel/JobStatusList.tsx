import React from "react";
import { useAppStore } from "src/webview/store/appStore";

export const JobStatusList: React.FC = () => {
  const jobs = useAppStore((state) => state.jobs);

  return (
    <section>
      <h4 style={{ marginBottom: 8 }}>Jobs</h4>
      {jobs.length === 0 ? (
        <p style={{ color: "#94a3b8" }}>No jobs running.</p>
      ) : (
        <div style={{ display: "grid", gap: 6 }}>
          {jobs.map((job) => (
            <div
              key={job.id}
              style={{
                padding: "8px 10px",
                borderRadius: 10,
                background: "#f1f5f9",
                border: "1px solid rgba(15,23,42,0.08)",
              }}
            >
              <div style={{ fontWeight: 600 }}>{job.type}</div>
              <div style={{ fontSize: 12, color: "#64748b" }}>{job.status}</div>
            </div>
          ))}
        </div>
      )}
    </section>
  );
};
