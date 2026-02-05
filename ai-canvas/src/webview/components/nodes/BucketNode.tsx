import React, { memo } from 'react';
import type { Bucket } from '../../../shared/types/entities';
import type { BucketNodeModel } from './BucketNodeModel';

const BUCKET_MIN_WIDTH = 200;
const BUCKET_MIN_HEIGHT = 120;

const frameStyle: React.CSSProperties = {
  minWidth: BUCKET_MIN_WIDTH,
  minHeight: BUCKET_MIN_HEIGHT,
  background: 'var(--color-bucket-bg)',
  border: '2px solid var(--color-bucket)',
  borderRadius: 'var(--radius-lg)',
  overflow: 'hidden',
  width: '100%',
  height: '100%',
  boxSizing: 'border-box',
};

const headerStyle: React.CSSProperties = {
  padding: 'var(--spacing-sm) var(--spacing-md)',
  background: 'var(--color-bucket)',
  color: 'white',
  fontSize: 'var(--font-size-md)',
  fontWeight: 600,
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'space-between',
  gap: 'var(--spacing-sm)',
};

const statusStripStyle: React.CSSProperties = {
  padding: 'var(--spacing-xs) var(--spacing-md)',
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-description)',
  background: 'rgba(0,0,0,0.05)',
  borderBottom: '1px solid var(--color-widget-border)',
};

const bodyStyle: React.CSSProperties = {
  padding: 'var(--spacing-sm) var(--spacing-md)',
  fontSize: 'var(--font-size-sm)',
  color: 'var(--color-foreground)',
};

export interface BucketNodeViewProps {
  model: BucketNodeModel;
  onSelect: () => void;
  onDoubleClick: () => void;
  onContextMenu: (e: React.MouseEvent) => void;
  isDropTarget?: boolean;
}

export const BucketNodeView = memo(function BucketNodeView({
  model,
  onSelect,
  onDoubleClick,
  onContextMenu,
  isDropTarget,
}: BucketNodeViewProps) {
  const entity = model.data as Bucket;
  const modulesCount = Array.isArray(entity.children) ? entity.children.length : 0;
  const blocksCount = 0;
  const total = modulesCount || 1;
  const done = 0;

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
        ...frameStyle,
        border: isDropTarget ? '3px dashed var(--color-focus-border)' : frameStyle.border,
        boxShadow: model.selected ? '0 0 0 2px var(--color-focus-border)' : undefined,
        transition: 'border 0.15s ease, box-shadow 0.15s ease',
      }}
      onClick={(e) => { e.stopPropagation(); onSelect(); }}
      onDoubleClick={(e) => { e.stopPropagation(); onDoubleClick(); }}
      onContextMenu={(e) => { e.preventDefault(); onContextMenu(e); }}
    >
      <div style={headerStyle}>
        <span>{entity.name}</span>
        <span style={{ fontSize: 'var(--font-size-xs)', opacity: 0.9 }}>Bucket</span>
      </div>
      <div style={statusStripStyle}>
        {done}/{total} · {modulesCount} modules · {blocksCount} blocks
      </div>
      <div style={bodyStyle}>
        {entity.purpose || 'No description'}
      </div>
    </div>
  );
});
