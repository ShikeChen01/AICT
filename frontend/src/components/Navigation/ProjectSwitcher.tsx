/**
 * ProjectSwitcher — dropdown in the top nav for switching between projects.
 */

import { useState, useRef, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ChevronDown, Check, FolderOpen } from 'lucide-react';
import { useProjectContext } from '../../contexts/ProjectContext';
import { cn } from '../ui';

export function ProjectSwitcher() {
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const { projects, loading } = useProjectContext();
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const currentProject = projects.find((p) => p.id === projectId);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  if (!projectId || loading) return null;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className={cn(
          'flex items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors',
          'text-[var(--text-primary)] hover:bg-[var(--surface-hover)]',
          'border border-[var(--border-color)]'
        )}
      >
        <FolderOpen className="h-4 w-4 text-[var(--text-muted)]" />
        <span className="max-w-[180px] truncate">{currentProject?.name ?? 'Select project'}</span>
        <ChevronDown className={cn('h-3.5 w-3.5 text-[var(--text-muted)] transition-transform', open && 'rotate-180')} />
      </button>

      {open && (
        <div className="absolute left-0 top-full z-50 mt-1 w-64 rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] py-1 shadow-lg">
          <div className="px-3 py-2">
            <p className="text-[11px] font-medium uppercase tracking-wide text-[var(--text-muted)]">Projects</p>
          </div>
          <div className="max-h-64 overflow-y-auto">
            {projects.map((project) => (
              <button
                key={project.id}
                type="button"
                onClick={() => {
                  navigate(`/project/${project.id}/workspace`);
                  setOpen(false);
                }}
                className={cn(
                  'flex w-full items-center gap-2 px-3 py-2 text-sm transition-colors',
                  project.id === projectId
                    ? 'bg-[var(--surface-hover)] text-[var(--text-primary)] font-medium'
                    : 'text-[var(--text-secondary)] hover:bg-[var(--surface-hover)]'
                )}
              >
                {project.id === projectId ? (
                  <Check className="h-3.5 w-3.5 text-[var(--color-primary)]" />
                ) : (
                  <span className="h-3.5 w-3.5" />
                )}
                <span className="truncate">{project.name}</span>
              </button>
            ))}
          </div>
          <div className="border-t border-[var(--border-color)] px-3 py-2">
            <button
              type="button"
              onClick={() => {
                navigate('/projects');
                setOpen(false);
              }}
              className="text-xs font-medium text-[var(--color-primary)] hover:text-[var(--color-primary-hover)]"
            >
              All Projects &rarr;
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
