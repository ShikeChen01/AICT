/**
 * Core entity types for the canvas (Bucket, Module, Block).
 * @see docs/high_level_design.md § 2
 */

export type EntityId = string;

export type SizeHint = 'xs' | 's' | 'm' | 'l' | 'xl';
export type EntityStatus = 'todo' | 'doing' | 'review' | 'done';

export interface EntityTests {
  block_test?: string;
  module_test?: string;
}

export interface BaseEntity {
  id: EntityId;
  name: string;
  purpose: string;
  exports: string[];
  imports: string[];
  deps: string[];
  children: EntityId[];
  tests: EntityTests;
  size_hint: SizeHint;
  status: EntityStatus;
}

export interface Bucket extends BaseEntity {
  type: 'bucket';
  path?: string;
}

export interface Module extends BaseEntity {
  type: 'module';
  path?: string;
}

export interface Block extends BaseEntity {
  type: 'block';
  path: string; // Block typically has a file path
}

export type Entity = Bucket | Module | Block;

export function isBucket(e: Entity): e is Bucket {
  return e.type === 'bucket';
}
export function isModule(e: Entity): e is Module {
  return e.type === 'module';
}
export function isBlock(e: Entity): e is Block {
  return e.type === 'block';
}
