import { useState } from "react";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system";
  text: string;
}

export interface ChatThreadProps {
  messages: ChatMessage[];
  onSend: (text: string) => void;
}

export function ChatThread({ messages, onSend }: ChatThreadProps) {
  const [draft, setDraft] = useState("");

  const submit = () => {
    const trimmed = draft.trim();
    if (!trimmed) {
      return;
    }
    onSend(trimmed);
    setDraft("");
  };

  return (
    <section style={{ display: "grid", gap: 12 }}>
      <div style={{ maxHeight: 240, overflowY: "auto", display: "grid", gap: 8 }}>
        {messages.map((message) => (
          <div key={message.id} style={{ padding: 8, borderRadius: 8, background: "#f4f4f4" }}>
            <strong>{message.role}</strong>
            <div>{message.text}</div>
          </div>
        ))}
      </div>
      <div style={{ display: "flex", gap: 8 }}>
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Ask the agent?"
          style={{ flex: 1 }}
        />
        <button type="button" onClick={submit}>
          Send
        </button>
      </div>
    </section>
  );
}
