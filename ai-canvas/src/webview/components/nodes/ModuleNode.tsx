import React, { memo } from 'react';
import type { ModuleNodeModel } from './ModuleNodeModel';
import type { Module } from '../../../shared/types/entities';

const MODULE_MIN_WIDTH = 160;
const MODULE_MIN_HEIGHT = 56;

const cardStyle: React.CSSProperties = {
  minWidth: MODULE_MIN_WIDTH,
  minHeight: MODULE_MIN_HEIGHT,
  background: 'var(--color-module-bg)',
  border: '1px solid var(--color-module)',
  borderRadius: 'var(--radius-md)',
  overflow: 'hidden',
  width: '100%',
  height: '100%',
  boxSizing: 'border-box',
};

const headerStyle: React.CSSProperties = {
  padding: 'var(--spacing-sm) var(--spacing-md)',
  fontSize: 'var(--font-size-md)',
  fontWeight: 600,
  color: 'var(--color-foreground)',
  borderBottom: '1px solid var(--color-widget-border)',
};

const summaryStyle: React.CSSProperties = {
  padding: 'var(--spacing-xs) var(--spacing-md)',
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-description)',
  lineHeight: 1.3,
};

export interface ModuleNodeViewProps {
  model: ModuleNodeModel;
  onSelect: () => void;
  onDoubleClick: () => void;
  onContextMenu: (e: React.MouseEvent) => void;
  isDropTarget?: boolean;
}

export const ModuleNodeView = memo(function ModuleNodeView({
  model,
  onSelect,
  onDoubleClick,
  onContextMenu,
  isDropTarget,
}: ModuleNodeViewProps) {
  const entity = model.data as Module;
  return (
    <div
      role="button"
      tabIndex={0}
      style={{
        position: 'absolute',
        left: model.position.x,
        top: model.position.y,
        width: model.size.width,
        height: model.size.height,
        ...cardStyle,
        border: isDropTarget ? '3px dashed var(--color-focus-border)' : cardStyle.border,
        boxShadow: model.selected ? '0 0 0 2px var(--color-focus-border)' : undefined,
        transition: 'border 0.15s ease, box-shadow 0.15s ease',
      }}
      onClick={(e) => { e.stopPropagation(); onSelect(); }}
      onDoubleClick={(e) => { e.stopPropagation(); onDoubleClick(); }}
      onContextMenu={(e) => { e.preventDefault(); onContextMenu(e); }}
    >
      <div style={headerStyle}>{entity.name}</div>
      <div style={summaryStyle}>
        {entity.purpose ? `${entity.purpose.slice(0, 60)}${entity.purpose.length > 60 ? '…' : ''}` : ''}
      </div>
    </div>
  );
});
