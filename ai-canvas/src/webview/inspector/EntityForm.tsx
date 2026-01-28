import React, { useState } from "react";
import type { Entity } from "src/shared/types";
import { useAppStore } from "src/webview/store/appStore";

const inputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 8,
  border: "1px solid rgba(15,23,42,0.15)",
};

type SizeHint = NonNullable<Entity["size_hint"]>;

export const EntityForm: React.FC<{ entity: Entity }> = ({ entity }) => {
  const updateEntity = useAppStore((state) => state.updateEntity);
  const [name, setName] = useState(entity.name);
  const [purpose, setPurpose] = useState(entity.purpose);
  const [sizeHint, setSizeHint] = useState<SizeHint>(entity.size_hint ?? "m");

  const onSave = () => {
    updateEntity({ ...entity, name, purpose, size_hint: sizeHint });
  };

  return (
    <section>
      <h4 style={{ marginBottom: 8 }}>Entity</h4>
      <label style={{ display: "grid", gap: 6 }}>
        <span>Name</span>
        <input style={inputStyle} value={name} onChange={(event) => setName(event.target.value)} />
      </label>
      <label style={{ display: "grid", gap: 6, marginTop: 10 }}>
        <span>Purpose</span>
        <textarea
          style={{ ...inputStyle, minHeight: 80 }}
          value={purpose}
          onChange={(event) => setPurpose(event.target.value)}
        />
      </label>
      <label style={{ display: "grid", gap: 6, marginTop: 10 }}>
        <span>Size hint</span>
        <select
          style={inputStyle}
          value={sizeHint}
          onChange={(event) => setSizeHint(event.target.value as SizeHint)}
        >
          <option value="xs">XS</option>
          <option value="s">S</option>
          <option value="m">M</option>
          <option value="l">L</option>
          <option value="xl">XL</option>
        </select>
      </label>
      <button
        type="button"
        onClick={onSave}
        style={{ marginTop: 12, padding: "8px 12px", borderRadius: 10, border: "none", background: "#0f172a", color: "#f8fafc" }}
      >
        Save
      </button>
    </section>
  );
};
