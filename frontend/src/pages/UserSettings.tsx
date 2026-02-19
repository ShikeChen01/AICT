import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { updateMe } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { Button, Card, Input } from '../components/ui';

export function UserSettingsPage() {
  const { user, refreshProfile, logout } = useAuth();
  const navigate = useNavigate();
  const [displayName, setDisplayName] = useState(user?.display_name ?? '');
  const [githubToken, setGithubToken] = useState('');
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isSaving, setIsSaving] = useState(false);

  if (!user) {
    return <div className="p-6 text-[var(--text-muted)]">Loading...</div>;
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
    <div className="min-h-screen bg-[var(--app-bg)] p-6">
      <Card className="mx-auto max-w-2xl p-6">
        <h1 className="mb-2 text-xl font-semibold">User Settings</h1>
        <p className="mb-6 text-sm text-gray-600">{user.email}</p>
        <form onSubmit={handleSave} className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1">Display name</label>
            <Input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1">GitHub Personal Access Token</label>
            <Input
              type="password"
              value={githubToken}
              onChange={(e) => setGithubToken(e.target.value)}
              placeholder={user.github_token_set ? 'Configured - enter to replace' : 'ghp_xxx'}
            />
          </div>
          {message && <p className="text-sm text-green-600">{message}</p>}
          {error && <p className="text-sm text-red-600">{error}</p>}
          <div className="flex gap-2">
            <Button
              type="submit"
              disabled={isSaving}
            >
              Save
            </Button>
            <Button
              type="button"
              onClick={() => navigate('/repositories')}
              variant="secondary"
            >
              Back
            </Button>
            <Button
              type="button"
              onClick={async () => {
                await logout();
                navigate('/login', { replace: true });
              }}
              variant="ghost"
              className="ml-auto"
            >
              Logout
            </Button>
          </div>
        </form>
      </Card>
    </div>
  );
}
