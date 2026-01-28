import type { EntityId } from "src/shared/types/entities";

type WorkItemType = "code" | "test" | "refactor" | "docs" | "analysis";
type WorkItemStatus = "todo" | "doing" | "done";

type WorkItem = {
  id: string;
  title: string;
  description?: string;
  type: WorkItemType;
  status?: WorkItemStatus;
  target_entity_id?: EntityId;
  files?: string[];
};

type PlanStage = {
  id: string;
  title: string;
  summary?: string;
  depends_on?: string[];
  work_items: WorkItem[];
  tests?: string[];
};

type Plan = {
  id: string;
  scope_id: EntityId;
  title?: string;
  summary?: string;
  stages: PlanStage[];
  risks?: string[];
  assumptions?: string[];
};

export type { Plan, PlanStage, WorkItem };
