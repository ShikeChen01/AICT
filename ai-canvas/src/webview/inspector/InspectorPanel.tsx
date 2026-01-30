import React from 'react';
import { useAppStore } from '../store/appStore';
import { EntityForm } from './EntityForm';

const panelStyle: React.CSSProperties = {
  width: '280px',
  minWidth: '280px',
  borderLeft: '1px solid #ccc',
  background: '#fafafa',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden'
};
const titleStyle: React.CSSProperties = {
  padding: '12px',
  fontSize: '13px',
  fontWeight: 600,
  borderBottom: '1px solid #eee'
};
const emptyStyle: React.CSSProperties = {
  padding: '24px',
  fontSize: '12px',
  color: '#888',
  textAlign: 'center'
};

export function InspectorPanel() {
  const entities = useAppStore((s) => s.entities);
  const selectedEntityId = useAppStore((s) => s.selectedEntityId);
  const entity = selectedEntityId
    ? entities.find((e) => e.id === selectedEntityId) ?? null
    : null;

  return (
    <div style={panelStyle}>
      <div style={titleStyle}>Inspector</div>
      <div style={{ flex: 1, overflow: 'auto' }}>
        {!entity ? (
          <div style={emptyStyle}>Select an entity on the canvas</div>
        ) : (
          <EntityForm entity={entity} />
        )}
      </div>
    </div>
  );
}
