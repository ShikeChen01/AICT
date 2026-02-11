/**
 * AICT Frontend Application
 * Main app with routing for Chat and Kanban views
 */

import { useState, useEffect } from 'react';
import { BrowserRouter, Routes, Route, NavLink, Navigate } from 'react-router-dom';
import { ChatView } from './components/Chat';
import { KanbanBoard } from './components/Kanban';
import { setAuthToken, healthCheck } from './api/client';

// Default project ID for MVP-0 (single project)
// In production, this would come from a project selector or URL
const DEFAULT_PROJECT_ID = '00000000-0000-0000-0000-000000000001';

// Set auth token SYNCHRONOUSLY before any component renders/fetches.
// Must run at module level so child useEffect hooks already have the token.
setAuthToken(import.meta.env.VITE_API_TOKEN || 'change-me-in-production');

function Sidebar() {
  return (
    <aside className="w-64 bg-gray-900 text-white flex flex-col">
      {/* Logo */}
      <div className="p-6 border-b border-gray-800">
        <h1 className="text-2xl font-bold">AICT</h1>
        <p className="text-sm text-gray-400">Multi-Agent Platform</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4">
        <ul className="space-y-2">
          <li>
            <NavLink
              to="/chat"
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                }`
              }
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                />
              </svg>
              Chat with GM
            </NavLink>
          </li>
          <li>
            <NavLink
              to="/kanban"
              className={({ isActive }) =>
                `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                  isActive
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                }`
              }
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2"
                />
              </svg>
              Kanban Board
            </NavLink>
          </li>
        </ul>
      </nav>

      {/* Footer */}
      <div className="p-4 border-t border-gray-800">
        <div className="flex items-center gap-3 text-sm text-gray-400">
          <div className="w-8 h-8 rounded-full bg-gray-700 flex items-center justify-center">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"
              />
            </svg>
          </div>
          <div>
            <p className="text-white font-medium">User</p>
            <p className="text-xs">MVP-0</p>
          </div>
        </div>
      </div>
    </aside>
  );
}

function ConnectionStatus({ isConnected }: { isConnected: boolean }) {
  return (
    <div
      className={`fixed bottom-4 right-4 flex items-center gap-2 px-3 py-2 rounded-full text-sm font-medium ${
        isConnected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
      }`}
    >
      <div
        className={`w-2 h-2 rounded-full ${
          isConnected ? 'bg-green-500' : 'bg-red-500 animate-pulse'
        }`}
      />
      {isConnected ? 'Connected' : 'Connecting...'}
    </div>
  );
}

function App() {
  const [isBackendConnected, setIsBackendConnected] = useState(false);
  const [projectId] = useState(DEFAULT_PROJECT_ID);

  // Token is set synchronously at module level above (before any component renders).

  // Check backend connection
  useEffect(() => {
    const checkConnection = async () => {
      try {
        await healthCheck();
        setIsBackendConnected(true);
      } catch {
        setIsBackendConnected(false);
      }
    };

    checkConnection();
    const interval = setInterval(checkConnection, 30000); // Check every 30s

    return () => clearInterval(interval);
  }, []);

  return (
    <BrowserRouter>
      <div className="flex h-screen bg-gray-100">
        <Sidebar />

        <main className="flex-1 overflow-hidden">
          <Routes>
            <Route path="/" element={<Navigate to="/chat" replace />} />
            <Route path="/chat" element={<ChatView projectId={projectId} />} />
            <Route path="/kanban" element={<KanbanBoard projectId={projectId} />} />
          </Routes>
        </main>

        <ConnectionStatus isConnected={isBackendConnected} />
      </div>
    </BrowserRouter>
  );
}

export default App;
