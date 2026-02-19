/**
 * ConnectionStatus — WebSocket connection indicator.
 */

interface ConnectionStatusProps {
  isConnected: boolean;
}

export function ConnectionStatus({ isConnected }: ConnectionStatusProps) {
  return (
    <div
      className={`fixed bottom-4 right-4 z-40 flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-medium shadow-sm ${
        isConnected
          ? 'border-emerald-200 bg-emerald-100 text-emerald-800'
          : 'border-amber-200 bg-amber-100 text-amber-800'
      }`}
    >
      <div
        className={`w-2 h-2 rounded-full ${
          isConnected ? 'bg-emerald-500' : 'bg-amber-500 animate-pulse'
        }`}
      />
      {isConnected ? 'Connected' : 'Connecting...'}
    </div>
  );
}

export default ConnectionStatus;
