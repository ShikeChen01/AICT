import React from "react";
import { useAppStore } from "src/webview/store/appStore";

export const DiffPreview: React.FC = () => {
  const diff = useAppStore((state) => state.diff);

  return (
    <section>
      <h4 style={{ marginBottom: 8 }}>Diff Preview</h4>
      {diff ? (
        <pre
          style={{
            background: "#0f172a",
            color: "#f8fafc",
            padding: 12,
            borderRadius: 10,
            maxHeight: 180,
            overflow: "auto",
            fontSize: 12,
          }}
        >
          {diff.text}
        </pre>
      ) : (
        <p style={{ color: "#94a3b8" }}>No diff loaded.</p>
      )}
    </section>
  );
};
