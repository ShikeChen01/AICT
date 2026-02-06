import React, { memo } from 'react';
import type { BlockNodeModel } from './BlockNodeModel';
import type { Block } from '../../../shared/types/entities';

const BLOCK_MIN_WIDTH = 90;
const BLOCK_MIN_HEIGHT = 32;

const chipStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 'var(--spacing-xs)',
  padding: 'var(--spacing-xs) var(--spacing-sm)',
  minWidth: BLOCK_MIN_WIDTH,
  background: 'var(--color-block-bg)',
  border: '1px solid var(--color-block)',
  borderRadius: 'var(--radius-sm)',
  fontSize: 'var(--font-size-sm)',
  color: 'var(--color-foreground)',
  width: '100%',
  height: '100%',
  boxSizing: 'border-box',
};

const extBadgeStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-description)',
  marginLeft: 2,
};

export interface BlockNodeViewProps {
  model: BlockNodeModel;
  onSelect: () => void;
  onDoubleClick: () => void;
  onContextMenu: (e: React.MouseEvent) => void;
  isDropTarget?: boolean;
  onPointerEnter?: () => void;
  onPointerLeave?: () => void;
}

export const BlockNodeView = memo(function BlockNodeView({
  model,
  onSelect,
  onDoubleClick,
  onContextMenu,
  isDropTarget,
  onPointerEnter,
  onPointerLeave,
}: BlockNodeViewProps) {
  const entity = model.data as Block;
  const path = entity.path ?? '';
  const ext = path ? path.split('.').pop() ?? '' : '';
  const fileIcon = ext ? `.${ext}` : '📄';
  return (
    <div
      role="button"
      tabIndex={0}
      style={{
        ...chipStyle,
        position: 'absolute',
        left: model.position.x,
        top: model.position.y,
        width: model.size.width,
        height: model.size.height,
        border: isDropTarget ? '3px dashed var(--color-focus-border)' : chipStyle.border,
        boxShadow: model.selected ? '0 0 0 2px var(--color-focus-border)' : undefined,
        transition: 'border 0.15s ease, box-shadow 0.15s ease',
      }}
      onClick={(e) => { e.stopPropagation(); onSelect(); }}
      onDoubleClick={(e) => { e.stopPropagation(); onDoubleClick(); }}
      onContextMenu={(e) => { e.preventDefault(); onContextMenu(e); }}
      onPointerEnter={onPointerEnter}
      onPointerLeave={onPointerLeave}
    >
      <span style={{ fontSize: '1em' }}>{fileIcon === '📄' ? '📄' : `[${fileIcon}]`}</span>
      <span>{entity.name}</span>
      {ext && <span style={extBadgeStyle}>.{ext}</span>}
    </div>
  );
});


