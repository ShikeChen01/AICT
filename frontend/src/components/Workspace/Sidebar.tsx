/**
 * Sidebar — project selector and navigation (workspace, kanban, prompt assembly, project architecture, settings).
 */

import { NavLink, useNavigate, useParams } from 'react-router-dom';
import { useProjectContext } from '../../contexts/ProjectContext';
import { Select, cn } from '../ui';

interface SidebarProps {
  activeProjectId: string;
  onProjectChange?: (projectId: string) => void;
}

export function Sidebar({ activeProjectId, onProjectChange }: SidebarProps) {
  const navigate = useNavigate();
  const { projectId } = useParams<{ projectId: string }>();
  const { projects, loading } = useProjectContext();

  const workspacePath = projectId ? `/repository/${projectId}/workspace` : '/';
  const kanbanPath = projectId ? `/repository/${projectId}/kanban` : '/';
  const promptAssemblyPath = projectId ? `/repository/${projectId}/prompt_assembly` : '/';
  const projectArchitecturePath = projectId ? `/repository/${projectId}/artifacts` : '/';
  const settingsPath = projectId ? `/repository/${projectId}/settings` : '/';
  const backendLogsPath = projectId ? `/repository/${projectId}/backend-logs` : '/';

  const handleProjectChange = (nextId: string) => {
    onProjectChange?.(nextId);
    navigate(`/repository/${nextId}/workspace`);
  };

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    cn(
      'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
      isActive
        ? 'bg-white/12 text-white'
        : 'text-slate-300 hover:bg-white/7 hover:text-white'
    );

  return (
    <aside className="w-72 border-r border-slate-800/80 bg-slate-950 text-white flex flex-col">
      <div className="border-b border-slate-800/80 px-5 py-5">
        <NavLink to="/repositories" className="group block">
          <h1 className="text-2xl font-bold tracking-tight group-hover:text-blue-300 transition-colors">AICT</h1>
          <p className="mt-1 text-xs text-slate-400 group-hover:text-slate-300 transition-colors">
            Agent Monitoring Console
          </p>
        </NavLink>
      </div>

      <div className="border-b border-slate-800/80 p-4">
        <label htmlFor="project-selector" className="mb-2 block text-[11px] uppercase tracking-wide text-slate-400">
          Active repository
        </label>
        <Select
          id="project-selector"
          value={activeProjectId}
          onChange={(e) => handleProjectChange(e.target.value)}
          disabled={loading}
          className="border-slate-700 bg-slate-900 text-slate-100 focus-visible:ring-blue-400/30"
        >
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </Select>
      </div>

      <nav className="flex-1 overflow-y-auto p-4">
        <ul className="space-y-2">
          <li>
            <NavLink to={workspacePath} className={linkClass}>
              <span className="w-5 h-5 flex items-center justify-center">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </span>
              Workspace
            </NavLink>
          </li>
          <li>
            <NavLink to={kanbanPath} className={linkClass}>
              <span className="w-5 h-5 flex items-center justify-center">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
                </svg>
              </span>
              Kanban
            </NavLink>
          </li>
          <li>
            <NavLink to={promptAssemblyPath} className={linkClass}>
              <span className="w-5 h-5 flex items-center justify-center">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </span>
              Prompt Assembly
            </NavLink>
          </li>
          <li>
            <NavLink to={projectArchitecturePath} className={linkClass}>
              <span className="w-5 h-5 flex items-center justify-center">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                </svg>
              </span>
              Project Architecture
            </NavLink>
          </li>
          <li>
            <NavLink to={settingsPath} className={linkClass}>
              <span className="w-5 h-5 flex items-center justify-center">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
              </span>
              Project Settings
            </NavLink>
          </li>
          <li>
            <a
              href={backendLogsPath}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-slate-300 transition-colors hover:bg-white/7 hover:text-white"
            >
              <span className="w-5 h-5 flex items-center justify-center">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                    d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </span>
              AI Usage
            </a>
          </li>
        </ul>
      </nav>

      <div className="border-t border-slate-800/80 p-4">
        <NavLink to="/settings" className="inline-flex items-center gap-2 text-sm text-slate-300 hover:text-white">
          User Settings
        </NavLink>
      </div>
    </aside>
  );
}

export default Sidebar;
