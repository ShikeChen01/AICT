import React from 'react';
import { useAppSelector, useAppDispatch } from '../../store/hooks';
import { closeAgent, toggleMinimize } from '../../store/slices/agentSlice';
import { ScopeChip } from './ScopeChip';
import { ModeDropdown } from './ModeDropdown';

const headerStyle: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  gap: 'var(--spacing-sm)',
  padding: 'var(--spacing-sm) var(--spacing-md)',
  background: 'var(--color-sidebar-background)',
  borderBottom: '1px solid var(--color-widget-border)',
  cursor: 'move',
  flexShrink: 0,
};

const btnStyle: React.CSSProperties = {
  padding: 'var(--spacing-xs)',
  background: 'transparent',
  border: 'none',
  color: 'var(--color-foreground)',
  cursor: 'pointer',
  borderRadius: 'var(--radius-sm)',
  fontSize: 'var(--font-size-md)',
};

export function AgentHeader() {
  const dispatch = useAppDispatch();
  const scopeLocked = useAppSelector((s) => s.agent.scopeLocked);

  return (
    <div className="agent-drag-handle" style={headerStyle}>
        <ScopeChip />
        <span style={{ fontSize: 'var(--font-size-xs)', color: 'var(--color-description)' }}>
          {scopeLocked ? 'Scope locked' : 'Scope unlocked'}
        </span>
        <ModeDropdown />
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 4 }}>
          <button type="button" style={btnStyle} title="Run">▶</button>
          <button type="button" style={btnStyle} title="Stop">■</button>
          <button
            type="button"
            style={btnStyle}
            title="Minimize"
            onClick={() => dispatch(toggleMinimize())}
          >
            ▾
          </button>
          <button
            type="button"
            style={btnStyle}
            title="Close"
            onClick={() => dispatch(closeAgent())}
          >
            ✕
          </button>
        </div>
      </div>
  );
}
