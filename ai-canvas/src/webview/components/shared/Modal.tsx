import React from 'react';

const overlayStyle: React.CSSProperties = {
  position: 'fixed',
  inset: 0,
  background: 'rgba(0,0,0,0.5)',
  display: 'flex',
  alignItems: 'center',
  justifyContent: 'center',
  zIndex: 1000,
};

const panelStyle: React.CSSProperties = {
  background: 'var(--color-sidebar-background)',
  border: '1px solid var(--color-widget-border)',
  borderRadius: 'var(--radius-lg)',
  padding: 'var(--spacing-lg)',
  minWidth: 320,
  maxWidth: 420,
  boxShadow: '0 4px 20px rgba(0,0,0,0.3)',
};

export function Modal({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  if (!open) return null;

  return (
    <div
      style={overlayStyle}
      onClick={(e) => e.target === e.currentTarget && onClose()}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div style={panelStyle} onClick={(e) => e.stopPropagation()}>
        <h2
          id="modal-title"
          style={{
            margin: '0 0 var(--spacing-md) 0',
            fontSize: 'var(--font-size-lg)',
            fontWeight: 600,
            color: 'var(--color-foreground)',
          }}
        >
          {title}
        </h2>
        {children}
      </div>
    </div>
  );
}
