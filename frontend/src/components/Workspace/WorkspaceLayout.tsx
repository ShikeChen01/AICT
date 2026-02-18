/**
 * WorkspaceLayout — three-column layout: Sidebar | Main | Agents panel.
 */

import { Sidebar } from './Sidebar';
import { ConnectionStatus } from './ConnectionStatus';

interface WorkspaceLayoutProps {
  activeProjectId: string;
  onProjectChange?: (projectId: string) => void;
  main: React.ReactNode;
  agentsPanel?: React.ReactNode;
  isWsConnected?: boolean;
}

export function WorkspaceLayout({
  activeProjectId,
  onProjectChange,
  main,
  agentsPanel,
  isWsConnected = false,
}: WorkspaceLayoutProps) {
  return (
    <div className="flex h-screen overflow-x-hidden bg-gray-100">
      <Sidebar activeProjectId={activeProjectId} onProjectChange={onProjectChange} />
      <main className="flex-1 min-w-0 overflow-hidden flex flex-col">
        {main}
      </main>
      {agentsPanel != null && (
        <aside className="w-80 min-w-0 border-l border-gray-200 bg-white overflow-hidden flex flex-col">
          {agentsPanel}
        </aside>
      )}
      <ConnectionStatus isConnected={isWsConnected} />
    </div>
  );
}

export default WorkspaceLayout;
