import React, { useState, useCallback } from 'react';
import { useAppSelector } from '../../store/hooks';
import type { BaseNode } from '../FlowDiagram/core/BaseNode';
import type { Position } from '../FlowDiagram/core/types';
import { BucketNodeView } from '../nodes/BucketNode';
import { ModuleNodeView } from '../nodes/ModuleNode';
import { BlockNodeView } from '../nodes/BlockNode';
import { ResizeHandles, type Corner } from './ResizeHandles';
import type { BucketNodeModel } from '../nodes/BucketNodeModel';
import type { ModuleNodeModel } from '../nodes/ModuleNodeModel';
import type { BlockNodeModel } from '../nodes/BlockNodeModel';

/** Size of connection handle dots (circles on the sides of nodes) */
const CONNECT_HANDLE_SIZE = 10;

interface NodeLayerProps {
  nodes: BaseNode[];
  onSelect: (id: string, additive?: boolean) => void;
  onDoubleClick: (id: string) => void;
  onContextMenu: (id: string, e: React.MouseEvent) => void;
  onHandlePointerDown: (
    nodeId: string,
    handlePos: Position,
    e: React.PointerEvent
  ) => void;
  onResizePointerDown: (
    nodeId: string,
    corner: Corner,
    e: React.PointerEvent
  ) => void;
}

function getViewForType(type: string) {
  switch (type) {
    case 'bucket':
      return BucketNodeView;
    case 'module':
      return ModuleNodeView;
    case 'block':
      return BlockNodeView;
    case 'api_contract':
      return ModuleNodeView;
    default:
      return BlockNodeView;
  }
}

export function NodeLayer({
  nodes,
  onSelect,
  onDoubleClick,
  onContextMenu,
  onHandlePointerDown,
  onResizePointerDown,
}: NodeLayerProps) {
  const potentialParentId = useAppSelector((s) => s.ui.potentialParentId);
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);

  const handlePointerEnter = useCallback((nodeId: string) => {
    setHoveredNodeId(nodeId);
  }, []);

  const handlePointerLeave = useCallback(() => {
    setHoveredNodeId(null);
  }, []);

  return (
    <>
      {nodes.map((node) => {
        const View = getViewForType(node.type);
        const showHandles = node.selected || hoveredNodeId === node.id;

        return (
          <React.Fragment key={node.id}>
            {/* The node view itself — hover detection is on the node view div directly */}
            <View
              model={node as BucketNodeModel | ModuleNodeModel | BlockNodeModel}
              onSelect={() => onSelect(node.id)}
              onDoubleClick={() => onDoubleClick(node.id)}
              onContextMenu={(e) => onContextMenu(node.id, e)}
              isDropTarget={potentialParentId === node.id}
              onPointerEnter={() => handlePointerEnter(node.id)}
              onPointerLeave={handlePointerLeave}
            />

            {/* Resize handles -- square corners, shown when selected */}
            {node.selected && (
              <ResizeHandles
                bounds={node.getBounds()}
                onResizePointerDown={(corner, e) =>
                  onResizePointerDown(node.id, corner, e)
                }
              />
            )}

            {/* Connection handles -- round dots on sides, shown on hover or selection */}
            {showHandles &&
              node.handles.map((handle) => {
                const pos = node.getHandlePosition(handle.position);
                return (
                  <div
                    key={handle.id}
                    className="connection-handle"
                    role="button"
                    tabIndex={0}
                    aria-label={`Connect from ${handle.position}`}
                    style={{
                      position: 'absolute',
                      left: pos.x - CONNECT_HANDLE_SIZE / 2,
                      top: pos.y - CONNECT_HANDLE_SIZE / 2,
                      width: CONNECT_HANDLE_SIZE,
                      height: CONNECT_HANDLE_SIZE,
                      borderRadius: '50%',
                      background: 'var(--color-background)',
                      border: '2px solid var(--color-foreground)',
                      cursor: 'crosshair',
                      pointerEvents: 'all',
                      boxSizing: 'border-box',
                      zIndex: 15,
                      opacity: node.selected ? 1 : 0.7,
                      transition: 'transform 0.15s ease, opacity 0.15s ease, background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease',
                    }}
                    onPointerDown={(e) => {
                      e.stopPropagation();
                      onHandlePointerDown(node.id, pos, e);
                    }}
                    onPointerEnter={(e) => {
                      const el = e.currentTarget;
                      el.style.background = 'var(--color-focus-border)';
                      el.style.borderColor = 'var(--color-focus-border)';
                      el.style.transform = 'scale(1.4)';
                      el.style.opacity = '1';
                      el.style.boxShadow = '0 0 6px var(--color-focus-border)';
                    }}
                    onPointerLeave={(e) => {
                      const el = e.currentTarget;
                      el.style.background = 'var(--color-background)';
                      el.style.borderColor = 'var(--color-foreground)';
                      el.style.transform = 'scale(1)';
                      el.style.opacity = node.selected ? '1' : '0.7';
                      el.style.boxShadow = 'none';
                    }}
                  />
                );
              })}
          </React.Fragment>
        );
      })}
    </>
  );
}
