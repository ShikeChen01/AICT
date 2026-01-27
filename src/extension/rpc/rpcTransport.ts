import type * as vscode from "vscode";
import type { RpcEvent, RpcRequest, RpcResponse } from "../../shared/types/rpc";

export interface RpcTransport {
  send: (message: RpcResponse | RpcEvent) => void;
  onRequest: (handler: (req: RpcRequest) => void) => vscode.Disposable;
  dispose: () => void;
}

function isRpcRequest(message: unknown): message is RpcRequest {
  if (typeof message !== "object" || message === null) {
    return false;
  }
  const value = message as { id?: unknown; method?: unknown };
  return typeof value.id === "string" && typeof value.method === "string";
}

export function createWebviewTransport(webview: vscode.Webview): RpcTransport {
  const handlers = new Set<(req: RpcRequest) => void>();
  const disposable = webview.onDidReceiveMessage((message: unknown) => {
    if (!isRpcRequest(message)) {
      return;
    }
    for (const handler of handlers) {
      handler(message);
    }
  });

  return {
    send(message) {
      void webview.postMessage(message);
    },
    onRequest(handler) {
      handlers.add(handler);
      return {
        dispose: () => {
          handlers.delete(handler);
        },
      } as vscode.Disposable;
    },
    dispose() {
      disposable.dispose();
      handlers.clear();
    },
  };
}
