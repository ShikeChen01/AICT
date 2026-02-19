/**
 * WorkspaceLayout — three-column layout: Sidebar | Main | Agents panel.
 */

import { useEffect, useRef, useState } from 'react';
import { Sidebar } from './Sidebar';
import { ConnectionStatus } from './ConnectionStatus';

interface WorkspaceLayoutProps {
  activeProjectId: string;
  onProjectChange?: (projectId: string) => void;
  main: React.ReactNode;
  monitoringPanel?: React.ReactNode;
  isWsConnected?: boolean;
}

export function WorkspaceLayout({
  activeProjectId,
  onProjectChange,
  main,
  monitoringPanel,
  isWsConnected = false,
}: WorkspaceLayoutProps) {
  const [monitoringWidth, setMonitoringWidth] = useState(384);
  const [isResizingMonitoring, setIsResizingMonitoring] = useState(false);
  const mainRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!isResizingMonitoring || monitoringPanel == null) return;
    const handleMouseMove = (event: MouseEvent) => {
      const rect = mainRef.current?.getBoundingClientRect();
      if (!rect) return;
      const minWidth = 320;
      const maxWidth = Math.max(minWidth, rect.width * 0.6);
      const nextWidth = rect.right - event.clientX;
      const clamped = Math.min(Math.max(nextWidth, minWidth), maxWidth);
      setMonitoringWidth(clamped);
    };
    const handleMouseUp = () => setIsResizingMonitoring(false);

    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
    document.body.style.userSelect = 'none';
    document.body.style.cursor = 'col-resize';

    return () => {
      window.removeEventListener('mousemove', handleMouseMove);
      window.removeEventListener('mouseup', handleMouseUp);
      document.body.style.userSelect = '';
      document.body.style.cursor = '';
    };
  }, [isResizingMonitoring, monitoringPanel]);

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--app-bg)]">
      <Sidebar activeProjectId={activeProjectId} onProjectChange={onProjectChange} />
      <main ref={mainRef} className="flex min-w-0 flex-1 gap-3 overflow-hidden p-4">
        <section className="min-w-0 flex-1 overflow-hidden">{main}</section>
        {monitoringPanel != null && (
          <>
            <div
              role="separator"
              aria-orientation="vertical"
              aria-label="Resize monitoring panel"
              onMouseDown={(event) => {
                event.preventDefault();
                setIsResizingMonitoring(true);
              }}
              className="w-1.5 cursor-col-resize rounded bg-transparent hover:bg-[var(--border-color)] active:bg-[var(--color-primary)]/40"
            />
            <aside
              className="min-w-0 overflow-hidden"
              style={{ width: `${monitoringWidth}px` }}
            >
              {monitoringPanel}
            </aside>
          </>
        )}
      </main>
      <div className="pointer-events-none">
        <ConnectionStatus isConnected={isWsConnected} />
      </div>
    </div>
  );
}

export default WorkspaceLayout;
