import React from 'react';
import { useAppSelector } from '../../store/hooks';

const containerStyle: React.CSSProperties = {
  flex: 1,
  overflow: 'auto',
  padding: 'var(--spacing-sm)',
  display: 'flex',
  flexDirection: 'column',
  gap: 'var(--spacing-sm)',
};

const bubbleUser: React.CSSProperties = {
  alignSelf: 'flex-end',
  maxWidth: '85%',
  padding: 'var(--spacing-sm) var(--spacing-md)',
  background: 'var(--color-button-background)',
  color: 'var(--color-button-foreground)',
  borderRadius: 'var(--radius-md)',
  fontSize: 'var(--font-size-sm)',
};

const bubbleAgent: React.CSSProperties = {
  alignSelf: 'flex-start',
  maxWidth: '85%',
  padding: 'var(--spacing-sm) var(--spacing-md)',
  background: 'var(--color-input-background)',
  border: '1px solid var(--color-widget-border)',
  borderRadius: 'var(--radius-md)',
  fontSize: 'var(--font-size-sm)',
};

export function AgentChatHistory() {
  const history = useAppSelector((s) => s.agent.history);

  return (
    <div style={containerStyle}>
      {history.length === 0 && (
        <div style={{ color: 'var(--color-description)', fontSize: 'var(--font-size-sm)' }}>
          No messages yet. Set scope and type a prompt to start.
        </div>
      )}
      {history.map((msg) => (
        <div
          key={msg.id}
          style={msg.role === 'user' ? bubbleUser : bubbleAgent}
        >
          {msg.content}
        </div>
      ))}
    </div>
  );
}
