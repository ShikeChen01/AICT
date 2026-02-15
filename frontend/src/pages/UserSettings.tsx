import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { updateMe } from '../api/client';
import { useAuth } from '../contexts/AuthContext';

export function UserSettingsPage() {
  const { user, refreshProfile, logout } = useAuth();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState(user?.display_name ?? '');
  const [githubToken, setGithubToken] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  if (!user) {
    return <div className="p-6">Loading...</div>;
  }

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setMessage(null);
    setError(null);
    setIsSaving(true);
    try {
      await updateMe({
        display_name: displayName || null,
        github_token: githubToken || null,
      });
      setGithubToken('');
      await refreshProfile();
      setMessage('Settings saved.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save settings');
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 p-6">
      <div className="max-w-2xl mx-auto bg-white border rounded-lg p-6">
        <h1 className="text-xl font-semibold mb-2">User Settings</h1>
        <p className="text-sm text-gray-600 mb-6">{user.email}</p>
        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Display name</label>
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              className="w-full px-3 py-2 border rounded-lg"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">GitHub Personal Access Token</label>
            <input
              type="password"
              value={githubToken}
              onChange={(e) => setGithubToken(e.target.value)}
              placeholder={user.github_token_set ? 'Configured - enter to replace' : 'ghp_xxx'}
              className="w-full px-3 py-2 border rounded-lg"
            />
          </div>
          {message && <p className="text-sm text-green-600">{message}</p>}
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-2">
            <button
              type="submit"
              disabled={isSaving}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg disabled:opacity-50"
            >
              Save
            </button>
            <button
              type="button"
              onClick={() => navigate('/repositories')}
              className="px-4 py-2 border rounded-lg"
            >
              Back
            </button>
            <button
              type="button"
              onClick={async () => {
                await logout();
                navigate('/login', { replace: true });
              }}
              className="ml-auto px-4 py-2 border rounded-lg"
            >
              Logout
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
