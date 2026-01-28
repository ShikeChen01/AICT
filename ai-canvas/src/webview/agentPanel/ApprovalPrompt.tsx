import React from "react";

export const ApprovalPrompt: React.FC = () => (
  <section>
    <h4 style={{ marginBottom: 8 }}>Approval</h4>
    <p style={{ color: "#64748b" }}>Approve or reject the latest patch.</p>
    <div style={{ display: "flex", gap: 8 }}>
      <button type="button" style={{ padding: "8px 12px", borderRadius: 10 }}>
        Reject
      </button>
      <button
        type="button"
        style={{ padding: "8px 12px", borderRadius: 10, background: "#0f172a", color: "#f8fafc" }}
      >
        Approve
      </button>
    </div>
  </section>
);
