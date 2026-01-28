import React, { useMemo } from "react";
import { CanvasView } from "src/webview/canvas/CanvasView";
import { InspectorPanel } from "src/webview/inspector/InspectorPanel";
import { AgentPanel } from "src/webview/agentPanel/AgentPanel";
import { useAppStore } from "src/webview/store/appStore";

const buildStyles = () => ({
  root: {
    fontFamily: "\"DM Sans\", \"Segoe UI\", sans-serif",
    color: "#0f172a",
    background: "radial-gradient(circle at top, #f7f4ee 0%, #f2e9dd 35%, #e7dccb 100%)",
    minHeight: "100vh",
    display: "grid",
    gridTemplateRows: "56px 1fr",
  } as React.CSSProperties,
  header: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    padding: "0 20px",
    background: "rgba(255,255,255,0.6)",
    backdropFilter: "blur(12px)",
    borderBottom: "1px solid rgba(15,23,42,0.1)",
  } as React.CSSProperties,
  layout: {
    display: "grid",
    gridTemplateColumns: "minmax(0, 1fr) 360px",
    gap: "16px",
    padding: "16px",
  } as React.CSSProperties,
  main: {
    display: "grid",
    gridTemplateRows: "1fr",
    background: "rgba(255,255,255,0.4)",
    borderRadius: "16px",
    border: "1px solid rgba(15,23,42,0.08)",
    overflow: "hidden",
  } as React.CSSProperties,
  side: {
    display: "grid",
    gridTemplateRows: "1fr 1fr",
    gap: "16px",
  } as React.CSSProperties,
  panel: {
    background: "rgba(255,255,255,0.85)",
    borderRadius: "16px",
    border: "1px solid rgba(15,23,42,0.08)",
    overflow: "hidden",
  } as React.CSSProperties,
  brand: {
    display: "flex",
    alignItems: "center",
    gap: "12px",
    fontWeight: 700,
    letterSpacing: "0.04em",
    textTransform: "uppercase",
  } as React.CSSProperties,
  badge: {
    fontSize: "12px",
    padding: "4px 10px",
    background: "#0f172a",
    color: "#f8fafc",
    borderRadius: "999px",
  } as React.CSSProperties,
  status: {
    fontSize: "13px",
    color: "#475569",
  } as React.CSSProperties,
});

export const App: React.FC = () => {
  const styles = useMemo(buildStyles, []);
  const selection = useAppStore((state) => state.selectedEntityId);

  return (
    <div style={styles.root}>
      <style>{`
        * { box-sizing: border-box; }
        body { margin: 0; }
        input, textarea, select, button { font: inherit; }
        .panel-scroll { overflow: auto; height: 100%; }
      `}</style>
      <header style={styles.header}>
        <div style={styles.brand}>
          <span style={styles.badge}>AICT</span>
          <span>Canvas</span>
        </div>
        <div style={styles.status}>
          {selection ? `Selected: ${selection}` : "No selection"}
        </div>
      </header>
      <div style={styles.layout}>
        <main style={styles.main}>
          <CanvasView />
        </main>
        <aside style={styles.side}>
          <div style={styles.panel}>
            <InspectorPanel />
          </div>
          <div style={styles.panel}>
            <AgentPanel />
          </div>
        </aside>
      </div>
    </div>
  );
};
