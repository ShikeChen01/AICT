/**
 * useScreenStream — binary WebSocket hook for live sandbox screen streaming.
 *
 * Opens a WS connection to /ws/screen?token=...&sandbox_id=... when sandboxId
 * is set. Each binary message (JPEG frame) is converted to an object URL for
 * rendering in an <img> tag. Previous object URLs are revoked to prevent leaks.
 *
 * Returns { frameUrl, isConnected }.
 * Setting sandboxId to null disconnects the stream (natural unsubscribe).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { getAuthToken } from '../api/client';

interface ScreenStreamState {
  frameUrl: string | null;
  isConnected: boolean;
}

export function useScreenStream(sandboxId: string | null): ScreenStreamState {
  const [frameUrl, setFrameUrl] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const prevUrlRef = useRef<string | null>(null);

  const cleanup = useCallback(() => {
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

  useEffect(() => {
    if (!sandboxId) {
      cleanup();
      return;
    }

    const token = getAuthToken();
    if (!token) {
      return;
    }

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = `${protocol}//${window.location.host}/ws/screen?token=${encodeURIComponent(token)}&sandbox_id=${encodeURIComponent(sandboxId)}`;

    const ws = new WebSocket(url);
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;

    ws.onopen = () => {
      setIsConnected(true);
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
    };

    ws.onerror = () => {
      setIsConnected(false);
    };

    return cleanup;
  }, [sandboxId, cleanup]);

  return { frameUrl, isConnected };
}
