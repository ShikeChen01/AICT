import React from 'react';
import { useAppStore } from './store/appStore';
import { useCanvasStore } from './store/canvasStore';
import type { Bucket, Module, Block, Entity } from '../shared/types/entities';

function randomId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return crypto.randomUUID();
  }
  return `id-${Date.now()}-${Math.random().toString(36).slice(2, 11)}`;
}

const defaultBase = {
  purpose: '',
  exports: [],
  imports: [],
  deps: [],
  children: [],
  tests: {},
  size_hint: 'm' as const,
  status: 'todo' as const
};

function createBucket(): Bucket {
  return {
    ...defaultBase,
    id: randomId(),
    type: 'bucket',
    name: 'New Bucket'
  };
}
function createModule(): Module {
  return {
    ...defaultBase,
    id: randomId(),
    type: 'module',
    name: 'New Module'
  };
}
function createBlock(): Block {
  return {
    ...defaultBase,
    id: randomId(),
    type: 'block',
    name: 'New Block',
    path: 'untitled'
  };
}

const toolbarStyle: React.CSSProperties = {
  display: 'flex',
  gap: '8px',
  padding: '8px 12px',
  borderBottom: '1px solid #eee',
  background: '#fafafa'
};
const btnStyle: React.CSSProperties = {
  padding: '6px 12px',
  fontSize: '12px',
  cursor: 'pointer'
};

export function Toolbar() {
  const createEntity = useAppStore((s) => s.createEntity);
  const syncFromEntities = useCanvasStore((s) => s.syncFromEntities);
  const entities = useAppStore((s) => s.entities);

  const addEntity = (entity: Entity) => {
    createEntity(entity);
    const nextEntities = [...entities, entity];
    useCanvasStore.getState().syncFromEntities(nextEntities);
  };

  return (
    <div style={toolbarStyle}>
      <button
        style={btnStyle}
        type="button"
        onClick={() => addEntity(createBucket())}
      >
        + Bucket
      </button>
      <button
        style={btnStyle}
        type="button"
        onClick={() => addEntity(createModule())}
      >
        + Module
      </button>
      <button
        style={btnStyle}
        type="button"
        onClick={() => addEntity(createBlock())}
      >
        + Block
      </button>
    </div>
  );
}
