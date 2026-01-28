import React, { useState } from "react";
import type { Entity } from "src/shared/types";
import { useAppStore } from "src/webview/store/appStore";

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 8,
  border: "1px solid rgba(15,23,42,0.15)",
};

export const TestStrategyEditor: React.FC<{ entity: Entity }> = ({ entity }) => {
  const updateEntity = useAppStore((state) => state.updateEntity);
  const [blockTest, setBlockTest] = useState(entity.tests?.block_test ?? "");
  const [moduleTest, setModuleTest] = useState(entity.tests?.module_test ?? "");

  const onSave = () => {
    updateEntity({
      ...entity,
      tests: {
        block_test: blockTest || undefined,
        module_test: moduleTest || undefined,
      },
    });
  };

  return (
    <section>
      <h4 style={{ marginBottom: 8 }}>Test Strategy</h4>
      <label style={{ display: "grid", gap: 6 }}>
        <span>Block test command</span>
        <input style={inputStyle} value={blockTest} onChange={(event) => setBlockTest(event.target.value)} />
      </label>
      <label style={{ display: "grid", gap: 6, marginTop: 10 }}>
        <span>Module test command</span>
        <input style={inputStyle} value={moduleTest} onChange={(event) => setModuleTest(event.target.value)} />
      </label>
      <button
        type="button"
        onClick={onSave}
        style={{ marginTop: 10, padding: "8px 12px", borderRadius: 10, border: "none", background: "#0f766e", color: "#f8fafc" }}
      >
        Save
      </button>
    </section>
  );
};
