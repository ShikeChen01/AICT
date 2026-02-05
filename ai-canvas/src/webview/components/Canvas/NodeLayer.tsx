import React from 'react';
import { useAppSelector } from '../../store/hooks';
import type { BaseNode } from '../FlowDiagram/core/BaseNode';
import type { Position } from '../FlowDiagram/core/types';
import { BucketNodeView } from '../nodes/BucketNode';
import { ModuleNodeView } from '../nodes/ModuleNode';
import { BlockNodeView } from '../nodes/BlockNode';
import { ResizeHandles } from './ResizeHandles';
import type { BucketNodeModel } from '../nodes/BucketNodeModel';
import type { ModuleNodeModel } from '../nodes/ModuleNodeModel';
import type { BlockNodeModel } from '../nodes/BlockNodeModel';

const HANDLE_SIZE = 12;

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
}: NodeLayerProps) {
  const potentialParentId = useAppSelector((s) => s.ui.potentialParentId);
  return (
    <>
      {nodes.map((node) => {
        const View = getViewForType(node.type);
        return (
          <React.Fragment key={node.id}>
            <View
              model={node as BucketNodeModel | ModuleNodeModel | BlockNodeModel}
              onSelect={() => onSelect(node.id)}
              onDoubleClick={() => onDoubleClick(node.id)}
              onContextMenu={(e) => onContextMenu(node.id, e)}
              isDropTarget={potentialParentId === node.id}
            />
            {node.selected && (
              <ResizeHandles bounds={node.getBounds()} />
            )}
            {node.selected &&
              node.handles.map((handle) => {
                const pos = node.getHandlePosition(handle.position);
                return (
                  <div
                    key={handle.id}
                    role="button"
                    tabIndex={0}
                    aria-label={`Connect from ${handle.position}`}
                    style={{
                      position: 'absolute',
                      left: pos.x - HANDLE_SIZE / 2,
                      top: pos.y - HANDLE_SIZE / 2,
                      width: HANDLE_SIZE,
                      height: HANDLE_SIZE,
                      borderRadius: '50%',
                      background: 'var(--color-focus-border)',
                      border: '2px solid var(--color-background)',
                      cursor: 'crosshair',
                      pointerEvents: 'all',
                      boxSizing: 'border-box',
                    }}
                    onPointerDown={(e) => {
                      e.stopPropagation();
                      onHandlePointerDown(node.id, pos, e);
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
