export type EntityId = string;

export type EntityType = "bucket" | "module" | "block";
export type SizeHint = "xs" | "s" | "m" | "l" | "xl";
export type EntityStatus = "todo" | "doing" | "review" | "done";

export interface EntityTests {
  block_test?: string;
  module_test?: string;
}

export interface BaseEntity {
  id: EntityId;
  type: EntityType;
  name: string;
  purpose: string;
  exports: string[];
  imports: string[];
  deps: string[];
  children: EntityId[];
  tests?: EntityTests;
  size_hint?: SizeHint;
  status?: EntityStatus;
  path?: string;
}

export interface Bucket extends BaseEntity {
  type: "bucket";
}

export interface Module extends BaseEntity {
  type: "module";
}

export interface Block extends BaseEntity {
  type: "block";
  path: string;
}

export type Entity = Bucket | Module | Block;
