import type { Webview } from 'vscode';
import type { RpcRequest, RpcResponse } from '../../shared/types/rpc';

export interface RpcTransport {
  send(response: RpcResponse): void;
  onRequest(cb: (request: RpcRequest) => void): () => void;
  dispose(): void;
}

const RPC_MESSAGE_KIND = 'aict-rpc';

export interface RpcMessage {
  kind: typeof RPC_MESSAGE_KIND;
  payload: RpcRequest | RpcResponse;
}

function isRpcMessage(msg: unknown): msg is RpcMessage {
  return (
    typeof msg === 'object' &&
    msg !== null &&
    (msg as RpcMessage).kind === RPC_MESSAGE_KIND &&
    'payload' in (msg as RpcMessage)
  );
}

/**
 * Wrap webview.postMessage and onDidReceiveMessage into a typed transport.
 * Assigns request ids on the client; host echoes id in response.
 */
export function createWebviewTransport(webview: Webview): RpcTransport {
  const listeners: Array<(request: RpcRequest) => void> = [];
  const messageListener = webview.onDidReceiveMessage((msg: unknown) => {
    if (!isRpcMessage(msg)) return;
    const payload = msg.payload;
    if ('method' in payload && payload.method) {
      listeners.forEach((cb) => cb(payload as RpcRequest));
    }
  });

  return {
    send(response: RpcResponse): void {
      webview.postMessage({
        kind: RPC_MESSAGE_KIND,
        payload: response
      } as RpcMessage);
    },
    onRequest(cb: (request: RpcRequest) => void): () => void {
      listeners.push(cb);
      return () => {
        const i = listeners.indexOf(cb);
        if (i >= 0) listeners.splice(i, 1);
      };
    },
    dispose(): void {
      messageListener.dispose();
      listeners.length = 0;
    }
  };
}
