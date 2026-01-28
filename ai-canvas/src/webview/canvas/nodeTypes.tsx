import React from "react";
import type { NodeProps } from "reactflow";

const Card: React.FC<{ title: string; subtitle?: string; accent: string }> = ({
  title,
  subtitle,
  accent,
}) => (
  <div
    style={{
      minWidth: 160,
      padding: "12px 14px",
      borderRadius: 12,
      background: "#fffdf7",
      border: `1px solid ${accent}`,
      boxShadow: "0 8px 20px rgba(15,23,42,0.08)",
    }}
  >
    <div style={{ fontSize: 12, textTransform: "uppercase", letterSpacing: "0.12em", color: accent }}>
      {title}
    </div>
    {subtitle ? (
      <div style={{ marginTop: 6, fontSize: 13, color: "#475569" }}>{subtitle}</div>
    ) : null}
  </div>
);

const BucketNode: React.FC<NodeProps<{ label?: string; purpose?: string }>> = ({ data }) => (
  <Card title={data.label ?? "Bucket"} subtitle={data.purpose} accent="#b45309" />
);

const ModuleNode: React.FC<NodeProps<{ label?: string; purpose?: string }>> = ({ data }) => (
  <Card title={data.label ?? "Module"} subtitle={data.purpose} accent="#1d4ed8" />
);

const BlockNode: React.FC<NodeProps<{ label?: string; purpose?: string }>> = ({ data }) => (
  <Card title={data.label ?? "Block"} subtitle={data.purpose} accent="#0f766e" />
);

export const nodeTypes = {
  bucket: BucketNode,
  module: ModuleNode,
  block: BlockNode,
};
