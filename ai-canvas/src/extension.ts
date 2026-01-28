import * as vscode from "vscode";
import { createRpcServer } from "src/extension/rpc/rpcServer";
import { createWebviewTransport } from "src/extension/rpc/rpcTransport";
import { registerCoreHandlers } from "src/extension/rpc/rpcHandlers";
import { PolicyEngine } from "src/extension/policy/policyEngine";
import { PatchEngine } from "src/extension/patch/patchEngine";
import { repoIndexer } from "src/extension/repoIndex/repoIndexer";
import { runCommand } from "src/extension/runner/commandRunner";
import { workspaceStore } from "src/extension/storage/workspaceStore";
import { cacheStore } from "src/extension/storage/cacheStore";
import { CloudGateway } from "src/extension/cloud/gatewayClient";

export function activate(context: vscode.ExtensionContext) {
  const disposable = vscode.commands.registerCommand("ai-canvas.openCanvas", () => {
    const panel = vscode.window.createWebviewPanel(
      "aiCanvas",
      "AI Canvas",
      vscode.ViewColumn.One,
      { enableScripts: true },
    );

    const transport = createWebviewTransport(panel.webview);
    const policy = new PolicyEngine();
    const runner = { runCommand };
    const patchEngine = new PatchEngine({ runner, policy });
    const cloud = new CloudGateway();

    const handlers = registerCoreHandlers({
      workspaceRoot: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? process.cwd(),
      policy,
      runner,
      patchEngine,
      repoIndexer,
      workspaceStore,
      cacheStore,
      cloud,
    });

    const server = createRpcServer({
      transport,
      handlers,
    });

    server.start();

    panel.onDidDispose(() => {
      server.dispose();
    });

    panel.webview.html = getWebviewHtml();
  });

  context.subscriptions.push(disposable);
}

export function deactivate() {}

function getWebviewHtml(): string {
  return `<!doctype html>
  <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <meta name="viewport" content="width=device-width, initial-scale=1.0" />
      <title>AI Canvas</title>
      <style>
        body { font-family: sans-serif; margin: 0; padding: 24px; }
        .card { border: 1px solid #ddd; border-radius: 8px; padding: 16px; max-width: 640px; }
        h1 { margin: 0 0 8px; }
        p { margin: 0; color: #444; }
      </style>
    </head>
    <body>
      <div class="card">
        <h1>AI Canvas</h1>
        <p>The command is wired. Next step is to mount the webview UI here.</p>
      </div>
    </body>
  </html>`;
}
