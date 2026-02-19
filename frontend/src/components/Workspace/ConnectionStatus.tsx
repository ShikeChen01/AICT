/**
 * ConnectionStatus — WebSocket connection and backend worker health indicator.
 */

interface ConnectionStatusProps {
  isConnected: boolean;
  workersReady?: boolean;
}

export function ConnectionStatus({ isConnected, workersReady = true }: ConnectionStatusProps) {
  const degraded = isConnected && !workersReady;

  const colorClass = !isConnected
    ? 'border-amber-200 bg-amber-100 text-amber-800'
    : degraded
      ? 'border-red-200 bg-red-100 text-red-800'
      : 'border-emerald-200 bg-emerald-100 text-emerald-800';

  const dotClass = !isConnected
    ? 'bg-amber-500 animate-pulse'
    : degraded
      ? 'bg-red-500 animate-pulse'
      : 'bg-emerald-500';

  const label = !isConnected
    ? 'Connecting...'
    : degraded
      ? 'Workers not ready'
      : 'Connected';

  const title = degraded
    ? 'Backend agent workers failed to start. Messages will not be processed until the server restarts.'
    : undefined;

  return (
    <div
      className={`fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium shadow-sm ${colorClass}`}
      title={title}
    >
      <div className={`w-2 h-2 rounded-full ${dotClass}`} />
      {label}
    </div>
  );
}

export default ConnectionStatus;
