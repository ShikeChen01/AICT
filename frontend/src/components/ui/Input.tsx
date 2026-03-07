import type { InputHTMLAttributes } from 'react';
import { cn } from './cn';

type InputProps = InputHTMLAttributes<HTMLInputElement>;

export function Input({ className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        'h-9 w-full rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] px-3 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-faint)] shadow-[var(--shadow-xs)] outline-none transition-all duration-150 focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/30 focus-visible:border-[var(--color-primary)]/50',
        className
      )}
      {...props}
    />
  );
}

export default Input;

