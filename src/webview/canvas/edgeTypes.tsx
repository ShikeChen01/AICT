import { BaseEdge, getBezierPath } from "reactflow";
import type { EdgeProps } from "reactflow";

function ContainmentEdge(props: EdgeProps) {
  const [edgePath] = getBezierPath(props);
  return <BaseEdge path={edgePath} style={{ stroke: "#555", strokeWidth: 2 }} />;
}

function DependencyEdge(props: EdgeProps) {
  const [edgePath] = getBezierPath(props);
  return <BaseEdge path={edgePath} style={{ stroke: "#c85", strokeWidth: 2, strokeDasharray: "6 4" }} />;
}

export const edgeTypes = {
  containment: ContainmentEdge,
  dependency: DependencyEdge,
};
