import type { TextareaHTMLAttributes } from 'react';
import { cn } from './cn';

type TextareaProps = TextareaHTMLAttributes<HTMLTextAreaElement>;

export function Textarea({ className, ...props }: TextareaProps) {
  return (
    <textarea
      className={cn(
        'w-full rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] px-3 py-2.5 text-sm text-[var(--text-primary)] placeholder:text-[var(--text-faint)] shadow-[var(--shadow-xs)] outline-none transition-all duration-150 focus-visible:ring-2 focus-visible:ring-[var(--color-primary)]/30 focus-visible:border-[var(--color-primary)]/50',
        className
      )}
      {...props}
    />
  );
}

export default Textarea;

