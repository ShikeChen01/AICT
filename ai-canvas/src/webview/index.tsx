/**
 * Webview entry. VS Code injects acquireVsCodeApi in the webview context.
 */
import { mountApp } from './App';

interface VsCodeWebviewGlobal {
  acquireVsCodeApi?: () => { postMessage: (m: unknown) => void; getState: () => unknown; setState: (s: unknown) => void };
}
function bootstrap() {
  const g = (typeof window !== 'undefined' ? window : {}) as VsCodeWebviewGlobal;
  const acquireVsCodeApi = g.acquireVsCodeApi;
  const root = document.getElementById('root');
  if (!acquireVsCodeApi) {
    if (root) root.innerHTML = '<div style="padding:20px;color:#f48771;">acquireVsCodeApi not available. Reload the webview.</div>';
    return;
  }
  try {
    const api = acquireVsCodeApi();
    mountApp(() => api);
  } catch (e) {
    if (root) root.innerHTML = `<div style="padding:20px;color:#f48771;">Failed to start: ${String(e)}</div>`;
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootstrap);
} else {
  bootstrap();
}
