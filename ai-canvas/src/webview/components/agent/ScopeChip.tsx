import React from 'react';
import { useAppSelector } from '../../store/hooks';
import { selectBreadcrumbPath } from '../../store/selectors/scopeSelectors';
import { selectEntityById } from '../../store/selectors/entitySelectors';

const chipStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  padding: 'var(--spacing-xs) var(--spacing-sm)',
  fontSize: 'var(--font-size-xs)',
  background: 'var(--color-input-background)',
  border: '1px solid var(--color-widget-border)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--color-description)',
};

export function ScopeChip() {
  const breadcrumb = useAppSelector(selectBreadcrumbPath);
  const scopeEntity = useAppSelector((s) => {
    const id = s.agent.scopeEntityId;
    return id ? selectEntityById(s, id) : null;
  });

  const label = scopeEntity
    ? `${scopeEntity.type}: ${scopeEntity.name}`
    : 'Workspace';

  return (
    <span style={chipStyle} title={breadcrumb.join(' / ')}>
      {label}
    </span>
  );
}
