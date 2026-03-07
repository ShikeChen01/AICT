/**
 * AppLayout — shared layout shell for all authenticated pages.
 * Renders TopNav at the top with page content below.
 */

import { TopNav } from '../Navigation';

interface AppLayoutProps {
  children: React.ReactNode;
}

export function AppLayout({ children }: AppLayoutProps) {
  return (
    <div className="flex h-screen flex-col overflow-hidden bg-[var(--app-bg)]">
      <TopNav />
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {children}
      </div>
    </div>
  );
}
