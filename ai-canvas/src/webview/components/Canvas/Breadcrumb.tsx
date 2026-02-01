import React from 'react';
import { useAppSelector, useAppDispatch } from '../../store/hooks';
import { selectBreadcrumbLevels } from '../../store/selectors/scopeSelectors';
import { setScope, setFocusMode, exitScope } from '../../store/slices/uiSlice';
import type { EntityId } from '../../../shared/types/entities';
import type { Entity } from '../../../shared/types/entities';

const chipStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: 'var(--spacing-xs) var(--spacing-sm)',
  fontSize: 'var(--font-size-sm)',
  color: 'var(--color-description)',
  background: 'var(--color-input-background)',
  border: '1px solid var(--color-widget-border)',
  borderRadius: 'var(--radius-sm)',
  cursor: 'pointer',
  marginRight: 'var(--spacing-xs)',
};

export function Breadcrumb() {
  const dispatch = useAppDispatch();
  const levels = useAppSelector(selectBreadcrumbLevels);
  const entities = useAppSelector((s) => s.entities.byId);

  const handleClick = (id: EntityId | null, index: number) => {
    if (index === 0 || id === null) {
      dispatch(exitScope());
      return;
    }
    const entity = entities[id] as Entity | undefined;
    if (!entity) return;
    dispatch(setScope(id));
    dispatch(setFocusMode(entity.type === 'bucket' ? 'bucket' : entity.type === 'module' ? 'module' : 'workspace'));
  };

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        flexWrap: 'wrap',
        gap: 'var(--spacing-xs)',
      }}
    >
      {levels.map((level, index) => (
        <button
          key={level.id ?? 'workspace'}
          type="button"
          style={chipStyle}
          onClick={() => handleClick(level.id, index)}
        >
          {level.name}
        </button>
      ))}
    </div>
  );
}
