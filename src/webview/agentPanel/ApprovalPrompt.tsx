export interface ApprovalPromptProps {
  message: string;
  onApprove: () => void;
  onReject: () => void;
}

export function ApprovalPrompt({ message, onApprove, onReject }: ApprovalPromptProps) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
      <span>{message}</span>
      <button type="button" onClick={onApprove}>
        Approve
      </button>
      <button type="button" onClick={onReject}>
        Reject
      </button>
    </div>
  );
}
