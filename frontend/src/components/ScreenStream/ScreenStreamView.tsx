/**
 * ScreenStreamView — renders a live MJPEG stream from an agent's sandbox.
 *
 * Shows the sandbox's Xvfb display as a sequence of JPEG frames.
 * When sandboxId is null, shows a placeholder message.
 */

import { useScreenStream } from '../../hooks/useScreenStream';

interface ScreenStreamViewProps {
  sandboxId: string | null;
}

export function ScreenStreamView({ sandboxId }: ScreenStreamViewProps) {
  const { frameUrl, isConnected } = useScreenStream(sandboxId);

  if (!sandboxId) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-sm text-gray-500">
        Select an agent with a sandbox to view its screen.
      </div>
    );
  }

  return (
    <div className="relative flex h-full items-center justify-center bg-black">
      {/* Connection indicator */}
      <div className="absolute top-2 right-2 z-10 flex items-center gap-1.5 rounded-full bg-black/60 px-2 py-1 text-xs text-white">
        <span
          className={`inline-block h-2 w-2 rounded-full ${isConnected ? 'bg-green-400' : 'bg-red-400'}`}
        />
        {isConnected ? 'Live' : 'Connecting...'}
      </div>

      {frameUrl ? (
        <img
          src={frameUrl}
          alt="Sandbox screen"
          className="max-h-full max-w-full object-contain"
          draggable={false}
        />
      ) : (
        <div className="text-sm text-gray-400">
          {isConnected ? 'Waiting for frames...' : 'Connecting to sandbox display...'}
        </div>
      )}
    </div>
  );
}

export default ScreenStreamView;
