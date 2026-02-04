import { describe, it, expect } from 'vitest';
import {
  isPointInBounds,
  getNodeCenter,
  findPotentialParent,
  type NodeWithBounds,
} from './collision';
import type { EntityId, Entity } from '../../shared/types/entities';

function makeEntity(
  id: EntityId,
  type: 'bucket' | 'module' | 'block',
  children: EntityId[] = []
): Entity {
  const base = {
    id,
    name: id,
    purpose: '',
    exports: [],
    imports: [],
    deps: [],
    children,
    tests: {},
    size_hint: 'm' as const,
    status: 'todo' as const,
  };
  if (type === 'bucket') return { ...base, type: 'bucket' };
  if (type === 'module') return { ...base, type: 'module' };
  return { ...base, type: 'block', path: 'x.ts' };
}

describe('isPointInBounds', () => {
  const bounds = { x: 10, y: 20, width: 100, height: 50 };

  it('returns true when point is inside', () => {
    expect(isPointInBounds({ x: 50, y: 40 }, bounds)).toBe(true);
  });

  it('returns true on left and top edges', () => {
    expect(isPointInBounds({ x: 10, y: 20 }, bounds)).toBe(true);
  });

  it('returns true on right and bottom edges', () => {
    expect(isPointInBounds({ x: 110, y: 70 }, bounds)).toBe(true);
  });

  it('returns false when point is outside', () => {
    expect(isPointInBounds({ x: 9, y: 20 }, bounds)).toBe(false);
    expect(isPointInBounds({ x: 111, y: 70 }, bounds)).toBe(false);
    expect(isPointInBounds({ x: 50, y: 71 }, bounds)).toBe(false);
  });
});

describe('getNodeCenter', () => {
  it('returns center for typical position and size', () => {
    const pos = { x: 100, y: 200 };
    const size = { width: 160, height: 80 };
    expect(getNodeCenter(pos, size)).toEqual({ x: 180, y: 240 });
  });
});

describe('findPotentialParent', () => {
  it('returns null when no candidates contain the center', () => {
    const nodes: NodeWithBounds[] = [
      { id: 'bucket1', position: { x: 0, y: 0 }, size: { width: 200, height: 100 }, type: 'bucket' },
    ];
    const entities: Record<EntityId, Entity> = {
      bucket1: makeEntity('bucket1', 'bucket', []),
      mod1: makeEntity('mod1', 'module', []),
    };
    const result = findPotentialParent(
      'mod1',
      { x: 500, y: 500 },
      { width: 80, height: 40 },
      nodes,
      entities
    );
    expect(result).toBeNull();
  });

  it('returns the parent when one valid container contains the center', () => {
    const nodes: NodeWithBounds[] = [
      { id: 'bucket1', position: { x: 0, y: 0 }, size: { width: 200, height: 200 }, type: 'bucket' },
    ];
    const entities: Record<EntityId, Entity> = {
      bucket1: makeEntity('bucket1', 'bucket', []),
      mod1: makeEntity('mod1', 'module', []),
    };
    const center = { x: 100, y: 100 };
    const result = findPotentialParent(
      'mod1',
      { x: 60, y: 80 },
      { width: 80, height: 40 },
      nodes,
      entities
    );
    expect(result).toBe('bucket1');
  });

  it('returns smallest valid container when multiple contain the center', () => {
    const nodes: NodeWithBounds[] = [
      { id: 'bucket1', position: { x: 0, y: 0 }, size: { width: 300, height: 300 }, type: 'bucket' },
      { id: 'mod1', position: { x: 50, y: 50 }, size: { width: 100, height: 100 }, type: 'module' },
    ];
    const entities: Record<EntityId, Entity> = {
      bucket1: makeEntity('bucket1', 'bucket', ['mod1']),
      mod1: makeEntity('mod1', 'module', []),
    };
    const result = findPotentialParent(
      'block1',
      { x: 90, y: 90 },
      { width: 20, height: 20 },
      nodes,
      { ...entities, block1: makeEntity('block1', 'block', []) }
    );
    expect(result).toBe('mod1');
  });

  it('returns null when parent type cannot have this child type', () => {
    const nodes: NodeWithBounds[] = [
      { id: 'block1', position: { x: 0, y: 0 }, size: { width: 200, height: 100 }, type: 'block' },
    ];
    const entities: Record<EntityId, Entity> = {
      block1: makeEntity('block1', 'block', []),
      mod1: makeEntity('mod1', 'module', []),
    };
    const result = findPotentialParent(
      'mod1',
      { x: 50, y: 50 },
      { width: 80, height: 40 },
      nodes,
      entities
    );
    expect(result).toBeNull();
  });

  it('returns null when candidate would create circular reference (descendant as parent)', () => {
    const nodes: NodeWithBounds[] = [
      { id: 'bucket1', position: { x: 0, y: 0 }, size: { width: 300, height: 300 }, type: 'bucket' },
      { id: 'mod1', position: { x: 50, y: 50 }, size: { width: 100, height: 100 }, type: 'module' },
    ];
    const entities: Record<EntityId, Entity> = {
      bucket1: makeEntity('bucket1', 'bucket', ['mod1']),
      mod1: makeEntity('mod1', 'module', []),
    };
    const result = findPotentialParent(
      'bucket1',
      { x: 100, y: 100 },
      { width: 50, height: 50 },
      nodes,
      entities
    );
    expect(result).toBeNull();
  });

  it('returns null when dragged entity is missing', () => {
    const nodes: NodeWithBounds[] = [
      { id: 'bucket1', position: { x: 0, y: 0 }, size: { width: 200, height: 200 }, type: 'bucket' },
    ];
    const entities: Record<EntityId, Entity> = {
      bucket1: makeEntity('bucket1', 'bucket', []),
    };
    const result = findPotentialParent(
      'missing',
      { x: 100, y: 100 },
      { width: 80, height: 40 },
      nodes,
      entities
    );
    expect(result).toBeNull();
  });
});
