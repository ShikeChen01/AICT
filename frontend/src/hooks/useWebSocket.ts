/**
 * useWebSocket Hook
 * Manages WebSocket connection and event handling
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { createWebSocketClient, getAuthToken, WebSocketClient } from '../api/client';
import type { WSEvent, WSEventType } from '../types';

interface UseWebSocketOptions {
  autoConnect?: boolean;
}

interface UseWebSocketReturn {
  isConnected: boolean;
  connect: () => void;
  disconnect: () => void;
  subscribe: <T>(eventType: WSEventType, handler: (data: T) => void) => () => void;
}

export function useWebSocket(
  projectId: string | null,
  options: UseWebSocketOptions = {}
): UseWebSocketReturn {
  const { autoConnect = true } = options;
  const token = getAuthToken();
  const clientRef = useRef<WebSocketClient | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  // Initialize client only when projectId and token are available; reconnect when token appears
  useEffect(() => {
    if (!projectId || !token) {
      clientRef.current?.disconnect();
      clientRef.current = null;
      setIsConnected(false); // eslint-disable-line react-hooks/set-state-in-effect
      return;
    }

    const client = createWebSocketClient(projectId);
    clientRef.current = client;

    // Track connection state
    const unsubscribe = client.subscribe(() => {
      setIsConnected(client.isConnected);
    });

    let checkConnection: ReturnType<typeof setInterval> | null = null;
    let checkTimeout: ReturnType<typeof setTimeout> | null = null;

    if (autoConnect) {
      client.connect();
      checkConnection = setInterval(() => {
        setIsConnected(client.isConnected);
        if (client.isConnected && checkConnection !== null) {
          clearInterval(checkConnection);
          checkConnection = null;
        }
      }, 100);
      checkTimeout = setTimeout(() => {
        if (checkConnection !== null) {
          clearInterval(checkConnection);
          checkConnection = null;
        }
      }, 10000);
    }

    return () => {
      if (checkConnection !== null) clearInterval(checkConnection);
      if (checkTimeout !== null) clearTimeout(checkTimeout);
      unsubscribe();
      client.disconnect();
      clientRef.current = null;
    };
  }, [projectId, token, autoConnect]);

  const connect = useCallback(() => {
    clientRef.current?.connect();
  }, []);

  const disconnect = useCallback(() => {
    clientRef.current?.disconnect();
    setIsConnected(false);
  }, []);

  const subscribe = useCallback(
    <T>(eventType: WSEventType, handler: (data: T) => void) => {
      if (!clientRef.current) {
        return () => {};
      }

      return clientRef.current.subscribe((event: WSEvent) => {
        if (event.type === eventType) {
          handler(event.data as T);
        }
      });
    },
    []
  );

  return {
    isConnected,
    connect,
    disconnect,
    subscribe,
  };
}

export default useWebSocket;
