import type { HTMLAttributes } from 'react';
import { cn } from './cn';

type BadgeVariant = 'neutral' | 'default' | 'manager' | 'cto' | 'engineer' | 'success' | 'warning' | 'danger';

interface BadgeProps extends HTMLAttributes<HTMLSpanElement> {
  variant?: BadgeVariant;
}

const badgeVariantClass: Record<BadgeVariant, string> = {
  neutral: 'bg-slate-100 text-slate-700',
  default: 'bg-slate-100 text-slate-700',
  manager: 'bg-violet-100 text-violet-700',
  cto: 'bg-cyan-100 text-cyan-700',
  engineer: 'bg-emerald-100 text-emerald-700',
  success: 'bg-emerald-100 text-emerald-700',
  warning: 'bg-amber-100 text-amber-700',
  danger: 'bg-red-100 text-red-700',
};

export function Badge({ className, variant = 'neutral', ...props }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide',
        badgeVariantClass[variant],
        className
      )}
      {...props}
    />
  );
}

export default Badge;

