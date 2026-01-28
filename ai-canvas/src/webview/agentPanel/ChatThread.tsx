import React, { useState } from "react";
import { useAppStore } from "src/webview/store/appStore";

export const ChatThread: React.FC = () => {
  const chat = useAppStore((state) => state.chat);
  const addMessage = useAppStore((state) => state.addChatMessage);
  const [input, setInput] = useState("");

  const onSend = () => {
    if (!input.trim()) {
      return;
    }
    addMessage("user", input.trim());
    setInput("");
  };

  return (
    <section>
      <h4 style={{ marginBottom: 8 }}>Conversation</h4>
      <div style={{ display: "grid", gap: 8 }}>
        {chat.length === 0 ? (
          <p style={{ color: "#94a3b8" }}>No messages yet.</p>
        ) : (
          chat.map((msg) => (
            <div
              key={msg.id}
              style={{
                padding: "8px 10px",
                borderRadius: 10,
                background: msg.role === "user" ? "#e2e8f0" : "#fef3c7",
              }}
            >
              <strong style={{ fontSize: 12, textTransform: "uppercase" }}>{msg.role}</strong>
              <div style={{ marginTop: 4 }}>{msg.text}</div>
            </div>
          ))
        )}
      </div>
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <input
          style={{ flex: 1, padding: "8px 10px", borderRadius: 8, border: "1px solid rgba(15,23,42,0.15)" }}
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder="Ask the agent..."
        />
        <button type="button" onClick={onSend}>
          Send
        </button>
      </div>
    </section>
  );
};
