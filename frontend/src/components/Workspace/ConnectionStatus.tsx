/**
 * ConnectionStatus — WebSocket connection indicator.
 */

interface ConnectionStatusProps {
  isConnected: boolean;
}

export function ConnectionStatus({ isConnected }: ConnectionStatusProps) {
  return (
    <div
      className={`fixed bottom-4 right-4 flex items-center gap-2 px-3 py-2 rounded-full text-sm font-medium ${
        isConnected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
      }`}
    >
      <div
        className={`w-2 h-2 rounded-full ${
          isConnected ? 'bg-green-500' : 'bg-red-500 animate-pulse'
        }`}
      />
      {isConnected ? 'Connected' : 'Connecting...'}
    </div>
  );
}

export default ConnectionStatus;
