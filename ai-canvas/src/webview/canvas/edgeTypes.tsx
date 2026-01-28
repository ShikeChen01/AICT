import React from "react";
import type { EdgeProps } from "reactflow";
import { BaseEdge, getBezierPath } from "reactflow";

const ContainmentEdge: React.FC<EdgeProps> = (props) => {
  const [path] = getBezierPath(props);
  return <BaseEdge path={path} style={{ stroke: "#94a3b8", strokeWidth: 1.5 }} />;
};

const DependencyEdge: React.FC<EdgeProps> = (props) => {
  const [path] = getBezierPath(props);
  return <BaseEdge path={path} style={{ stroke: "#64748b", strokeWidth: 2 }} />;
};

export const edgeTypes = {
  contains: ContainmentEdge,
  depends_on: DependencyEdge,
};
