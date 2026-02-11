/**
 * useWebSocket Hook
 * Manages WebSocket connection and event handling
 */

import { useEffect, useRef, useState, useCallback } from 'react';
import { createWebSocketClient, WebSocketClient } from '../api/client';
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
  const clientRef = useRef<WebSocketClient | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  // Initialize client
  useEffect(() => {
    if (!projectId) return;

    const client = createWebSocketClient(projectId);
    clientRef.current = client;

    // Track connection state
    const unsubscribe = client.subscribe(() => {
      // Connection state is managed internally by the client
      setIsConnected(client.isConnected);
    });

    if (autoConnect) {
      client.connect();
      // Check connection after a short delay
      const checkConnection = setInterval(() => {
        setIsConnected(client.isConnected);
        if (client.isConnected) {
          clearInterval(checkConnection);
        }
      }, 100);

      // Clear interval after 10 seconds max
      setTimeout(() => clearInterval(checkConnection), 10000);
    }

    return () => {
      unsubscribe();
      client.disconnect();
      clientRef.current = null;
    };
  }, [projectId, autoConnect]);

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
