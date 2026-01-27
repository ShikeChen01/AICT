export interface DiffPreviewProps {
  diff: string;
}

export function DiffPreview({ diff }: DiffPreviewProps) {
  return (
    <pre
      style={{
        background: "#1d1d1d",
        color: "#f1f1f1",
        padding: 12,
        borderRadius: 8,
        whiteSpace: "pre-wrap",
        maxHeight: 240,
        overflowY: "auto",
      }}
    >
      {diff || "No diff available."}
    </pre>
  );
}
