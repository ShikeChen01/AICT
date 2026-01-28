export type EntityId = string;

type EntityType = "bucket" | "module" | "block";
type EntityStatus = "todo" | "doing" | "review" | "done";
type EntitySizeHint = "xs" | "s" | "m" | "l" | "xl";

type EntityTests = {
  block_test?: string;
  module_test?: string;
};

type AcceptanceCriterion = {
  id: string;
  text: string;
  done: boolean;
};

type BaseEntity = {
  id: EntityId;
  type: EntityType;
  name: string;
  purpose: string;
  path?: string;
  exports?: string[];
  imports?: string[];
  deps?: string[];
  children?: EntityId[];
  tests?: EntityTests;
  size_hint?: EntitySizeHint;
  status?: EntityStatus;
  acceptance_criteria?: AcceptanceCriterion[];
  tags?: string[];
};

export type Bucket = BaseEntity & {
  type: "bucket";
  external_apis?: string[];
};

export type Module = BaseEntity & {
  type: "module";
};

export type Block = BaseEntity & {
  type: "block";
  path: string;
};

export type Entity = Bucket | Module | Block;
