import React, { useState, useEffect } from 'react';
import { useAppSelector, useAppDispatch } from '../../store/hooks';
import { updateEntity } from '../../store/slices/entitiesSlice';
import { setEditPopover } from '../../store/slices/uiSlice';
import { selectEntityById } from '../../store/selectors/entitySelectors';
import type { Entity, Bucket, Module, Block } from '../../../shared/types/entities';

const popoverStyle: React.CSSProperties = {
  position: 'fixed',
  zIndex: 100,
  padding: 'var(--spacing-md)',
  background: 'var(--color-sidebar-background)',
  border: '1px solid var(--color-widget-border)',
  borderRadius: 'var(--radius-md)',
  boxShadow: '0 4px 12px rgba(0,0,0,0.2)',
  minWidth: 220,
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: 'var(--spacing-sm) var(--spacing-md)',
  marginBottom: 'var(--spacing-sm)',
  fontSize: 'var(--font-size-md)',
  background: 'var(--color-input-background)',
  border: '1px solid var(--color-input-border)',
  borderRadius: 'var(--radius-md)',
  color: 'var(--color-foreground)',
  boxSizing: 'border-box',
};

const btnStyle: React.CSSProperties = {
  padding: 'var(--spacing-sm) var(--spacing-md)',
  fontSize: 'var(--font-size-sm)',
  cursor: 'pointer',
  border: 'none',
  borderRadius: 'var(--radius-md)',
  marginRight: 'var(--spacing-sm)',
};

export function EditPopover({
  entityId,
  x,
  y,
  onClose,
}: {
  entityId: string;
  x: number;
  y: number;
  onClose: () => void;
}) {
  const dispatch = useAppDispatch();
  const entity = useAppSelector((s) => selectEntityById(s, entityId));
  const [name, setName] = useState('');
  const [purpose, setPurpose] = useState('');
  const [path, setPath] = useState('');

  useEffect(() => {
    if (entity) {
      setName(entity.name);
      setPurpose(entity.purpose || '');
      setPath((entity as Block).path ?? '');
    }
  }, [entity]);

  if (!entity) return null;

  const handleSave = () => {
    const changes: Partial<Entity> = { name, purpose };
    if (entity.type === 'block') (changes as Partial<Block>).path = path;
    dispatch(updateEntity({ id: entityId, changes }));
    dispatch(setEditPopover(null));
  };

  return (
    <>
      <div style={{ position: 'fixed', inset: 0, zIndex: 99 }} onClick={onClose} aria-hidden />
      <div style={{ ...popoverStyle, left: x, top: y }}>
        <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 8 }}>
          Edit {entity.type}
        </div>
        <label style={{ display: 'block', fontSize: 'var(--font-size-xs)', marginBottom: 4 }}>Name</label>
        <input
          style={inputStyle}
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <label style={{ display: 'block', fontSize: 'var(--font-size-xs)', marginBottom: 4 }}>Purpose</label>
        <input
          style={inputStyle}
          value={purpose}
          onChange={(e) => setPurpose(e.target.value)}
        />
        {entity.type === 'block' && (
          <>
            <label style={{ display: 'block', fontSize: 'var(--font-size-xs)', marginBottom: 4 }}>Path</label>
            <input
              style={inputStyle}
              value={path}
              onChange={(e) => setPath(e.target.value)}
            />
          </>
        )}
        <div style={{ marginTop: 'var(--spacing-md)' }}>
          <button
            type="button"
            style={{ ...btnStyle, background: 'var(--color-button-background)', color: 'var(--color-button-foreground)' }}
            onClick={handleSave}
          >
            Save
          </button>
          <button
            type="button"
            style={{ ...btnStyle, background: 'transparent', border: '1px solid var(--color-widget-border)' }}
            onClick={onClose}
          >
            Cancel
          </button>
        </div>
      </div>
    </>
  );
}
