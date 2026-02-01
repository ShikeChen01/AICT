import React from 'react';
import { type NodeProps } from 'reactflow';
import type { BlockNodeData } from '../../../shared/types/canvas';

const chipStyle: React.CSSProperties = {
  display: 'inline-flex',
  alignItems: 'center',
  gap: 'var(--spacing-xs)',
  padding: 'var(--spacing-xs) var(--spacing-sm)',
  minWidth: 90,
  background: 'var(--color-block-bg)',
  border: '1px solid var(--color-block)',
  borderRadius: 'var(--radius-sm)',
  fontSize: 'var(--font-size-sm)',
  color: 'var(--color-foreground)',
};

const extBadgeStyle: React.CSSProperties = {
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-description)',
  marginLeft: 2,
};

export function BlockNode({ data }: NodeProps<BlockNodeData>) {
  const { entity, isDimmed, fileIcon, testPassed } = data;
  const path = (entity as { path?: string }).path ?? '';
  const ext = path ? path.split('.').pop() ?? '' : '';

  return (
    <div
      style={{
        ...chipStyle,
        opacity: isDimmed ? 0.5 : 1,
        boxShadow: testPassed ? '0 0 8px rgba(76, 175, 80, 0.5)' : undefined,
      }}
    >
      <span style={{ fontSize: '1em' }}>{fileIcon === '📄' ? '📄' : `[${fileIcon}]`}</span>
      <span>{entity.name}</span>
      {ext && <span style={extBadgeStyle}>.{ext}</span>}
    </div>
  );
}
