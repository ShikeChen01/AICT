import { describe, it, expect } from 'vitest';
import { isDescendant } from './entityHelpers';
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
    exports: [] as string[],
    imports: [] as string[],
    deps: [] as string[],
    children,
    tests: {} as { block_test?: string; module_test?: string },
    size_hint: 'm' as const,
    status: 'todo' as const,
  };
  if (type === 'bucket') return { ...base, type: 'bucket' };
  if (type === 'module') return { ...base, type: 'module' };
  return { ...base, type: 'block', path: 'x.ts' };
}

describe('isDescendant', () => {
  it('returns false when potentialDescendant is the same node', () => {
    const entities: Record<EntityId, Entity> = {
      a: makeEntity('a', 'bucket', ['b']),
      b: makeEntity('b', 'module', []),
    };
    expect(isDescendant('a', 'a', entities)).toBe(false);
  });

  it('returns true when potentialDescendant is a direct child of ancestor', () => {
    const entities: Record<EntityId, Entity> = {
      a: makeEntity('a', 'bucket', ['b']),
      b: makeEntity('b', 'module', []),
    };
    expect(isDescendant('b', 'a', entities)).toBe(true);
  });

  it('returns true when potentialDescendant is a deep descendant', () => {
    const entities: Record<EntityId, Entity> = {
      a: makeEntity('a', 'bucket', ['b']),
      b: makeEntity('b', 'module', ['c']),
      c: makeEntity('c', 'block', []),
    };
    expect(isDescendant('c', 'a', entities)).toBe(true);
    expect(isDescendant('c', 'b', entities)).toBe(true);
  });

  it('returns false when nodes are in unrelated branches', () => {
    const entities: Record<EntityId, Entity> = {
      a: makeEntity('a', 'bucket', ['b']),
      b: makeEntity('b', 'module', []),
      c: makeEntity('c', 'bucket', ['d']),
      d: makeEntity('d', 'module', []),
    };
    expect(isDescendant('d', 'a', entities)).toBe(false);
    expect(isDescendant('b', 'c', entities)).toBe(false);
  });

  it('returns false when ancestor entity is missing', () => {
    const entities: Record<EntityId, Entity> = {
      a: makeEntity('a', 'module', []),
    };
    expect(isDescendant('a', 'missing', entities)).toBe(false);
  });

  it('does not throw for empty entities', () => {
    expect(isDescendant('x', 'y', {})).toBe(false);
  });
});
