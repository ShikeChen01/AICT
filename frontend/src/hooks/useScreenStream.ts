/**
 * useScreenStream — binary WebSocket hook for live sandbox screen streaming.
 *
 * Opens a WS connection to /ws/screen?token=...&sandbox_id=... when sandboxId
 * is set. Each binary message (JPEG frame) is converted to an object URL for
 * rendering in an <img> tag. Previous object URLs are revoked to prevent leaks.
 *
 * Features:
 *   - Auto-reconnect with exponential backoff on disconnect
 *   - Periodic keepalive pings to prevent Cloud Run idle-timeout
 *
 * Returns { frameUrl, isConnected }.
 * Setting sandboxId to null disconnects the stream (natural unsubscribe).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { getAuthToken, getSandboxWsBase } from '../api/client';

interface ScreenStreamState {
  frameUrl: string | null;
  isConnected: boolean;
}

/** Max reconnect attempts before giving up */
const MAX_RECONNECT_ATTEMPTS = 10;
/** Base delay between reconnect attempts (ms). Doubles each attempt, max 30s. */
const BASE_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 30_000;
/** Keepalive ping interval (ms) — keeps Cloud Run from closing idle connections */
const KEEPALIVE_INTERVAL_MS = 30_000;

export function useScreenStream(sandboxId: string | null): ScreenStreamState {
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const prevUrlRef = useRef<string | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const keepaliveTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const shouldStopRef = useRef(false);

  const cleanup = useCallback(() => {
    shouldStopRef.current = true;
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (keepaliveTimerRef.current !== null) {
      clearInterval(keepaliveTimerRef.current);
      keepaliveTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    if (prevUrlRef.current) {
      URL.revokeObjectURL(prevUrlRef.current);
      prevUrlRef.current = null;
    }
    setFrameUrl(null);
    setIsConnected(false);
  }, []);

  const connect = useCallback((sid: string) => {
    if (shouldStopRef.current) return;

    const token = getAuthToken();
    if (!token) return;

    const wsBase = getSandboxWsBase();
    const url = `${wsBase}/screen?token=${encodeURIComponent(token)}&sandbox_id=${encodeURIComponent(sid)}`;

    const ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
      reconnectAttemptRef.current = 0; // Reset backoff on success

      // Start keepalive pings — send a JSON ping every 30s to keep
      // Cloud Run's HTTP/2 proxy from closing the connection for idleness.
      if (keepaliveTimerRef.current !== null) {
        clearInterval(keepaliveTimerRef.current);
      }
      keepaliveTimerRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ type: 'ping' }));
        }
      }, KEEPALIVE_INTERVAL_MS);
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        const blob = new Blob([event.data], { type: 'image/jpeg' });
        const newUrl = URL.createObjectURL(blob);

        // Revoke the previous URL to prevent memory leaks
        if (prevUrlRef.current) {
          URL.revokeObjectURL(prevUrlRef.current);
        }
        prevUrlRef.current = newUrl;
        setFrameUrl(newUrl);
      }
    };

    ws.onclose = () => {
      setIsConnected(false);
      wsRef.current = null;
      if (keepaliveTimerRef.current !== null) {
        clearInterval(keepaliveTimerRef.current);
        keepaliveTimerRef.current = null;
      }

      // Auto-reconnect with exponential backoff
      if (!shouldStopRef.current && reconnectAttemptRef.current < MAX_RECONNECT_ATTEMPTS) {
        const attempt = reconnectAttemptRef.current;
        const delay = Math.min(
          BASE_RECONNECT_DELAY_MS * Math.pow(2, attempt),
          MAX_RECONNECT_DELAY_MS,
        );
        reconnectAttemptRef.current = attempt + 1;
        console.log(
          `[ScreenStream] Reconnecting in ${delay}ms (attempt ${attempt + 1}/${MAX_RECONNECT_ATTEMPTS})`,
        );
        reconnectTimerRef.current = setTimeout(() => {
          reconnectTimerRef.current = null;
          connect(sid); // eslint-disable-line react-hooks/immutability
        }, delay);
      }
    };

    ws.onerror = () => {
      // onclose will be called after onerror, which handles reconnect
      setIsConnected(false);
    };
  }, []);

  useEffect(() => {
    if (!sandboxId) {
      cleanup();
      return;
    }

    // Reset state for new sandbox
    shouldStopRef.current = false;
    reconnectAttemptRef.current = 0;
    if (reconnectTimerRef.current !== null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (keepaliveTimerRef.current !== null) {
      clearInterval(keepaliveTimerRef.current);
      keepaliveTimerRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    connect(sandboxId);

    return cleanup;
  }, [sandboxId, cleanup, connect]);

  return { frameUrl, isConnected };
}
