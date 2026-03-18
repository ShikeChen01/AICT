/**
 * VncView — interactive remote desktop viewer for sandbox containers.
 *
 * Uses noVNC (RFB client) over WebSocket to provide full mouse + keyboard
 * interaction with the sandbox's Xvfb display, streamed via x11vnc.
 *
 * The connection path:
 *   Browser (noVNC) → Backend /ws/vnc proxy → Sandbox /ws/vnc → x11vnc TCP
 *
 * Features:
 *   - Auto-reconnect with exponential backoff on disconnect
 *   - Interactive/view-only toggle
 *   - Connection status indicator
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import RFB from '@novnc/novnc/lib/rfb';
import { getAuthToken, getSandboxWsBase } from '../../api/client';

type ConnectionStatus = 'disconnected' | 'connecting' | 'connected';

interface VncViewProps {
  sandboxId: string | null;
  /** When true, user cannot interact — display-only mode. */
  viewOnly?: boolean;
}

/** Max reconnect attempts before giving up */
const MAX_RECONNECT_ATTEMPTS = 10;
/** Base delay between reconnect attempts (ms). Doubles each attempt, max 30s. */
const BASE_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30_000;

export function VncView({ sandboxId, viewOnly = false }: VncViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rfbRef = useRef<RFB | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>('disconnected');
  const [interactive, setInteractive] = useState(!viewOnly);
  const [disconnectReason, setDisconnectReason] = useState<string | null>(null);

  // Reconnect state — kept in refs so the effect closure always sees the latest.
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  /** Set to true when the component is unmounted or sandboxId changes */
  const shouldStopRef = useRef(false);

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

  /** Build the WebSocket URL for the VNC proxy endpoint (backend /ws/vnc). */
  const buildWsUrl = useCallback(() => {
    const token = getAuthToken();
    if (!token || !sandboxId) return null;

    const wsBase = getSandboxWsBase();
    return (
      `${wsBase}/vnc` +
      `?token=${encodeURIComponent(token)}` +
      `&sandbox_id=${encodeURIComponent(sandboxId)}`
    );
  }, [sandboxId]);

  /** Tear down any existing RFB connection. */
  const destroyRfb = useCallback(() => {
    if (rfbRef.current) {
      try {
        rfbRef.current.disconnect();
      } catch {
        // Ignore errors during teardown
      }
      rfbRef.current = null;
    }
  }, []);

  /** Cancel any pending reconnect timer. */
  const cancelReconnect = useCallback(() => {
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  /** Create a new RFB connection. */
  const connect = useCallback(() => {
    if (!containerRef.current || shouldStopRef.current) return;

    const wsUrl = buildWsUrl();
    if (!wsUrl) return;

    setStatus('connecting');
    setDisconnectReason(null);

    // Clear the container before noVNC adds its canvas
    const container = containerRef.current;
    container.innerHTML = '';

    try {
      // Create WebSocket ourselves so we can capture close reason from backend.
      // The backend VNC endpoint accepts with subprotocol="binary", so we MUST
      // request it — otherwise the handshake is invalid and the connection dies
      // with code 1006 before the upgrade completes.
      const ws = new WebSocket(wsUrl, ['binary']);
      ws.binaryType = 'arraybuffer';
      ws.onclose = (ev) => {
        if (ev.reason) {
          setDisconnectReason(ev.reason);
        } else if (ev.code === 1006) {
          setDisconnectReason('Connection closed unexpectedly (upstream may be unreachable)');
        }
      };
      const rfb = new RFB(container, ws, { shared: true });
      rfb.scaleViewport = true;
      rfb.resizeSession = false;
      rfb.viewOnly = !interactive;
      rfb.focusOnClick = true;
      rfb.qualityLevel = 6;
      rfb.compressionLevel = 2;

      rfb.addEventListener('connect', () => {
        setStatus('connected');
        setDisconnectReason(null);
        reconnectAttemptRef.current = 0; // Reset backoff on success
        if (rfbRef.current) {
          rfbRef.current.scaleViewport = true;
          rfbRef.current.resizeSession = false;
          rfbRef.current.viewOnly = !interactive;
          rfbRef.current.focusOnClick = true;
        }
      });

      rfb.addEventListener('disconnect', () => {
        setStatus('disconnected');
        rfbRef.current = null;

        // Auto-reconnect unless we intentionally tore down
        if (!shouldStopRef.current && reconnectAttemptRef.current < MAX_RECONNECT_ATTEMPTS) {
          const attempt = reconnectAttemptRef.current;
          const delay = Math.min(
            BASE_RECONNECT_DELAY_MS * Math.pow(2, attempt),
            MAX_RECONNECT_DELAY_MS,
          );
          reconnectAttemptRef.current = attempt + 1;
          console.log(
            `[VNC] Reconnecting in ${delay}ms (attempt ${attempt + 1}/${MAX_RECONNECT_ATTEMPTS})`,
          );
          reconnectTimerRef.current = setTimeout(() => {
            reconnectTimerRef.current = null;
            connect();
          }, delay);
        }
      });

      rfbRef.current = rfb;
    } catch (err) {
      console.error('[VNC] Failed to create RFB connection:', err);
      setStatus('disconnected');
    }
  }, [buildWsUrl, interactive]);

  // Main effect: connect when sandboxId changes
  useEffect(() => {
    shouldStopRef.current = false;
    reconnectAttemptRef.current = 0;
    cancelReconnect();
    destroyRfb();

    if (!sandboxId) {
      setStatus('disconnected');
      return;
    }

    connect();

    return () => {
      shouldStopRef.current = true;
      cancelReconnect();
      destroyRfb();
    };
    // Reconnect when sandboxId changes; interactive is handled via separate effect
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sandboxId]);

  if (!sandboxId) {
    return (
      <div className="flex flex-1 items-center justify-center p-4 text-sm text-gray-500">
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
          {status === 'connected'
            ? 'VNC Live'
            : status === 'connecting'
              ? 'Connecting...'
              : reconnectAttemptRef.current > 0 && reconnectAttemptRef.current < MAX_RECONNECT_ATTEMPTS
                ? 'Reconnecting...'
                : 'Disconnected'}
        </div>
      </div>

      {/* noVNC canvas container — uses relative positioning so noVNC's
          internal 100% width/height screen wrapper resolves against this
          element's flex-computed dimensions. */}
      <div
        ref={containerRef}
        className="relative flex-1 min-h-0 overflow-hidden"
      />

      {/* Overlay message when not connected */}
      {status !== 'connected' && (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-gradient-to-b from-[#0f172a] to-[#1e293b]">
          {status === 'connecting' ? (
            <>
              <div className="w-10 h-10 rounded-full border-2 border-blue-500/30 border-t-blue-400 animate-spin" />
              <span className="text-sm text-gray-300 font-medium">Connecting to sandbox display…</span>
              {reconnectAttemptRef.current > 0 && (
                <span className="text-xs text-gray-500">
                  Attempt {reconnectAttemptRef.current}/{MAX_RECONNECT_ATTEMPTS}
                </span>
              )}
            </>
          ) : reconnectAttemptRef.current >= MAX_RECONNECT_ATTEMPTS ? (
            <>
              <div className="w-10 h-10 rounded-full bg-red-500/10 flex items-center justify-center">
                <span className="text-red-400 text-lg">✕</span>
              </div>
              <span className="text-sm text-gray-300 font-medium">Connection lost</span>
              <span className="text-xs text-gray-500 max-w-sm text-center">
                Could not reach the sandbox after {MAX_RECONNECT_ATTEMPTS} attempts.
                The sandbox may still be starting up.
              </span>
              <button
                onClick={() => { reconnectAttemptRef.current = 0; connect(); }}
                className="mt-2 px-4 py-1.5 rounded-md text-xs font-medium bg-blue-500/20 text-blue-300 hover:bg-blue-500/30 transition-colors"
              >
                Retry Connection
              </button>
            </>
          ) : (
            <>
              <div className="w-10 h-10 rounded-full border-2 border-gray-600/30 border-t-gray-400 animate-spin" />
              <span className="text-sm text-gray-300 font-medium">Waiting for sandbox…</span>
              {disconnectReason && (
                <span className="max-w-sm text-center text-xs text-amber-400/80">
                  {disconnectReason}
                </span>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}

export default VncView;
