import React from 'react';
import { type Node, type NodeProps, NodeResizer, Handle, Position } from '@xyflow/react';
import { useAppSelector } from '../../store/hooks';
import type { ModuleNodeData } from '../../../shared/types/canvas';

const MODULE_MIN_WIDTH = 160;
const MODULE_MIN_HEIGHT = 56;
const MODULE_DEFAULT_WIDTH = 220;
const MODULE_DEFAULT_HEIGHT = 80;

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

export function ModuleNode(props: NodeProps<Node<ModuleNodeData, 'module'>>) {
  const { data, selected, id } = props;
  const { entity, isDimmed, blocksCount, depsCount, progress } = data;
  const potentialParentId = useAppSelector((s) => s.ui.potentialParentId);
  const isDropTarget = potentialParentId === id;
  const total = progress.total || 1;
  const done = progress.done ?? 0;

  return (
    <>
      <NodeResizer
        isVisible={selected}
        minWidth={MODULE_MIN_WIDTH}
        minHeight={MODULE_MIN_HEIGHT}
        maxWidth={500}
        maxHeight={400}
        color="var(--color-module)"
        handleStyle={{ borderRadius: 2 }}
      />
      {/* Connection handles - 4 side middles only (corners reserved for NodeResizer) */}
      <Handle type="source" position={Position.Top} id="top" isConnectable style={{ left: '50%' }} />
      <Handle type="source" position={Position.Left} id="left" isConnectable style={{ top: '50%' }} />
      <Handle type="source" position={Position.Right} id="right" isConnectable style={{ top: '50%' }} />
      <Handle type="source" position={Position.Bottom} id="bottom" isConnectable style={{ left: '50%' }} />

      <div
        style={{
          ...cardStyle,
          opacity: isDimmed ? 0.5 : 1,
          border: isDropTarget ? '3px dashed var(--color-focus-border)' : cardStyle.border,
          transition: 'border 0.15s ease',
        }}
      >
      <div style={headerStyle}>{entity.name}</div>
      <div style={summaryStyle}>
        {done}/{total} · {blocksCount} blocks · {depsCount} deps
        {entity.purpose ? ` · ${entity.purpose.slice(0, 40)}${entity.purpose.length > 40 ? '…' : ''}` : ''}
      </div>
    </div>
    </>
  );
}
