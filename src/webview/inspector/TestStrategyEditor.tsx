import type { Entity } from "../../shared/types";

export interface TestStrategyEditorProps {
  entity: Entity;
  onChange: (updates: Partial<Entity>) => void;
}

export function TestStrategyEditor({ entity, onChange }: TestStrategyEditorProps) {
  const blockTest = entity.tests?.block_test ?? "";
  const moduleTest = entity.tests?.module_test ?? "";

  return (
    <section style={{ display: "grid", gap: 8 }}>
      <label>
        <div>Block Test Command</div>
        <input
          value={blockTest}
          onChange={(event) => onChange({ tests: { ...entity.tests, block_test: event.target.value } })}
          style={{ width: "100%" }}
        />
      </label>
      <label>
        <div>Module Test Command</div>
        <input
          value={moduleTest}
          onChange={(event) => onChange({ tests: { ...entity.tests, module_test: event.target.value } })}
          style={{ width: "100%" }}
        />
      </label>
    </section>
  );
}
