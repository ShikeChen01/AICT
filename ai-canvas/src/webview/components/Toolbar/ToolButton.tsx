import React from 'react';

const style: React.CSSProperties = {
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  width: 48,
  height: 48,
  padding: 0,
  fontSize: 'var(--font-size-lg)',
  cursor: 'pointer',
  background: 'var(--color-button-background)',
  color: 'var(--color-button-foreground)',
  border: 'none',
  borderRadius: 'var(--radius-md)',
  fontFamily: 'var(--font-family)',
  transition: 'background 0.2s ease',
};

export function ToolButton({
  title,
  children,
  onClick,
  active,
}: {
  title: string;
  children: React.ReactNode;
  onClick: () => void;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      style={{
        ...style,
        background: active ? 'var(--color-button-hover)' : style.background,
      }}
      title={title}
      onClick={onClick}
      onMouseEnter={(e) => {
        e.currentTarget.style.background = 'var(--color-button-hover)';
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.background = active ? 'var(--color-button-hover)' : 'var(--color-button-background)';
      }}
    >
      {children}
    </button>
  );
}
