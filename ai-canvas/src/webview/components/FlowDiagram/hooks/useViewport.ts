import { useCallback, useRef } from 'react';
import { useAppDispatch, useAppSelector } from '../../../store/hooks';
import { setViewport } from '../../../store/slices/canvasSlice';
import type { CommandRegistry } from '../../../commands/CommandRegistry';
import type { Position, Viewport } from '../core/types';

interface PanState {
  startViewport: Viewport;
  startMouse: Position;
  currentViewport: Viewport;
}

export function useViewport(commandRegistry: CommandRegistry) {
  const dispatch = useAppDispatch();
  const viewport = useAppSelector((s) => s.canvas.viewport);
  const panRef = useRef<PanState | null>(null);

  const startPan = useCallback((mouseScreen: Position) => {
    panRef.current = {
      startViewport: { ...viewport },
      startMouse: mouseScreen,
      currentViewport: { ...viewport },
    };
  }, [viewport]);

  const onPan = useCallback(
    (mouseScreen: Position) => {
      if (!panRef.current) return;
      const dx = mouseScreen.x - panRef.current.startMouse.x;
      const dy = mouseScreen.y - panRef.current.startMouse.y;
      const newViewport = {
        x: panRef.current.startViewport.x + dx,
        y: panRef.current.startViewport.y + dy,
        zoom: viewport.zoom,
      };
      panRef.current.currentViewport = newViewport;
      dispatch(setViewport(newViewport));
    },
    [viewport.zoom, dispatch]
  );

  const endPan = useCallback(() => {
    if (panRef.current) {
      const { startViewport, currentViewport } = panRef.current;
      if (
        startViewport.x !== currentViewport.x ||
        startViewport.y !== currentViewport.y
      ) {
        commandRegistry.execute({
          type: 'SET_VIEWPORT',
          payload: currentViewport,
        });
      }
    }
    panRef.current = null;
  }, [commandRegistry]);

  const onWheel = useCallback(
    (e: WheelEvent, containerRect: DOMRect) => {
      e.preventDefault();
      const zoomFactor = e.deltaY > 0 ? 0.9 : 1.1;
      const newZoom = Math.max(
        0.1,
        Math.min(3, viewport.zoom * zoomFactor)
      );
      const mouseX = e.clientX - containerRect.left;
      const mouseY = e.clientY - containerRect.top;
      const wx = (mouseX - viewport.x) / viewport.zoom;
      const wy = (mouseY - viewport.y) / viewport.zoom;
      const newX = mouseX - wx * newZoom;
      const newY = mouseY - wy * newZoom;
      commandRegistry.execute({
        type: 'SET_VIEWPORT',
        payload: { x: newX, y: newY, zoom: newZoom },
      });
    },
    [viewport, commandRegistry]
  );

  return {
    viewport,
    startPan,
    onPan,
    endPan,
    onWheel,
    isPanning: () => panRef.current !== null,
  };
}
