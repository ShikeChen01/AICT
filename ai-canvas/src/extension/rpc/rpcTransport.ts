import type * as vscode from "vscode";
import type { RpcEvent, RpcRequest, RpcResponse } from "src/shared/types/rpc";

// Webview transport adapter: wraps postMessage and message listener into a typed interface.
export type RpcTransportMessage = RpcRequest | RpcResponse | RpcEvent;

export type RpcTransport = {
  send: (message: RpcTransportMessage) => void;
  onMessage: (handler: (message: unknown) => void) => vscode.Disposable;
  dispose: () => void;
};

export const createWebviewTransport = (webview: vscode.Webview): RpcTransport => {
  let disposed = false;

  return {
    send: (message) => {
      if (disposed) {
        return;
      }
      void webview.postMessage(message);
    },
    onMessage: (handler) => webview.onDidReceiveMessage(handler),
    dispose: () => {
      disposed = true;
    },
  };
};
