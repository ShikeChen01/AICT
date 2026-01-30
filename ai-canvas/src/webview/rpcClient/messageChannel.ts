/**
 * Typed postMessage channel for webview <-> extension host.
 * Uses acquireVsCodeApi() in the webview; host uses webview.postMessage.
 */

const RPC_MESSAGE_KIND = 'aict-rpc';

export interface RpcMessage {
  kind: typeof RPC_MESSAGE_KIND;
  payload: unknown;
}

export interface MessageChannelApi {
  postMessage(msg: unknown): void;
  getState(): unknown;
  setState(state: unknown): void;
}

export interface CreateMessageChannelOptions {
  getApi: () => MessageChannelApi;
  onMessage: (payload: unknown) => void;
}

/**
 * Create a channel that sends messages via postMessage and forwards received messages.
 * Call this once with the result of acquireVsCodeApi() and a callback for incoming payloads.
 */
export function createMessageChannel(options: CreateMessageChannelOptions): {
  send: (payload: unknown) => void;
} {
  const { getApi, onMessage } = options;
  const api = getApi();

  const listener = (event: MessageEvent) => {
    const data = event.data;
    if (data?.kind === RPC_MESSAGE_KIND && data.payload !== undefined) {
      onMessage(data.payload);
    }
  };
  window.addEventListener('message', listener);

  return {
    send(payload: unknown): void {
      getApi().postMessage({ kind: RPC_MESSAGE_KIND, payload });
    }
  };
}
