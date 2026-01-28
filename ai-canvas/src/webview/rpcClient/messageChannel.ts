import type { RpcEvent, RpcRequest, RpcResponse } from "src/shared/types";

export type MessageChannel = {
  send: (message: RpcRequest | RpcResponse | RpcEvent) => void;
  onMessage: (handler: (message: unknown) => void) => () => void;
};

export const createMessageChannel = (): MessageChannel => {
  const vscode = (window as unknown as { acquireVsCodeApi?: () => { postMessage: (msg: unknown) => void } })
    .acquireVsCodeApi?.();

  return {
    send: (message) => {
      vscode?.postMessage(message);
    },
    onMessage: (handler) => {
      const listener = (event: MessageEvent) => handler(event.data);
      window.addEventListener("message", listener);
      return () => window.removeEventListener("message", listener);
    },
  };
};
