import React from "react";
import { ChatThread } from "src/webview/agentPanel/ChatThread";
import { JobStatusList } from "src/webview/agentPanel/JobStatusList";
import { DiffPreview } from "src/webview/agentPanel/DiffPreview";
import { ApprovalPrompt } from "src/webview/agentPanel/ApprovalPrompt";

export const AgentPanel: React.FC = () => {
  return (
    <div className="panel-scroll" style={{ padding: 20, display: "grid", gap: 16 }}>
      <div>
        <h3 style={{ marginTop: 0 }}>Agent</h3>
        <p style={{ color: "#64748b", marginBottom: 0 }}>
          Track jobs, review diffs, and approve patches.
        </p>
      </div>
      <ChatThread />
      <JobStatusList />
      <DiffPreview />
      <ApprovalPrompt />
    </div>
  );
};
