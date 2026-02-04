import React, { useState } from 'react';
import {
  getBezierPath,
  BaseEdge,
  type Edge,
  type EdgeProps,
} from '@xyflow/react';
import type { DependencyEdgeData, ApiContract } from '../../../shared/types/canvas';

const CONTRACT_CIRCLE_R = 8;

function ContractTooltip({ contract, x, y }: { contract: ApiContract; x: number; y: number }) {
  return (
    <foreignObject
      x={x - 80}
      y={y - 60}
      width={160}
      height={100}
      style={{ overflow: 'visible', pointerEvents: 'none' }}
    >
      <div
        style={{
          background: 'var(--color-sidebar-background)',
          border: '1px solid var(--color-widget-border)',
          borderRadius: 'var(--radius-md)',
          padding: 'var(--spacing-sm)',
          fontSize: 'var(--font-size-xs)',
          color: 'var(--color-foreground)',
          boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
        }}
      >
        <div style={{ fontWeight: 600, marginBottom: 4 }}>{contract.name}</div>
        <div>Type: {contract.type}</div>
        <div>Endpoint: {contract.endpoint || '—'}</div>
        <div>Auth: {contract.auth || '—'}</div>
        <div>Version: {contract.version || '—'}</div>
      </div>
    </foreignObject>
  );
}

export function DependencyEdge({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  sourcePosition,
  targetPosition,
  data,
  markerEnd,
}: EdgeProps<Edge<DependencyEdgeData>>) {
  const [path, labelX, labelY] = getBezierPath({
    sourceX,
    sourceY,
    targetX,
    targetY,
    sourcePosition,
    targetPosition,
  });
  const [showTooltip, setShowTooltip] = useState(false);
  const edgeData = data as DependencyEdgeData | undefined;
  const hasContract = edgeData?.hasApiContract && edgeData?.apiContract;
  const contract = edgeData?.apiContract;

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        markerEnd={markerEnd ?? undefined}
        style={{ strokeDasharray: '5,5' }}
      />
      {hasContract && contract && (
        <g
          transform={`translate(${labelX}, ${labelY})`}
          onMouseEnter={() => setShowTooltip(true)}
          onMouseLeave={() => setShowTooltip(false)}
          style={{ cursor: 'pointer' }}
        >
          <circle
            r={CONTRACT_CIRCLE_R}
            fill="var(--color-background)"
            stroke="var(--color-focus-border)"
            strokeWidth={2}
          />
          {showTooltip && (
            <ContractTooltip contract={contract} x={0} y={0} />
          )}
        </g>
      )}
    </>
  );
}
