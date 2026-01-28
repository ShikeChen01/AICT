import React from "react";
import type { Entity } from "src/shared/types";
import { useAppStore } from "src/webview/store/appStore";

export const AcceptanceCriteriaList: React.FC<{ entity: Entity }> = ({ entity }) => {
  const updateEntity = useAppStore((state) => state.updateEntity);
  const criteria = entity.acceptance_criteria ?? [];

  const toggle = (id: string) => {
    const next = criteria.map((item) => (item.id === id ? { ...item, done: !item.done } : item));
    updateEntity({ ...entity, acceptance_criteria: next });
  };

  return (
    <section>
      <h4 style={{ marginBottom: 8 }}>Acceptance Criteria</h4>
      {criteria.length === 0 ? (
        <p style={{ color: "#94a3b8" }}>No acceptance criteria yet.</p>
      ) : (
        <div style={{ display: "grid", gap: 6 }}>
          {criteria.map((item) => (
            <label key={item.id} style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <input type="checkbox" checked={item.done} onChange={() => toggle(item.id)} />
              <span>{item.text}</span>
            </label>
          ))}
        </div>
      )}
    </section>
  );
};
