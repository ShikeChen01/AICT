import React, { useEffect, useRef, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import { CanvasView } from './canvas/CanvasView';
import { InspectorPanel } from './inspector/InspectorPanel';
import { Toolbar } from './Toolbar';
import { useAppStore } from './store/appStore';
import { useCanvasStore } from './store/canvasStore';
import { createRpcClient } from './rpcClient/rpcClient';
import { getStateForSave } from './store/actions';
import type { MessageChannelApi } from './rpcClient/messageChannel';

const layoutStyle: React.CSSProperties = {
  display: 'flex',
  flexDirection: 'row',
  width: '100vw',
  height: '100vh',
  margin: 0,
  padding: 0,
  boxSizing: 'border-box'
};
const mainStyle: React.CSSProperties = {
  flex: 1,
  minWidth: 0,
  height: '100%'
};

let saveTimeout: ReturnType<typeof setTimeout> | null = null;
const SAVE_DEBOUNCE_MS = 800;

export function App({ getApi }: { getApi: () => MessageChannelApi }) {
  const clientRef = useRef<ReturnType<typeof createRpcClient> | null>(null);
  const getApiRef = useRef(getApi);

  useEffect(() => {
    getApiRef.current = getApi;
    clientRef.current = createRpcClient(() => getApiRef.current());
    const client = clientRef.current;
    client
      .loadWorkspaceState()
      .then((state) => {
        useAppStore.getState().loadState(state);
        useCanvasStore.getState().syncFromEntities(state.entities, state.canvas);
      })
      .catch((err) => console.error('Failed to load workspace state', err));
    return () => {
      client.dispose();
      clientRef.current = null;
    };
  }, [getApi]);

  const triggerSave = useCallback(() => {
    if (!clientRef.current) return;
    if (saveTimeout) clearTimeout(saveTimeout);
    saveTimeout = setTimeout(() => {
      saveTimeout = null;
      const { entities, canvas } = getStateForSave();
      clientRef.current!.saveWorkspaceState({ entities, canvas }).catch((err) => {
        console.error('Failed to save', err);
      });
    }, SAVE_DEBOUNCE_MS);
  }, []);

  useEffect(() => {
    const unsub = useAppStore.subscribe(() => triggerSave());
    return unsub;
  }, [triggerSave]);

  useEffect(() => {
    const unsub = useCanvasStore.subscribe(() => triggerSave());
    return unsub;
  }, [triggerSave]);

  return (
    <div style={layoutStyle}>
      <main style={mainStyle}>
        <Toolbar />
        <div style={{ flex: 1, minHeight: 0, height: 'calc(100vh - 45px)' }}>
          <CanvasView />
        </div>
      </main>
      <InspectorPanel />
    </div>
  );
}

export function mountApp(getApi: () => MessageChannelApi) {
  const root = document.getElementById('root');
  if (!root) throw new Error('Root element not found');
  const reactRoot = createRoot(root);
  reactRoot.render(<App getApi={getApi} />);
}
