import React from 'react';
import { type Node, type NodeProps, NodeResizer } from '@xyflow/react';
import { useAppSelector } from '../../store/hooks';
import type { BlockNodeData } from '../../../shared/types/canvas';

const BLOCK_MIN_WIDTH = 90;
const BLOCK_MIN_HEIGHT = 32;
const BLOCK_DEFAULT_WIDTH = 120;
const BLOCK_DEFAULT_HEIGHT = 36;

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

export function BlockNode(props: NodeProps<Node<BlockNodeData, 'block'>>) {
  const { data, selected, id } = props;
  const { entity, isDimmed, fileIcon, testPassed, width, height } = data;
  const potentialParentId = useAppSelector((s) => s.ui.potentialParentId);
  const isDropTarget = potentialParentId === id;
  const path = (entity as { path?: string }).path ?? '';
  const ext = path ? path.split('.').pop() ?? '' : '';
  const w = width ?? BLOCK_DEFAULT_WIDTH;
  const h = height ?? BLOCK_DEFAULT_HEIGHT;

  return (
    <>
      <NodeResizer
        isVisible={selected}
        minWidth={BLOCK_MIN_WIDTH}
        minHeight={BLOCK_MIN_HEIGHT}
        maxWidth={300}
        maxHeight={100}
        color="var(--color-block)"
        handleStyle={{ borderRadius: 2 }}
      />
      <div
        style={{
          ...chipStyle,
          width: w,
          height: h,
          opacity: isDimmed ? 0.5 : 1,
          border: isDropTarget ? '3px dashed var(--color-focus-border)' : chipStyle.border,
          transition: 'border 0.15s ease',
          boxShadow: testPassed ? '0 0 8px rgba(76, 175, 80, 0.5)' : undefined,
        }}
      >
        <span style={{ fontSize: '1em' }}>{fileIcon === '📄' ? '📄' : `[${fileIcon}]`}</span>
        <span>{entity.name}</span>
        {ext && <span style={extBadgeStyle}>.{ext}</span>}
      </div>
    </>
  );
}
