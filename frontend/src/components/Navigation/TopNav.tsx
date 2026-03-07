/**
 * TopNav — primary horizontal navigation bar replacing the old sidebar.
 * Professional, Figma-inspired top bar with project context, main nav, and user menu.
 */

import { NavLink, useParams } from 'react-router-dom';
import {
  MessageSquare,
  LayoutDashboard,
  Cpu,
  LayoutGrid,
  BarChart3,
  Sun,
  Moon,
} from 'lucide-react';
import { ProjectSwitcher } from './ProjectSwitcher';
import { UserMenu } from './UserMenu';
import { useTheme } from '../../contexts/ThemeContext';
import { cn } from '../ui';

interface NavItem {
  label: string;
  path: string;
  icon: React.ReactNode;
}

export function TopNav() {
  const { projectId } = useParams<{ projectId: string }>();
  const { theme, toggleTheme } = useTheme();

  const navItems: NavItem[] = projectId
    ? [
        {
          label: 'Workspace',
          path: `/project/${projectId}/workspace`,
          icon: <MessageSquare className="h-4 w-4" aria-hidden="true" />,
        },
        {
          label: 'Dashboard',
          path: `/project/${projectId}/dashboard`,
          icon: <LayoutDashboard className="h-4 w-4" aria-hidden="true" />,
        },
        {
          label: 'Agent Build',
          path: `/project/${projectId}/agent-build`,
          icon: <Cpu className="h-4 w-4" aria-hidden="true" />,
        },
        {
          label: 'Kanban',
          path: `/project/${projectId}/kanban`,
          icon: <LayoutGrid className="h-4 w-4" aria-hidden="true" />,
        },
        {
          label: 'Logs',
          path: `/project/${projectId}/logs`,
          icon: <BarChart3 className="h-4 w-4" aria-hidden="true" />,
        },
      ]
    : [];

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium rounded-md transition-colors',
      isActive
        ? 'bg-[var(--color-primary)]/10 text-[var(--color-primary)]'
        : 'text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--surface-hover)]'
    );

  return (
    <header className="flex h-14 shrink-0 items-center border-b border-[var(--border-color)] bg-[var(--surface-card)] px-4 shadow-[var(--shadow-xs)]" role="banner">
      {/* Left: Logo */}
      <NavLink to="/projects" className="mr-6 flex items-center gap-2" aria-label="AICT — go to projects">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-[var(--color-primary)] text-white text-xs font-bold" aria-hidden="true">
          AI
        </div>
        <div className="hidden sm:block">
          <span className="text-base font-bold tracking-tight text-[var(--text-primary)]">AICT</span>
        </div>
      </NavLink>

      {/* Project Switcher */}
      <ProjectSwitcher />

      {/* Center: Nav items */}
      {navItems.length > 0 && (
        <nav className="ml-6 flex items-center gap-1" aria-label="Main navigation">
          {navItems.map((item) => (
            <NavLink key={item.path} to={item.path} className={linkClass} end aria-label={item.label}>
              {item.icon}
              <span className="hidden md:inline">{item.label}</span>
            </NavLink>
          ))}
        </nav>
      )}

      {/* Right: Theme toggle + User menu */}
      <div className="ml-auto flex items-center gap-2">
        <button
          onClick={toggleTheme}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-[var(--text-secondary)] hover:bg-[var(--surface-hover)] hover:text-[var(--text-primary)] transition-colors"
          aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'}
        >
          {theme === 'dark' ? <Sun className="h-4 w-4" aria-hidden="true" /> : <Moon className="h-4 w-4" aria-hidden="true" />}
        </button>
        <UserMenu />
      </div>
    </header>
  );
}
