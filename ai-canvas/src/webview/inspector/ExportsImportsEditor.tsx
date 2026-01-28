import React, { useState } from "react";
import type { Entity } from "src/shared/types";
import { useAppStore } from "src/webview/store/appStore";

const listInputStyle: React.CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 8,
  border: "1px solid rgba(15,23,42,0.15)",
  marginBottom: 6,
};

export const ExportsImportsEditor: React.FC<{ entity: Entity }> = ({ entity }) => {
  const updateEntity = useAppStore((state) => state.updateEntity);
  const [exportsList, setExportsList] = useState(entity.exports ?? []);
  const [importsList, setImportsList] = useState(entity.imports ?? []);

  const updateList = (value: string, index: number, list: string[], setList: (items: string[]) => void) => {
    const next = [...list];
    next[index] = value;
    setList(next);
  };

  const addItem = (list: string[], setList: (items: string[]) => void) => {
    setList([...list, ""]);
  };

  const onSave = () => {
    updateEntity({ ...entity, exports: exportsList.filter(Boolean), imports: importsList.filter(Boolean) });
  };

  return (
    <section>
      <h4 style={{ marginBottom: 8 }}>Exports / Imports</h4>
      <div>
        <strong style={{ fontSize: 12, color: "#475569" }}>Exports</strong>
        {exportsList.map((value, index) => (
          <input
            key={`export-${index}`}
            style={listInputStyle}
            value={value}
            onChange={(event) => updateList(event.target.value, index, exportsList, setExportsList)}
          />
        ))}
        <button type="button" onClick={() => addItem(exportsList, setExportsList)}>
          + Add export
        </button>
      </div>
      <div style={{ marginTop: 10 }}>
        <strong style={{ fontSize: 12, color: "#475569" }}>Imports</strong>
        {importsList.map((value, index) => (
          <input
            key={`import-${index}`}
            style={listInputStyle}
            value={value}
            onChange={(event) => updateList(event.target.value, index, importsList, setImportsList)}
          />
        ))}
        <button type="button" onClick={() => addItem(importsList, setImportsList)}>
          + Add import
        </button>
      </div>
      <button
        type="button"
        onClick={onSave}
        style={{ marginTop: 10, padding: "8px 12px", borderRadius: 10, border: "none", background: "#1d4ed8", color: "#f8fafc" }}
      >
        Save
      </button>
    </section>
  );
};
