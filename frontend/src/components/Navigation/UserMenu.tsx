/**
 * UserMenu — profile dropdown in the top nav with settings and logout.
 */

import { useState, useRef, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { User, LogOut, Cog } from 'lucide-react';
import { useAuth } from '../../contexts/AuthContext';
import { cn } from '../ui';

export function UserMenu() {
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const initials = user?.display_name
    ? user.display_name.split(' ').map((n) => n[0]).join('').toUpperCase().slice(0, 2)
    : user?.email?.[0]?.toUpperCase() ?? '?';

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          'flex h-8 w-8 items-center justify-center rounded-full text-xs font-semibold transition-colors',
          'bg-[var(--color-primary)] text-white hover:bg-[var(--color-primary-hover)]'
        )}
        title={user?.display_name || user?.email || 'User menu'}
      >
        {initials}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-50 mt-1 w-56 rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] py-1 shadow-lg">
          <div className="border-b border-[var(--border-color)] px-4 py-3">
            <p className="text-sm font-medium text-[var(--text-primary)] truncate">
              {user?.display_name || 'User'}
            </p>
            <p className="text-xs text-[var(--text-muted)] truncate">{user?.email}</p>
          </div>

          <div className="py-1">
            <button
              type="button"
              onClick={() => {
                navigate('/settings');
                setOpen(false);
              }}
              className="flex w-full items-center gap-2.5 px-4 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
            >
              <User className="h-4 w-4" />
              User Settings
            </button>

            {projectId && (
              <button
                type="button"
                onClick={() => {
                  navigate(`/project/${projectId}/settings`);
                  setOpen(false);
                }}
                className="flex w-full items-center gap-2.5 px-4 py-2 text-sm text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]"
              >
                <Cog className="h-4 w-4" />
                Project Settings
              </button>
            )}
          </div>

          <div className="border-t border-[var(--border-color)] py-1">
            <button
              type="button"
              onClick={async () => {
                setOpen(false);
                await logout();
                navigate('/login', { replace: true });
              }}
              className="flex w-full items-center gap-2.5 px-4 py-2 text-sm text-red-600 hover:bg-red-50"
            >
              <LogOut className="h-4 w-4" />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
