/**
 * Sidebar — project selector and navigation (workspace, kanban, workflow, artifacts, settings).
 */

import { NavLink, useNavigate, useParams } from 'react-router-dom';
import { useProjectContext } from '../../contexts/ProjectContext';

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
  const workflowPath = projectId ? `/repository/${projectId}/workflow` : '/';
  const artifactsPath = projectId ? `/repository/${projectId}/artifacts` : '/';
  const settingsPath = projectId ? `/repository/${projectId}/settings` : '/';

  const handleProjectChange = (nextId: string) => {
    onProjectChange?.(nextId);
    navigate(`/repository/${nextId}/workspace`);
  };

  const linkClass = ({ isActive }: { isActive: boolean }) =>
    `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
      isActive ? 'bg-blue-600 text-white' : 'text-gray-300 hover:bg-gray-800 hover:text-white'
    }`;

  return (
    <aside className="w-64 bg-gray-900 text-white flex flex-col">
      <div className="p-6 border-b border-gray-800">
        <NavLink to="/repositories" className="group block">
          <h1 className="text-2xl font-bold group-hover:text-blue-300 transition-colors">AICT</h1>
          <p className="text-sm text-gray-400 group-hover:text-gray-300 transition-colors">
            Multi-Agent Platform
          </p>
        </NavLink>
      </div>

      <div className="p-4 border-b border-gray-800">
        <label htmlFor="project-selector" className="block text-xs uppercase tracking-wide text-gray-400 mb-2">
          Repository
        </label>
        <select
          id="project-selector"
          value={activeProjectId}
          onChange={(e) => handleProjectChange(e.target.value)}
          disabled={loading}
          className="w-full rounded-md border border-gray-700 bg-gray-800 px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          {projects.map((project) => (
            <option key={project.id} value={project.id}>
              {project.name}
            </option>
          ))}
        </select>
      </div>

      <nav className="flex-1 p-4">
        <ul className="space-y-2">
          <li>
            <NavLink to={workspacePath} className={linkClass}>
              <span className="w-5 h-5 flex items-center justify-center">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
                </svg>
              </span>
              Chat
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
            <NavLink to={workflowPath} className={linkClass}>
              <span className="w-5 h-5 flex items-center justify-center">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
              </span>
              Workflow
            </NavLink>
          </li>
          <li>
            <NavLink to={artifactsPath} className={linkClass}>
              <span className="w-5 h-5 flex items-center justify-center">
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7h5l2 2h11v10a2 2 0 01-2 2H5a2 2 0 01-2-2V7z" />
                </svg>
              </span>
              Artifacts
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
        </ul>
      </nav>

      <div className="p-4 border-t border-gray-800">
        <NavLink to="/settings" className="mb-3 inline-flex items-center gap-2 text-sm text-gray-300 hover:text-white">
          User Settings
        </NavLink>
      </div>
    </aside>
  );
}

export default Sidebar;
