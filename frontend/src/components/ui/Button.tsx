import type { ButtonHTMLAttributes } from 'react';
import { cn } from './cn';

type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
type ButtonSize = 'sm' | 'md' | 'lg';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  size?: ButtonSize;
}

const variantClass: Record<ButtonVariant, string> = {
  primary:
    'bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)] shadow-[var(--shadow-xs)] hover:shadow-[var(--shadow-sm)]',
  secondary:
    'bg-[var(--surface-card)] text-[var(--text-primary)] hover:bg-[var(--surface-hover)] border border-[var(--border-color)] shadow-[var(--shadow-xs)]',
  outline:
    'bg-transparent text-[var(--text-primary)] hover:bg-[var(--surface-hover)] border border-[var(--border-color)]',
  ghost:
    'text-[var(--text-secondary)] hover:bg-[var(--surface-muted)] hover:text-[var(--text-primary)]',
  danger:
    'bg-[var(--color-danger)] text-white hover:opacity-90 shadow-[var(--shadow-xs)]',
};

const sizeClass: Record<ButtonSize, string> = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-9 px-4 text-sm',
  lg: 'h-10 px-5 text-sm',
};

export function Button({
  className,
  variant = 'primary',
  size = 'md',
  type = 'button',
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={cn(
        'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/40 focus-visible:ring-offset-1',
        variantClass[variant],
        sizeClass[size],
        className
      )}
      {...props}
    />
  );
}

export default Button;
