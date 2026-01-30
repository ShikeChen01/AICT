import * as vscode from 'vscode';
import { createWebviewTransport } from './extension/rpc/rpcTransport';
import { createRpcServer } from './extension/rpc/rpcServer';
import { registerMvp0Handlers } from './extension/rpc/rpcHandlers';

export function activate(context: vscode.ExtensionContext) {
  context.subscriptions.push(
    vscode.commands.registerCommand('aiCanvas.open', () => {
      openCanvas(context);
    })
  );
}

export function deactivate() {}

function getWorkspaceRoot(): string {
  const folder = vscode.workspace.workspaceFolders?.[0];
  if (!folder) return '';
  return folder.uri.fsPath;
}

function openCanvas(context: vscode.ExtensionContext) {
  const panel = vscode.window.createWebviewPanel(
    'aiCanvas',
    'AI Canvas',
    vscode.ViewColumn.One,
    {
      enableScripts: true,
      retainContextWhenHidden: true,
      localResourceRoots: [vscode.Uri.joinPath(context.extensionUri, 'dist')]
    }
  );

  const scriptUri = panel.webview.asWebviewUri(
    vscode.Uri.joinPath(context.extensionUri, 'dist', 'webview.js')
  );
  const cspSource = panel.webview.cspSource;

  panel.webview.html = getWebviewContent(scriptUri, cspSource);

  const transport = createWebviewTransport(panel.webview);
  const handlers = registerMvp0Handlers({ getWorkspaceRoot });
  const server = createRpcServer({ transport, handlers });
  server.start();

  panel.onDidDispose(() => {
    server.stop();
  });
}

function getWebviewContent(scriptUri: vscode.Uri, cspSource: string): string {
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src ${cspSource}; style-src ${cspSource} 'unsafe-inline';">
  <title>AI Canvas</title>
  <style>
    body { margin: 0; padding: 0; font-family: var(--vscode-font-family); background: var(--vscode-editor-background, #1e1e1e); }
    #root { width: 100vw; height: 100vh; }
  </style>
</head>
<body>
  <div id="root"></div>
  <script src="${scriptUri}"></script>
</body>
</html>`;
}
