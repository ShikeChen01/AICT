import React, { useEffect, useRef, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import { Provider } from 'react-redux';
import { store, type RootState } from './store/store';
import { useAppSelector, useAppDispatch } from './store/hooks';
import { loadEntities } from './store/slices/entitiesSlice';
import { loadCanvas } from './store/slices/canvasSlice';
import { setEditPopover, setContextMenuWithPosition } from './store/slices/uiSlice';
import { ErrorBoundary } from './components/shared/ErrorBoundary';
import { selectStateForSave } from './store/selectors/entitySelectors';
import { createRpcClient } from './rpcClient/rpcClient';
import { Toolbar } from './components/Toolbar/Toolbar';
import { CanvasContainer } from './components/Canvas/CanvasContainer';
import { Breadcrumb } from './components/Canvas/Breadcrumb';
import { BucketCreationModal } from './components/popovers/BucketCreationModal';
import { EditPopover } from './components/popovers/EditPopover';
import { ContextMenu } from './components/popovers/ContextMenu';
import { AgentWindow } from './components/agent/AgentWindow';
import type { MessageChannelApi } from './rpcClient/messageChannel';
import type { CanvasLayout } from '../shared/types/rpc';
import './theme.css';

const layoutStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'row',
  width: '100vw',
  height: '100vh',
  margin: 0,
  padding: 0,
  boxSizing: 'border-box',
  background: 'var(--color-background)',
  color: 'var(--color-foreground)',
};
const mainStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  height: '100%',
  display: 'flex',
  flexDirection: 'column',
};

let saveTimeout: ReturnType<typeof setTimeout> | null = null;
const SAVE_DEBOUNCE_MS = 800;

function getStateForSave(state: RootState): { entities: ReturnType<typeof selectStateForSave>['entities']; canvas: CanvasLayout } {
  const saved = selectStateForSave(state);
  return {
    entities: saved.entities,
    canvas: saved.canvas,
  };
}

function AppContent({ getApi }: { getApi: () => MessageChannelApi }) {
  const clientRef = useRef<ReturnType<typeof createRpcClient> | null>(null);
  const getApiRef = useRef(getApi);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const dispatch = useAppDispatch();

  useEffect(() => {
    getApiRef.current = getApi;
    clientRef.current = createRpcClient(() => getApiRef.current());
    const client = clientRef.current;
    client
      .loadWorkspaceState()
      .then((result) => {
        dispatch(loadEntities(result.entities));
        if (result.canvas) {
          const nodePositions: Record<string, { x: number; y: number }> = {};
          const nodeSizes: Record<string, { width: number; height: number }> = {};
          for (const n of result.canvas.nodes ?? []) {
            nodePositions[n.id] = n.position;
            if (n.size) nodeSizes[n.id] = n.size;
          }
          const edges = (result.canvas.edges ?? []).map((e) => ({
            id: e.id,
            nodes: [e.source, e.target] as [string, string],
            type: 'dependency' as const,
            data: {
              dependencyType: 'depends_on' as const,
              hasApiContract: false,
            },
          }));
          dispatch(
            loadCanvas({
              nodePositions,
              nodeSizes,
              edges,
              viewport: result.canvas.viewport,
            })
          );
        }
        setLoading(false);
      })
      .catch((err) => {
        console.error('Failed to load workspace state', err);
        setError('Failed to load workspace');
        setLoading(false);
      });
    return () => {
      client.dispose();
      clientRef.current = null;
    };
  }, [getApi, dispatch]);

  const scopeEntityId = useAppSelector((s) => s.ui.scopeEntityId);
  useEffect(() => {
    (window as unknown as { __scopeEntityId: string | null }).__scopeEntityId = scopeEntityId;
  }, [scopeEntityId]);

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        dispatch(setEditPopover(null));
        dispatch(setContextMenuWithPosition(null));
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [dispatch]);

  const triggerSave = useCallback(() => {
    if (!clientRef.current) return;
    if (saveTimeout) clearTimeout(saveTimeout);
    saveTimeout = setTimeout(() => {
      saveTimeout = null;
      const state = store.getState();
      const { entities, canvas } = getStateForSave(state);
      clientRef.current!.saveWorkspaceState({ entities, canvas }).catch((err) => {
        console.error('Failed to save', err);
      });
    }, SAVE_DEBOUNCE_MS);
  }, []);

  useEffect(() => {
    const unsub = store.subscribe(() => triggerSave());
    return unsub;
  }, [triggerSave]);

  if (loading) {
    return (
      <div
        style={{
          ...layoutStyle,
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            fontSize: 'var(--font-size-lg)',
            color: 'var(--color-description)',
          }}
        >
          Loading workspace...
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          ...layoutStyle,
          alignItems: 'center',
          justifyContent: 'center',
          flexDirection: 'column',
          gap: 'var(--spacing-lg)',
        }}
      >
        <div
          style={{
            fontSize: 'var(--font-size-lg)',
            color: 'var(--color-error)',
          }}
        >
          {error}
        </div>
        <button
          onClick={() => {
            setError(null);
            setLoading(true);
            if (clientRef.current) {
              clientRef.current
                .loadWorkspaceState()
                .then((result) => {
                  dispatch(loadEntities(result.entities));
                  if (result.canvas) {
                    const nodePositions: Record<string, { x: number; y: number }> = {};
                    for (const n of result.canvas.nodes ?? []) {
                      nodePositions[n.id] = n.position;
                    }
                    const edges = (result.canvas.edges ?? []).map((e) => ({
                      id: e.id,
                      nodes: [e.source, e.target] as [string, string],
                      type: 'dependency' as const,
                      data: { dependencyType: 'depends_on' as const, hasApiContract: false },
                    }));
                    dispatch(loadCanvas({ nodePositions, edges, viewport: result.canvas.viewport }));
                  }
                  setLoading(false);
                })
                .catch((err) => {
                  console.error('Failed to load workspace state', err);
                  setError('Failed to load workspace');
                  setLoading(false);
                });
            }
          }}
          style={{
            padding: 'var(--spacing-sm) var(--spacing-lg)',
            background: 'var(--color-button-background)',
            color: 'var(--color-button-foreground)',
            border: 'none',
            borderRadius: 'var(--radius-md)',
            cursor: 'pointer',
            fontSize: 'var(--font-size-md)',
          }}
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div style={layoutStyle}>
      <Toolbar />
      <main style={mainStyle}>
        <div
          style={{
            padding: 'var(--spacing-sm) var(--spacing-md)',
            borderBottom: '1px solid var(--color-widget-border)',
            background: 'var(--color-sidebar-background)',
            flexShrink: 0,
          }}
        >
          <Breadcrumb />
        </div>
        <div style={{ flex: 1, minHeight: 0, position: 'relative' }}>
          <CanvasContainer />
        </div>
      </main>
      <BucketCreationModal />
      <ContextMenu />
      <EditPopoverWrapper />
      <AgentWindow />
    </div>
  );
}

function EditPopoverWrapper() {
  const editEntityId = useAppSelector((s) => s.ui.editPopoverEntityId);
  const editPosition = useAppSelector((s) => s.ui.editPopoverPosition);
  const dispatch = useAppDispatch();

  if (!editEntityId || !editPosition) return null;

  return (
    <EditPopover
      entityId={editEntityId}
      x={editPosition.x}
      y={editPosition.y}
      onClose={() => dispatch(setEditPopover(null))}
    />
  );
}

export function App({ getApi }: { getApi: () => MessageChannelApi }) {
  return <AppContent getApi={getApi} />;
}

export function mountApp(getApi: () => MessageChannelApi) {
  const root = document.getElementById('root');
  if (!root) throw new Error('Root element not found');
  const reactRoot = createRoot(root);
  reactRoot.render(
    <Provider store={store}>
      <ErrorBoundary>
        <App getApi={getApi} />
      </ErrorBoundary>
    </Provider>
  );
}
