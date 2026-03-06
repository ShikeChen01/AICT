import type { HTMLAttributes, ReactNode } from 'react';
import { Card } from './Card';
import { cn } from './cn';

interface PanelProps extends HTMLAttributes<HTMLDivElement> {
  title?: string;
  subtitle?: string;
  headerActions?: ReactNode;
  bodyClassName?: string;
}

export function Panel({
  title,
  subtitle,
  headerActions,
  bodyClassName,
  children,
  className,
  ...props
}: PanelProps) {
  return (
    <Card className={cn('flex min-h-0 flex-col overflow-hidden', className)} {...props}>
      {(title || subtitle || headerActions) && (
        <div className="flex items-start justify-between gap-3 border-b border-[var(--border-color)] bg-[var(--surface-muted)] px-4 py-3">
          <div>
            {title && <h3 className="text-sm font-semibold text-[var(--text-primary)]">{title}</h3>}
            {subtitle && <p className="mt-0.5 text-xs text-[var(--text-muted)]">{subtitle}</p>}
          </div>
          {headerActions}
        </div>
      )}
      <div className={cn('min-h-0 flex-1 flex flex-col overflow-hidden', bodyClassName)}>{children}</div>
    </Card>
  );
}

export default Panel;

