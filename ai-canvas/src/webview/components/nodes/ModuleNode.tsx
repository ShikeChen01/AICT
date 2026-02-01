import React from 'react';
import { type NodeProps } from 'reactflow';
import type { ModuleNodeData } from '../../../shared/types/canvas';

const cardStyle: React.CSSProperties = {
  minWidth: 160,
  minHeight: 56,
  background: 'var(--color-module-bg)',
  border: '1px solid var(--color-module)',
  borderRadius: 'var(--radius-md)',
  overflow: 'hidden',
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

export function ModuleNode({ data }: NodeProps<ModuleNodeData>) {
  const { entity, isDimmed, blocksCount, depsCount, progress } = data;
  const total = progress.total || 1;
  const done = progress.done ?? 0;

  return (
    <div style={{ ...cardStyle, opacity: isDimmed ? 0.5 : 1 }}>
      <div style={headerStyle}>{entity.name}</div>
      <div style={summaryStyle}>
        {done}/{total} · {blocksCount} blocks · {depsCount} deps
        {entity.purpose ? ` · ${entity.purpose.slice(0, 40)}${entity.purpose.length > 40 ? '…' : ''}` : ''}
      </div>
    </div>
  );
}
