export interface MessageChannel {
  postMessage: (message: unknown) => void;
  onMessage: (handler: (message: unknown) => void) => () => void;
}

export function createMessageChannel(): MessageChannel {
  const vscodeApi = (window as unknown as { acquireVsCodeApi?: () => { postMessage: (message: unknown) => void } })
    .acquireVsCodeApi?.();

  const postMessage = (message: unknown) => {
    if (vscodeApi) {
      vscodeApi.postMessage(message);
    } else {
      window.postMessage(message, "*");
    }
  };

  const onMessage = (handler: (message: unknown) => void) => {
    const listener = (event: MessageEvent) => {
      handler(event.data);
    };
    window.addEventListener("message", listener);
    return () => window.removeEventListener("message", listener);
  };

  return { postMessage, onMessage };
}
