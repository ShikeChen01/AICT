import React from 'react';
import { type NodeProps } from 'reactflow';
import type { BucketNodeData } from '../../../shared/types/canvas';

const frameStyle: React.CSSProperties = {
  minWidth: 200,
  minHeight: 80,
  background: 'var(--color-bucket-bg)',
  border: '2px solid var(--color-bucket)',
  borderRadius: 'var(--radius-lg)',
  overflow: 'hidden',
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

export function BucketNode({ data }: NodeProps<BucketNodeData>) {
  const { entity, isDimmed, modulesCount, blocksCount, progress } = data;
  const total = progress.total || 1;
  const done = progress.done ?? 0;

  return (
    <div style={{ ...frameStyle, opacity: isDimmed ? 0.5 : 1 }}>
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
}
