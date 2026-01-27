export interface WorkItem {
  id: string;
  title: string;
  description?: string;
  files?: string[];
}

export interface PlanStage {
  id: string;
  title: string;
  items: WorkItem[];
}

export interface Plan {
  id: string;
  scopeId?: string;
  stages: PlanStage[];
}
