import React from 'react';
import { useAppSelector, useAppDispatch } from '../../store/hooks';
import { removeEntity, duplicateEntity } from '../../store/slices/entitiesSlice';
import { removeNodePosition } from '../../store/slices/canvasSlice';
import { setContextMenuWithPosition, setEditPopoverWithPosition, enterScope } from '../../store/slices/uiSlice';
import { openAgentWithScope } from '../../store/slices/agentSlice';
import { selectEntityById } from '../../store/selectors/entitySelectors';
import type { EntityId } from '../../../shared/types/entities';

const menuStyle: React.CSSProperties = {
  position: 'fixed',
  zIndex: 100,
  padding: 'var(--spacing-xs)',
  background: 'var(--color-sidebar-background)',
  border: '1px solid var(--color-widget-border)',
  borderRadius: 'var(--radius-md)',
  boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
  minWidth: 160,
};

const itemStyle: React.CSSProperties = {
  display: 'block',
  width: '100%',
  padding: 'var(--spacing-sm) var(--spacing-md)',
  textAlign: 'left',
  fontSize: 'var(--font-size-sm)',
  background: 'transparent',
  border: 'none',
  color: 'var(--color-foreground)',
  cursor: 'pointer',
  borderRadius: 'var(--radius-sm)',
};

export function ContextMenu() {
  const dispatch = useAppDispatch();
  const entityId = useAppSelector((s) => s.ui.contextMenuEntityId);
  const position = useAppSelector((s) => s.ui.contextMenuPosition);
  const entity = useAppSelector((s) => (entityId ? selectEntityById(s, entityId) : null));

  const close = () => dispatch(setContextMenuWithPosition(null));

  if (!entityId || !position || !entity) return null;

  const handleRename = () => {
    dispatch(setEditPopoverWithPosition({ entityId, x: position.x, y: position.y + 40 }));
    close();
  };

  const handleDuplicate = () => {
    dispatch(duplicateEntity(entityId));
    close();
  };

  const handleDelete = () => {
    dispatch(removeEntity(entityId));
    dispatch(removeNodePosition(entityId));
    close();
  };

  const handleSetAgentScope = () => {
    dispatch(openAgentWithScope({ entityId }));
    close();
  };

  return (
    <>
      <div style={{ position: 'fixed', inset: 0, zIndex: 99 }} onClick={close} aria-hidden />
      <div style={{ ...menuStyle, left: position.x, top: position.y }}>
        <button type="button" style={itemStyle} onClick={handleRename}>
          Rename / Edit
        </button>
        <button type="button" style={itemStyle} onClick={handleDuplicate}>
          Duplicate
        </button>
        {(entity.type === 'bucket' || entity.type === 'module') && (
          <button
            type="button"
            style={itemStyle}
            onClick={() => {
              dispatch(enterScope({ entityId, mode: entity.type === 'bucket' ? 'bucket' : 'module' }));
              close();
            }}
          >
            Focus
          </button>
        )}
        <button type="button" style={itemStyle} onClick={handleSetAgentScope}>
          Set Agent scope
        </button>
        <button type="button" style={{ ...itemStyle, color: 'var(--color-error)' }} onClick={handleDelete}>
          Delete
        </button>
      </div>
    </>
  );
}
