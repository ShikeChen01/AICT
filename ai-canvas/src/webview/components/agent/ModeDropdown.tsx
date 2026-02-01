import React from 'react';
import { useAppSelector, useAppDispatch } from '../../store/hooks';
import { setAgentMode } from '../../store/slices/agentSlice';
import type { AgentMode } from '../../../shared/types/canvas';

const options: { value: AgentMode; label: string }[] = [
  { value: 'plan-only', label: 'Plan-only' },
  { value: 'code+tests', label: 'Code+Tests' },
  { value: 'tests-only', label: 'Tests-only' },
  { value: 'docs-only', label: 'Documentation-only' },
];

const selectStyle: React.CSSProperties = {
  padding: 'var(--spacing-xs) var(--spacing-sm)',
  fontSize: 'var(--font-size-sm)',
  background: 'var(--color-input-background)',
  border: '1px solid var(--color-widget-border)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--color-foreground)',
  cursor: 'pointer',
};

export function ModeDropdown() {
  const dispatch = useAppDispatch();
  const mode = useAppSelector((s) => s.agent.mode);

  return (
    <select
      style={selectStyle}
      value={mode}
      onChange={(e) => dispatch(setAgentMode(e.target.value as AgentMode))}
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
