import React, { useState } from 'react';
import { useAppSelector, useAppDispatch } from '../../store/hooks';
import { setFilters } from '../../store/slices/uiSlice';
import type { EntityStatus } from '../../../shared/types/entities';

const panelStyle: React.CSSProperties = {
  position: 'absolute',
  top: '100%',
  left: 0,
  marginTop: 4,
  padding: 'var(--spacing-sm)',
  background: 'var(--color-sidebar-background)',
  border: '1px solid var(--color-widget-border)',
  borderRadius: 'var(--radius-md)',
  boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
  zIndex: 100,
  minWidth: 140,
};

const statuses: EntityStatus[] = ['todo', 'doing', 'review', 'done'];

export function FilterPanel() {
  const dispatch = useAppDispatch();
  const filters = useAppSelector((s) => s.ui.filters);
  const [open, setOpen] = useState(false);

  const toggleStatus = (status: EntityStatus) => {
    const next = filters.status.includes(status)
      ? filters.status.filter((s) => s !== status)
      : [...filters.status, status];
    dispatch(setFilters({ status: next }));
  };

  return (
    <div style={{ position: 'relative' }}>
      <button
        type="button"
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: 48,
          height: 48,
          padding: 0,
          fontSize: 'var(--font-size-lg)',
          cursor: 'pointer',
          background: open ? 'var(--color-button-hover)' : 'var(--color-button-background)',
          color: 'var(--color-button-foreground)',
          border: 'none',
          borderRadius: 'var(--radius-md)',
        }}
        title="Filter"
        onClick={() => setOpen(!open)}
      >
        ⛃
      </button>
      {open && (
        <>
          <div
            style={{ position: 'fixed', inset: 0, zIndex: 99 }}
            onClick={() => setOpen(false)}
            aria-hidden
          />
          <div style={panelStyle}>
            <div style={{ fontSize: 'var(--font-size-sm)', fontWeight: 600, marginBottom: 8 }}>
              Filter by status
            </div>
            {statuses.map((s) => (
              <label
                key={s}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  fontSize: 'var(--font-size-sm)',
                  cursor: 'pointer',
                  marginBottom: 4,
                }}
              >
                <input
                  type="checkbox"
                  checked={filters.status.includes(s)}
                  onChange={() => toggleStatus(s)}
                />
                {s}
              </label>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
