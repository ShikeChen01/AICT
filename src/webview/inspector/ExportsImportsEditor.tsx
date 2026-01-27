import type { Entity } from "../../shared/types";

export interface ExportsImportsEditorProps {
  entity: Entity;
  onChange: (updates: Partial<Entity>) => void;
}

function listToText(items: string[]): string {
  return items.join("\n");
}

function textToList(text: string): string[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

export function ExportsImportsEditor({ entity, onChange }: ExportsImportsEditorProps) {
  return (
    <section style={{ display: "grid", gap: 8 }}>
      <label>
        <div>Exports</div>
        <textarea
          value={listToText(entity.exports)}
          onChange={(event) => onChange({ exports: textToList(event.target.value) })}
          rows={3}
          style={{ width: "100%" }}
        />
      </label>
      <label>
        <div>Imports</div>
        <textarea
          value={listToText(entity.imports)}
          onChange={(event) => onChange({ imports: textToList(event.target.value) })}
          rows={3}
          style={{ width: "100%" }}
        />
      </label>
    </section>
  );
}
