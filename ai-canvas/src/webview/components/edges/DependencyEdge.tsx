import React, { useState, memo } from 'react';
import type { DependencyEdgeData, ApiContract } from '../../../shared/types/canvas';
import type { DependencyEdgeModel } from './DependencyEdgeModel';
import type { Position } from '../FlowDiagram/core/types';

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

export interface DependencyEdgeViewProps {
  model: DependencyEdgeModel;
  pos0: Position;
  pos1: Position;
  onEndpointPointerDown: (index: 0 | 1, e: React.PointerEvent) => void;
  onEdgeClick?: () => void;
}

export const DependencyEdgeView = memo(function DependencyEdgeView({
  model,
  pos0,
  pos1,
  onEndpointPointerDown,
  onEdgeClick,
}: DependencyEdgeViewProps) {
  const [showTooltip, setShowTooltip] = useState(false);
  const pathD = model.getPath(pos0, pos1);
  const edgeData = model.data as DependencyEdgeData | undefined;
  const hasContract = edgeData?.hasApiContract && edgeData?.apiContract;
  const contract = edgeData?.apiContract;
  
  // Calculate midpoint for contract indicator
  const midX = (pos0.x + pos1.x) / 2;
  const midY = (pos0.y + pos1.y) / 2;

  return (
    <g className={`dependency-edge ${model.selected ? 'selected' : ''}`}>
      {onEdgeClick && (
        <path
          d={pathD}
          fill="none"
          stroke="transparent"
          strokeWidth={12}
          style={{ cursor: 'pointer', pointerEvents: 'stroke' }}
          onClick={(e) => {
            e.stopPropagation();
            onEdgeClick();
          }}
        />
      )}
      <path
        d={pathD}
        fill="none"
        stroke="var(--color-foreground)"
        strokeWidth={2}
        strokeDasharray="5,5"
        style={{ filter: 'invert(1) hue-rotate(180deg)', pointerEvents: 'none' }}
      />
      {hasContract && contract && (
        <g
          transform={`translate(${midX}, ${midY})`}
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
      {/* Endpoint circles for reconnection (only visible when selected) */}
      {model.selected && (
        <>
          <circle
            cx={pos0.x}
            cy={pos0.y}
            r={6}
            fill="var(--color-focus-border)"
            stroke="var(--color-background)"
            strokeWidth={2}
            style={{ cursor: 'grab', pointerEvents: 'all' }}
            onPointerDown={(e) => {
              e.stopPropagation();
              onEndpointPointerDown(0, e);
            }}
          />
          <circle
            cx={pos1.x}
            cy={pos1.y}
            r={6}
            fill="var(--color-focus-border)"
            stroke="var(--color-background)"
            strokeWidth={2}
            style={{ cursor: 'grab', pointerEvents: 'all' }}
            onPointerDown={(e) => {
              e.stopPropagation();
              onEndpointPointerDown(1, e);
            }}
          />
        </>
      )}
    </g>
  );
});
