import type { HTMLAttributes } from 'react';
import { cn } from './cn';

type CardProps = HTMLAttributes<HTMLDivElement>;

export function Card({ className, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-xl border border-[var(--border-color)] bg-[var(--surface-card)] shadow-[var(--shadow-sm)]',
        className
      )}
      {...props}
    />
  );
}

export default Card;

