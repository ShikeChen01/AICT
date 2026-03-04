/**
 * VncView — interactive remote desktop viewer for sandbox containers.
 *
 * Uses noVNC (RFB client) over WebSocket to provide full mouse + keyboard
 * interaction with the sandbox's Xvfb display, streamed via x11vnc.
 *
 * The connection path:
 *   Browser (noVNC) → Backend /ws/vnc proxy → Sandbox /ws/vnc → x11vnc TCP
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import RFB from '@novnc/novnc/lib/rfb';
import { getAuthToken } from '../../api/client';

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected';

interface VncViewProps {
  sandboxId: string | null;
  /** When true, user cannot interact — display-only mode. */
  viewOnly?: boolean;
}

export function VncView({ sandboxId, viewOnly = false }: VncViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rfbRef = useRef<RFB | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [interactive, setInteractive] = useState(!viewOnly);

  // Sync interactive mode with viewOnly prop changes
  useEffect(() => {
    setInteractive(!viewOnly);
  }, [viewOnly]);

  // Update RFB viewOnly when interactive state changes
  useEffect(() => {
    if (rfbRef.current) {
      rfbRef.current.viewOnly = !interactive;
    }
  }, [interactive]);

  const handleConnect = useCallback(() => {
    setStatus('connected');
    if (rfbRef.current) {
      rfbRef.current.scaleViewport = true;
      rfbRef.current.resizeSession = false;
      rfbRef.current.viewOnly = !interactive;
      rfbRef.current.focusOnClick = true;
    }
  }, [interactive]);

  const handleDisconnect = useCallback(() => {
    setStatus('disconnected');
    rfbRef.current = null;
  }, []);

  useEffect(() => {
    if (!sandboxId || !containerRef.current) {
      // Clean up any existing connection
      if (rfbRef.current) {
        rfbRef.current.disconnect();
        rfbRef.current = null;
      }
      setStatus('disconnected');
      return;
    }

    const token = getAuthToken();
    if (!token) return;

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl =
      `${protocol}//${window.location.host}/ws/vnc` +
      `?token=${encodeURIComponent(token)}` +
      `&sandbox_id=${encodeURIComponent(sandboxId)}`;

    setStatus('connecting');

    // Clear the container before noVNC adds its canvas
    const container = containerRef.current;
    container.innerHTML = '';

    try {
      const rfb = new RFB(container, wsUrl, { shared: true });
      rfb.scaleViewport = true;
      rfb.resizeSession = false;
      rfb.viewOnly = !interactive;
      rfb.focusOnClick = true;
      rfb.qualityLevel = 6;
      rfb.compressionLevel = 2;

      rfb.addEventListener('connect', handleConnect);
      rfb.addEventListener('disconnect', handleDisconnect);

      rfbRef.current = rfb;
    } catch {
      setStatus('disconnected');
    }

    return () => {
      if (rfbRef.current) {
        rfbRef.current.removeEventListener('connect', handleConnect);
        rfbRef.current.removeEventListener('disconnect', handleDisconnect);
        rfbRef.current.disconnect();
        rfbRef.current = null;
      }
    };
    // Reconnect when sandboxId changes; interactive is handled via separate effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sandboxId]);

  if (!sandboxId) {
    return (
      <div className="flex h-full items-center justify-center p-4 text-sm text-gray-500">
        Select an agent with a sandbox to view its screen.
      </div>
    );
  }

  return (
    <div className="relative flex h-full flex-col bg-black">
      {/* Top bar: status indicator + interactive toggle */}
      <div className="absolute top-2 right-2 z-10 flex items-center gap-2">
        {/* Interactive toggle */}
        <button
          type="button"
          onClick={() => setInteractive((prev) => !prev)}
          className={`rounded-full px-2.5 py-1 text-xs font-medium transition-colors ${
            interactive
              ? 'bg-blue-500/80 text-white hover:bg-blue-600/80'
              : 'bg-black/60 text-gray-300 hover:bg-black/80'
          }`}
          title={interactive ? 'Click to disable interaction' : 'Click to enable remote control'}
        >
          {interactive ? 'Interactive' : 'View Only'}
        </button>

        {/* Connection status */}
        <div className="flex items-center gap-1.5 rounded-full bg-black/60 px-2 py-1 text-xs text-white">
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              status === 'connected'
                ? 'bg-green-400'
                : status === 'connecting'
                  ? 'bg-yellow-400 animate-pulse'
                  : 'bg-red-400'
            }`}
          />
          {status === 'connected' ? 'VNC Live' : status === 'connecting' ? 'Connecting...' : 'Disconnected'}
        </div>
      </div>

      {/* noVNC canvas container */}
      <div
        ref={containerRef}
        className="flex-1 min-h-0"
        style={{
          /* noVNC creates a canvas inside; this ensures it fills the space */
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      />

      {/* Overlay message when disconnected */}
      {status === 'disconnected' && (
        <div className="absolute inset-0 flex items-center justify-center">
          <span className="text-sm text-gray-400">
            Connecting to sandbox display...
          </span>
        </div>
      )}
    </div>
  );
}

export default VncView;
