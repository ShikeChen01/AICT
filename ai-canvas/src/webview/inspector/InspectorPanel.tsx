import React from "react";
import { useAppStore } from "src/webview/store/appStore";
import { selectActiveEntity } from "src/webview/store/selectors";
import { EntityForm } from "src/webview/inspector/EntityForm";
import { ExportsImportsEditor } from "src/webview/inspector/ExportsImportsEditor";
import { AcceptanceCriteriaList } from "src/webview/inspector/AcceptanceCriteriaList";
import { TestStrategyEditor } from "src/webview/inspector/TestStrategyEditor";

export const InspectorPanel: React.FC = () => {
  const entity = useAppStore(selectActiveEntity);

  if (!entity) {
    return (
      <div style={{ padding: 20 }}>
        <h3 style={{ marginTop: 0 }}>Inspector</h3>
        <p style={{ color: "#64748b" }}>Select a node to edit its metadata.</p>
      </div>
    );
  }

  return (
    <div className="panel-scroll" style={{ padding: 20, display: "grid", gap: 16 }}>
      <div>
        <h3 style={{ marginTop: 0 }}>Inspector</h3>
        <p style={{ color: "#64748b", marginBottom: 0 }}>Edit entity metadata and requirements.</p>
      </div>
      <EntityForm entity={entity} />
      <ExportsImportsEditor entity={entity} />
      <AcceptanceCriteriaList entity={entity} />
      <TestStrategyEditor entity={entity} />
    </div>
  );
};
