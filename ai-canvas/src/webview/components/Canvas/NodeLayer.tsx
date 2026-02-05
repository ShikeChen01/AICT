import React from 'react';
import { useAppSelector } from '../../store/hooks';
import type { BaseNode } from '../FlowDiagram/core/BaseNode';
import { BucketNodeView } from '../nodes/BucketNode';
import { ModuleNodeView } from '../nodes/ModuleNode';
import { BlockNodeView } from '../nodes/BlockNode';
import { ResizeHandles } from './ResizeHandles';
import type { BucketNodeModel } from '../nodes/BucketNodeModel';
import type { ModuleNodeModel } from '../nodes/ModuleNodeModel';
import type { BlockNodeModel } from '../nodes/BlockNodeModel';

interface NodeLayerProps {
  nodes: BaseNode[];
  onSelect: (id: string, additive?: boolean) => void;
  onDoubleClick: (id: string) => void;
  onContextMenu: (id: string, e: React.MouseEvent) => void;
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
          </React.Fragment>
        );
      })}
    </>
  );
}
