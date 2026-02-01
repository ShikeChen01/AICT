import React, { useRef, useCallback } from 'react';
import Draggable from 'react-draggable';
import { useAppSelector, useAppDispatch } from '../../store/hooks';
import { setAgentPosition, toggleMinimize } from '../../store/slices/agentSlice';
import { AgentHeader } from './AgentHeader';
import { AgentChatHistory } from './AgentChatHistory';
import { AgentInput } from './AgentInput';
import { AgentStatusLine } from './AgentStatusLine';

const windowStyle: React.CSSProperties = {
  width: 380,
  height: 420,
  background: 'var(--color-sidebar-background)',
  border: '1px solid var(--color-widget-border)',
  borderRadius: 'var(--radius-lg)',
  boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
  display: 'flex',
  flexDirection: 'column',
  overflow: 'hidden',
};

const pillStyle: React.CSSProperties = {
  position: 'fixed',
  zIndex: 900,
  padding: 'var(--spacing-sm) var(--spacing-md)',
  background: 'var(--color-button-background)',
  color: 'var(--color-button-foreground)',
  borderRadius: 999,
  fontSize: 'var(--font-size-sm)',
  cursor: 'pointer',
  boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
};

export function AgentWindow() {
  const dispatch = useAppDispatch();
  const nodeRef = useRef<HTMLDivElement>(null);
  const isOpen = useAppSelector((s) => s.agent.isOpen);
  const isMinimized = useAppSelector((s) => s.agent.isMinimized);
  const position = useAppSelector((s) => s.agent.position);

  const handleStop = useCallback(
    (_e: unknown, data: { x: number; y: number }) => {
      dispatch(setAgentPosition({ x: data.x, y: data.y }));
    },
    [dispatch]
  );

  if (!isOpen) return null;

  if (isMinimized) {
    return (
      <div
        style={{
          ...pillStyle,
          left: position.x,
          top: position.y,
        }}
        onClick={() => dispatch(toggleMinimize())}
      >
        Agent
      </div>
    );
  }

  return (
    <Draggable
      nodeRef={nodeRef}
      handle=".agent-drag-handle"
      cancel="button, select, input"
      position={{ x: position.x, y: position.y }}
      onStop={handleStop}
    >
      <div ref={nodeRef} style={{ position: 'fixed', zIndex: 900 }}>
        <div style={windowStyle}>
          <AgentHeader />
          <AgentChatHistory />
          <AgentInput />
          <AgentStatusLine />
        </div>
      </div>
    </Draggable>
  );
}
