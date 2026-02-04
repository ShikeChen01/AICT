import React from 'react';
import { useAppSelector, useAppDispatch } from '../../store/hooks';
import { addEntity, createModule, createBlock, setParent } from '../../store/slices/entitiesSlice';
import { setNodePosition } from '../../store/slices/canvasSlice';
import { exitScope, setBucketCreationOpen, setConnectMode } from '../../store/slices/uiSlice';
import { openAgent } from '../../store/slices/agentSlice';
import { selectAllEntities } from '../../store/selectors/entitySelectors';
import { ToolButton } from './ToolButton';
import { FilterPanel } from './FilterPanel';
import type { Entity } from '../../../shared/types/entities';

const DEFAULT_PLACE_X = 120;
const DEFAULT_PLACE_Y = 120;

function canBeChild(childType: string, parentType?: string): boolean {
  if (!parentType) return false;
  if (parentType === 'bucket') return childType === 'module' || childType === 'block';
  if (parentType === 'module') return childType === 'module' || childType === 'block';
  return false;
}

const BackIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
    <path d="M15 18l-6-6 6-6" />
  </svg>
);

const sidebarStyle: React.CSSProperties = {
  width: 60,
  minWidth: 60,
  padding: 'var(--spacing-sm)',
  borderRight: '1px solid var(--color-widget-border)',
  background: 'var(--color-sidebar-background)',
  display: 'flex',
  flexDirection: 'column',
  alignItems: 'center',
  gap: 'var(--spacing-sm)',
};

export function Toolbar() {
  const dispatch = useAppDispatch();
  const entities = useAppSelector(selectAllEntities);
  const scopeEntityId = useAppSelector((s) => s.ui.scopeEntityId);
  const connectMode = useAppSelector((s) => s.ui.connectMode);
  const nodePositions = useAppSelector((s) => s.canvas.nodePositions);

  const addEntityToCanvas = (entity: Entity) => {
    dispatch(addEntity(entity));
    const count = entities.length;

    if (scopeEntityId) {
      const scopeEntity = entities.find((e) => e.id === scopeEntityId);
      if (scopeEntity && canBeChild(entity.type, scopeEntity.type)) {
        dispatch(setParent({ childId: entity.id, parentId: scopeEntityId }));
        const parentPos = nodePositions[scopeEntityId] ?? { x: 0, y: 0 };
        const childCount = scopeEntity.children.length;
        dispatch(
          setNodePosition({
            id: entity.id,
            position: {
              x: parentPos.x + 40 + (childCount % 3) * 180,
              y: parentPos.y + 60 + Math.floor(childCount / 3) * 120,
            },
          })
        );
        return;
      }
    }

    dispatch(
      setNodePosition({
        id: entity.id,
        position: {
          x: DEFAULT_PLACE_X + (count % 4) * 180,
          y: DEFAULT_PLACE_Y + Math.floor(count / 4) * 120,
        },
      })
    );
  };

  return (
    <div style={sidebarStyle}>
      {scopeEntityId && (
        <ToolButton
          title="Back"
          onClick={() => dispatch(exitScope())}
        >
          <BackIcon />
        </ToolButton>
      )}
      <ToolButton title="Add Bucket" onClick={() => dispatch(setBucketCreationOpen(true))}>
        <div style={{ fontSize: '10px', textAlign: 'center', lineHeight: '1.2' }}>
          <div style={{ fontSize: '14px' }}>＋</div>
          <div>Bucket</div>
        </div>
      </ToolButton>
      <ToolButton title="Add Module" onClick={() => addEntityToCanvas(createModule())}>
        <div style={{ fontSize: '10px', textAlign: 'center', lineHeight: '1.2' }}>
          <div style={{ fontSize: '14px' }}>＋</div>
          <div>Module</div>
        </div>
      </ToolButton>
      <ToolButton title="Add Block" onClick={() => addEntityToCanvas(createBlock())}>
        <div style={{ fontSize: '10px', textAlign: 'center', lineHeight: '1.2' }}>
          <div style={{ fontSize: '14px' }}>＋</div>
          <div>Block</div>
        </div>
      </ToolButton>
      <ToolButton
        title="Connect (draw dependency)"
        onClick={() => dispatch(setConnectMode(!connectMode))}
        active={connectMode}
      >
        ↔
      </ToolButton>
      <FilterPanel />
      <div style={{ flex: 1 }} />
      <ToolButton title="Open Agent" onClick={() => dispatch(openAgent())}>
        Agent
      </ToolButton>
    </div>
  );
}
