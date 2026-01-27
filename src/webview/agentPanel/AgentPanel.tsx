import { useMemo, useState } from "react";
import { useAppStore } from "../store/appStore";
import { ChatThread, type ChatMessage } from "./ChatThread";
import { JobStatusList } from "./JobStatusList";
import { DiffPreview } from "./DiffPreview";
import { ApprovalPrompt } from "./ApprovalPrompt";

export function AgentPanel() {
  const jobs = useAppStore((state) => state.jobs);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [diff, setDiff] = useState("");

  const approveMessage = useMemo(() => (diff ? "Approve patch?" : "No patch pending"), [diff]);

  const handleSend = (text: string) => {
    setMessages((prev) => [...prev, { id: `${Date.now()}`, role: "user", text }]);
  };

  return (
    <div style={{ display: "grid", gap: 16, padding: 16 }}>
      <ChatThread messages={messages} onSend={handleSend} />
      <section style={{ display: "grid", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Jobs</h3>
        <JobStatusList jobs={jobs} />
      </section>
      <section style={{ display: "grid", gap: 8 }}>
        <h3 style={{ margin: 0 }}>Diff Preview</h3>
        <DiffPreview diff={diff} />
      </section>
      <ApprovalPrompt
        message={approveMessage}
        onApprove={() => setDiff("")}
        onReject={() => setDiff("")}
      />
    </div>
  );
}
