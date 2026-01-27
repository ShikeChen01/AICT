import { useState } from "react";

export interface AcceptanceCriteriaListProps {
  items: string[];
  onChange: (items: string[]) => void;
}

export function AcceptanceCriteriaList({ items, onChange }: AcceptanceCriteriaListProps) {
  const [draft, setDraft] = useState("");

  const addItem = () => {
    const trimmed = draft.trim();
    if (!trimmed) {
      return;
    }
    onChange([...items, trimmed]);
    setDraft("");
  };

  return (
    <section style={{ display: "grid", gap: 8 }}>
      <div>Acceptance Criteria</div>
      <ul style={{ margin: 0, paddingLeft: 16 }}>
        {items.map((item, index) => (
          <li key={`${item}-${index}`}>{item}</li>
        ))}
      </ul>
      <div style={{ display: "flex", gap: 8 }}>
        <input value={draft} onChange={(event) => setDraft(event.target.value)} style={{ flex: 1 }} />
        <button type="button" onClick={addItem}>
          Add
        </button>
      </div>
    </section>
  );
}
