import { useEffect } from "react";
import { CanvasView } from "./canvas/CanvasView";
import { InspectorPanel } from "./inspector/InspectorPanel";
import { AgentPanel } from "./agentPanel/AgentPanel";
import { useAppStore } from "./store/appStore";
import { useCanvasStore } from "./store/canvasStore";
import type { Entity } from "../shared/types";

const sampleEntities: Entity[] = [
  {
    id: "bucket-1",
    type: "bucket",
    name: "Backend",
    purpose: "System boundary for core services",
    exports: ["Public API"],
    imports: [],
    deps: ["node", "postgres"],
    children: ["module-1"],
    size_hint: "l",
    status: "doing",
  },
  {
    id: "module-1",
    type: "module",
    name: "Users API",
    purpose: "REST endpoints for user data",
    exports: ["GET /users", "POST /users"],
    imports: ["db"],
    deps: ["zod"],
    children: ["block-1"],
    size_hint: "m",
    status: "todo",
  },
  {
    id: "block-1",
    type: "block",
    name: "users.ts",
    purpose: "Route handlers and validation",
    exports: ["registerRoutes"],
    imports: ["userService"],
    deps: [],
    children: [],
    path: "src/api/users.ts",
    tests: { block_test: "npm test -- users" },
    size_hint: "s",
    status: "review",
  },
];

export function App() {
  const panel = useAppStore((state) => state.panel);
  const setPanel = useAppStore((state) => state.setPanel);
  const entities = useAppStore((state) => state.entities);
  const setEntities = useAppStore((state) => state.setEntities);
  const selectEntity = useAppStore((state) => state.selectEntity);

  const nodes = useCanvasStore((state) => state.nodes);
  const edges = useCanvasStore((state) => state.edges);
  const selection = useCanvasStore((state) => state.selection);
  const setNodes = useCanvasStore((state) => state.setNodes);
  const setEdges = useCanvasStore((state) => state.setEdges);

  useEffect(() => {
    if (entities.length === 0) {
      setEntities(sampleEntities);
      selectEntity(sampleEntities[0]?.id);
    }
  }, [entities.length, selectEntity, setEntities]);

  useEffect(() => {
    if (nodes.length === 0) {
      setNodes([
        {
          id: "bucket-1",
          type: "bucket",
          position: { x: 60, y: 80 },
          data: { label: "Backend", description: "System boundary" },
        },
        {
          id: "module-1",
          type: "module",
          position: { x: 360, y: 120 },
          data: { label: "Users API", description: "REST endpoints" },
        },
        {
          id: "block-1",
          type: "block",
          position: { x: 660, y: 200 },
          data: { label: "users.ts", description: "Route handlers" },
        },
      ]);
    }
    if (edges.length === 0) {
      setEdges([
        { id: "bucket-module", source: "bucket-1", target: "module-1", type: "containment" },
        { id: "module-block", source: "module-1", target: "block-1", type: "containment" },
      ]);
    }
  }, [edges.length, nodes.length, setEdges, setNodes]);

  useEffect(() => {
    if (selection.nodes.length > 0) {
      selectEntity(selection.nodes[0]);
    }
  }, [selection.nodes, selectEntity]);

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <span className="brand-title">AICT Canvas</span>
          <span className="brand-subtitle">Prototype UI</span>
        </div>
        <div className="header-actions">
          <button
            type="button"
            className={panel === "inspector" ? "active" : ""}
            onClick={() => setPanel("inspector")}
          >
            Inspector
          </button>
          <button
            type="button"
            className={panel === "agent" ? "active" : ""}
            onClick={() => setPanel("agent")}
          >
            Agent
          </button>
        </div>
      </header>
      <div className="app-body">
        <main className="canvas-pane">
          <CanvasView />
        </main>
        <aside className="side-pane">{panel === "inspector" ? <InspectorPanel /> : <AgentPanel />}</aside>
      </div>
    </div>
  );
}
