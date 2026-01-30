import React from 'react';
import { Handle, Position, type NodeProps } from 'reactflow';
import type { Entity } from '../../shared/types/entities';

const baseStyle: React.CSSProperties = {
  padding: '8px 12px',
  borderRadius: '8px',
  minWidth: '120px',
  fontSize: '12px',
  border: '1px solid #ccc'
};

function EntityNode({ data }: NodeProps<{ label: string; entity: Entity }>) {
  const entity = data.entity;
  const typeStyle: React.CSSProperties =
    entity.type === 'bucket'
      ? { ...baseStyle, background: '#e3f2fd', borderColor: '#2196f3' }
      : entity.type === 'module'
        ? { ...baseStyle, background: '#f3e5f5', borderColor: '#9c27b0' }
        : { ...baseStyle, background: '#e8f5e9', borderColor: '#4caf50' };

  return (
    <>
      <Handle type="target" position={Position.Top} />
      <div style={typeStyle}>
        <div style={{ fontWeight: 600 }}>{data.label || entity.name}</div>
        <div style={{ fontSize: 10, color: '#666', marginTop: 4 }}>
          {entity.type} · {entity.status}
        </div>
      </div>
      <Handle type="source" position={Position.Bottom} />
    </>
  );
}

export const nodeTypes = {
  bucket: EntityNode,
  module: EntityNode,
  block: EntityNode
};
