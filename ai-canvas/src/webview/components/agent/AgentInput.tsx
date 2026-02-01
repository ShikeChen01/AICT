import React, { useState, useCallback } from 'react';
import { useAppSelector, useAppDispatch } from '../../store/hooks';
import { addChatMessage } from '../../store/slices/agentSlice';
import type { ChatMessage } from '../../../shared/types/canvas';

function randomId(): string {
  return `msg-${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

const inputStyle: React.CSSProperties = {
  width: '100%',
  padding: 'var(--spacing-sm) var(--spacing-md)',
  fontSize: 'var(--font-size-md)',
  background: 'var(--color-input-background)',
  border: '1px solid var(--color-input-border)',
  borderRadius: 'var(--radius-md)',
  color: 'var(--color-foreground)',
  boxSizing: 'border-box',
};

export function AgentInput() {
  const dispatch = useAppDispatch();
  const [value, setValue] = useState('');

  const send = useCallback(() => {
    const trimmed = value.trim();
    if (!trimmed) return;
    const msg: ChatMessage = {
      id: randomId(),
      role: 'user',
      content: trimmed,
      timestamp: Date.now(),
    };
    dispatch(addChatMessage(msg));
    setValue('');
  }, [dispatch, value]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      send();
    }
  };

  return (
    <div style={{ padding: 'var(--spacing-sm)', borderTop: '1px solid var(--color-widget-border)', flexShrink: 0 }}>
      <input
        style={inputStyle}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onKeyDown={onKeyDown}
        placeholder="Type a message (Shift+Enter for newline)"
      />
    </div>
  );
}
