import React from 'react';
import { useAppSelector } from '../../store/hooks';
import type { AgentStatus } from '../../../shared/types/canvas';

const statusLabels: Record<AgentStatus, string> = {
  idle: '',
  planning: 'Planning…',
  writing: 'Writing…',
  testing: 'Testing…',
};

const lineStyle: React.CSSProperties = {
  padding: 'var(--spacing-xs) var(--spacing-sm)',
  fontSize: 'var(--font-size-xs)',
  color: 'var(--color-description)',
  borderTop: '1px solid var(--color-widget-border)',
  flexShrink: 0,
};

export function AgentStatusLine() {
  const status = useAppSelector((s) => s.agent.status);
  const label = statusLabels[status];
  if (!label) return null;
  return <div style={lineStyle}>{label}</div>;
}
