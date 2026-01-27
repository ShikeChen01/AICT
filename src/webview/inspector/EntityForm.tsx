import { useMemo } from "react";
import type { Entity } from "../../shared/types";

export interface EntityFormProps {
  entity: Entity;
  onChange: (updates: Partial<Entity>) => void;
}

export function EntityForm({ entity, onChange }: EntityFormProps) {
  const sizeOptions = useMemo(() => ["xs", "s", "m", "l", "xl"], []);

  return (
    <section style={{ display: "grid", gap: 8 }}>
      <label>
        <div>Name</div>
        <input
          value={entity.name}
          onChange={(event) => onChange({ name: event.target.value })}
          style={{ width: "100%" }}
        />
      </label>
      <label>
        <div>Purpose</div>
        <textarea
          value={entity.purpose}
          onChange={(event) => onChange({ purpose: event.target.value })}
          rows={3}
          style={{ width: "100%" }}
        />
      </label>
      <label>
        <div>Size Hint</div>
        <select
          value={entity.size_hint ?? "m"}
          onChange={(event) => onChange({ size_hint: event.target.value as Entity["size_hint"] })}
        >
          {sizeOptions.map((option) => (
            <option key={option} value={option}>
              {option.toUpperCase()}
            </option>
          ))}
        </select>
      </label>
    </section>
  );
}
