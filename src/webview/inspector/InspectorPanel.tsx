import { useEffect, useState } from "react";
import { useAppStore } from "../store/appStore";
import { selectActiveEntity } from "../store/selectors";
import { updateEntity } from "../store/actions";
import { EntityForm } from "./EntityForm";
import { ExportsImportsEditor } from "./ExportsImportsEditor";
import { AcceptanceCriteriaList } from "./AcceptanceCriteriaList";
import { TestStrategyEditor } from "./TestStrategyEditor";

export function InspectorPanel() {
  const entity = useAppStore(selectActiveEntity);
  const [criteria, setCriteria] = useState<string[]>([]);

  useEffect(() => {
    setCriteria([]);
  }, [entity?.id]);

  if (!entity) {
    return <div style={{ padding: 16 }}>Select an entity to edit its details.</div>;
  }

  const handleChange = (updates: Partial<typeof entity>) => {
    updateEntity(entity.id, updates);
  };

  return (
    <div style={{ display: "grid", gap: 16, padding: 16 }}>
      <EntityForm entity={entity} onChange={handleChange} />
      <ExportsImportsEditor entity={entity} onChange={handleChange} />
      <AcceptanceCriteriaList items={criteria} onChange={setCriteria} />
      <TestStrategyEditor entity={entity} onChange={handleChange} />
    </div>
  );
}
