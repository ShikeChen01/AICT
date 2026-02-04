import React from 'react';
import { type Node, type NodeProps, NodeResizer } from '@xyflow/react';
import { useAppSelector } from '../../store/hooks';
import type { BucketNodeData } from '../../../shared/types/canvas';

const BUCKET_MIN_WIDTH = 200;
const BUCKET_MIN_HEIGHT = 120;
const BUCKET_DEFAULT_WIDTH = 280;
const BUCKET_DEFAULT_HEIGHT = 140;

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

export function BucketNode(props: NodeProps<Node<BucketNodeData, 'bucket'>>) {
  const { data, selected, id } = props;
  const { entity, isDimmed, modulesCount, blocksCount, progress, width, height } = data;
  const potentialParentId = useAppSelector((s) => s.ui.potentialParentId);
  const isDropTarget = potentialParentId === id;
  const total = progress.total || 1;
  const done = progress.done ?? 0;
  const w = width ?? BUCKET_DEFAULT_WIDTH;
  const h = height ?? BUCKET_DEFAULT_HEIGHT;

  return (
    <>
      <NodeResizer
        isVisible={selected}
        minWidth={BUCKET_MIN_WIDTH}
        minHeight={BUCKET_MIN_HEIGHT}
        maxWidth={800}
        maxHeight={600}
        color="var(--color-bucket)"
        handleStyle={{ borderRadius: 2 }}
      />
      <div
        style={{
          ...frameStyle,
          width: w,
          height: h,
          opacity: isDimmed ? 0.5 : 1,
          border: isDropTarget ? '3px dashed var(--color-focus-border)' : frameStyle.border,
          transition: 'border 0.15s ease',
        }}
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
    </>
  );
}
