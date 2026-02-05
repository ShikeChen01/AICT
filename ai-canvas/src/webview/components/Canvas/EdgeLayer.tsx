import React from 'react';
import type { BaseEdge } from '../FlowDiagram/core/BaseEdge';
import type { BaseNode } from '../FlowDiagram/core/BaseNode';
import type { EndpointIndex, Position } from '../FlowDiagram/core/types';
import { DependencyEdgeView } from '../edges/DependencyEdge';
import type { DependencyEdgeModel } from '../edges/DependencyEdgeModel';

interface EdgeLayerProps {
  edges: BaseEdge[];
  nodes: BaseNode[];
  onEdgeEndpointPointerDown: (
    edgeId: string,
    endpointIndex: EndpointIndex,
    nodes: [string, string],
    pos0: Position,
    pos1: Position,
    e: React.PointerEvent
  ) => void;
  onEdgeClick: (edgeId: string) => void;
}

function getConnectionPoint(
  node: BaseNode,
  otherNode: BaseNode
): Position {
  const nb = node.getBounds();
  const ob = otherNode.getBounds();
  const nodeCenterX = nb.x + nb.width / 2;
  const nodeCenterY = nb.y + nb.height / 2;
  const otherCenterX = ob.x + ob.width / 2;
  const otherCenterY = ob.y + ob.height / 2;
  const dx = otherCenterX - nodeCenterX;
  const dy = otherCenterY - nodeCenterY;
  if (Math.abs(dx) > Math.abs(dy)) {
    return dx > 0 ? node.getHandlePosition('right') : node.getHandlePosition('left');
  }
  return dy > 0 ? node.getHandlePosition('bottom') : node.getHandlePosition('top');
}

export function EdgeLayer({
  edges,
  nodes,
  onEdgeEndpointPointerDown,
  onEdgeClick,
}: EdgeLayerProps) {
  const nodeMap = new Map(nodes.map((n) => [n.id, n]));

  return (
    <svg
      className="edge-layer"
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'auto',
      }}
    >
      {edges.map((edge) => {
        const node0 = nodeMap.get(edge.nodes[0]);
        const node1 = nodeMap.get(edge.nodes[1]);
        if (!node0 || !node1) return null;
        const pos0 = getConnectionPoint(node0, node1);
        const pos1 = getConnectionPoint(node1, node0);

        if (edge.type === 'dependency') {
          return (
            <g
              key={edge.id}
              className={`edge ${edge.type}-edge ${edge.selected ? 'selected' : ''}`}
              style={{ pointerEvents: 'stroke' }}
            >
              <DependencyEdgeView
                model={edge as DependencyEdgeModel}
                pos0={pos0}
                pos1={pos1}
                onEndpointPointerDown={(index, e) =>
                  onEdgeEndpointPointerDown(
                    edge.id,
                    index,
                    edge.nodes,
                    pos0,
                    pos1,
                    e
                  )
                }
                onEdgeClick={() => onEdgeClick(edge.id)}
              />
            </g>
          );
        }

        const pathD = edge.getPath(pos0, pos1);
        const endpoints = edge.getEndpointBounds(pos0, pos1);
        return (
          <g
            key={edge.id}
            className={`edge ${edge.type}-edge ${edge.selected ? 'selected' : ''}`}
            style={{ pointerEvents: 'stroke' }}
          >
            <path
              d={pathD}
              fill="none"
              stroke="transparent"
              strokeWidth={12}
              style={{ cursor: 'pointer', pointerEvents: 'stroke' }}
              onClick={(e) => {
                e.stopPropagation();
                onEdgeClick(edge.id);
              }}
            />
            <path
              d={pathD}
              fill="none"
              stroke="var(--color-foreground)"
              strokeWidth={2}
              style={{ filter: 'invert(1) hue-rotate(180deg)', pointerEvents: 'none' }}
            />
            {edge.selected && (
              <>
                <circle
                  cx={endpoints[0].x}
                  cy={endpoints[0].y}
                  r={endpoints[0].r}
                  className="edge-endpoint"
                  style={{ cursor: 'grab', pointerEvents: 'all' }}
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    onEdgeEndpointPointerDown(
                      edge.id,
                      0,
                      edge.nodes,
                      pos0,
                      pos1,
                      e
                    );
                  }}
                />
                <circle
                  cx={endpoints[1].x}
                  cy={endpoints[1].y}
                  r={endpoints[1].r}
                  className="edge-endpoint"
                  style={{ cursor: 'grab', pointerEvents: 'all' }}
                  onPointerDown={(e) => {
                    e.stopPropagation();
                    onEdgeEndpointPointerDown(
                      edge.id,
                      1,
                      edge.nodes,
                      pos0,
                      pos1,
                      e
                    );
                  }}
                />
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}
