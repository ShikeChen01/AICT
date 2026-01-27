import type { NodeProps } from "reactflow";

interface NodeData {
  label?: string;
  description?: string;
}

function BaseNode({ data, className }: { data: NodeData; className: string }) {
  return (
    <div className={className} style={{ padding: 12, borderRadius: 10, border: "1px solid #222" }}>
      <div style={{ fontWeight: 600 }}>{data.label ?? "Untitled"}</div>
      {data.description ? <div style={{ fontSize: 12, opacity: 0.7 }}>{data.description}</div> : null}
    </div>
  );
}

export function BucketNode({ data }: NodeProps<NodeData>) {
  return <BaseNode data={data} className="node-bucket" />;
}

export function ModuleNode({ data }: NodeProps<NodeData>) {
  return <BaseNode data={data} className="node-module" />;
}

export function BlockNode({ data }: NodeProps<NodeData>) {
  return <BaseNode data={data} className="node-block" />;
}

export const nodeTypes = {
  bucket: BucketNode,
  module: ModuleNode,
  block: BlockNode,
};
