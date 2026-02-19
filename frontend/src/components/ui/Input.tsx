import type { InputHTMLAttributes } from 'react';
import { cn } from './cn';

type InputProps = InputHTMLAttributes<HTMLInputElement>;

export function Input({ className, ...props }: InputProps) {
  return (
    <input
      className={cn(
        'h-10 w-full rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] px-3 text-sm text-[var(--text-primary)] shadow-sm outline-none transition focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/30',
        className
      )}
      {...props}
    />
  );
}

export default Input;

