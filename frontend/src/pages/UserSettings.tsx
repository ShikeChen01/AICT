import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Monitor } from 'lucide-react';

import { updateMe, getOAuthLoginUrl, disconnectOAuth } from '../api/client';
import { useAuth } from '../contexts/AuthContext';
import { Button, Card, Input } from '../components/ui';
import { SandboxConfigEditor } from '../components/Sandbox/SandboxConfigEditor';
import { APIKeyManager } from '../components/APIKeyManager';
import { AppLayout } from '../components/Layout';
import { TierBadge } from '../components/TierBadge';
import type { UserProfile } from '../types';

function ConnectedAccounts({ user, onRefresh }: { user: UserProfile; onRefresh: () => Promise<void> }) {
  const [loading, setLoading] = useState(false);
  const [oauthError, setOAuthError] = useState<string | null>(null);

  const handleConnect = async () => {
    setOAuthError(null);
    setLoading(true);
    try {
      const { url } = await getOAuthLoginUrl('connect');
      window.location.href = url;
    } catch (err) {
      setOAuthError(err instanceof Error ? err.message : 'Failed to start OAuth flow');
      setLoading(false);
    }
  };

  const handleDisconnect = async () => {
    setOAuthError(null);
    setLoading(true);
    try {
      await disconnectOAuth();
      await onRefresh();
    } catch (err) {
      setOAuthError(err instanceof Error ? err.message : 'Failed to disconnect');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between rounded-lg border border-[var(--border)] p-3">
        <div className="flex items-center gap-3">
          <div className="h-8 w-8 rounded bg-gray-900 flex items-center justify-center">
            <svg className="w-4 h-4 text-white" viewBox="0 0 24 24" fill="currentColor">
              <path d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364l2.0201-1.1638a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.4114-.6765zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0974-2.3616l2.603-1.5006 2.6029 1.5006v3.0013l-2.6029 1.5006-2.603-1.5006z" />
            </svg>
          </div>
          <div>
            <p className="text-sm font-medium">OpenAI</p>
            {user.openai_connected ? (
              <p className="text-xs text-green-600">Connected</p>
            ) : (
              <p className="text-xs text-gray-500">Not connected</p>
            )}
          </div>
        </div>
        {user.openai_connected ? (
          <Button variant="ghost" onClick={handleDisconnect} disabled={loading}>
            Disconnect
          </Button>
        ) : (
          <Button variant="secondary" onClick={handleConnect} disabled={loading}>
            Connect
          </Button>
        )}
      </div>
      {oauthError && <p className="text-xs text-red-600">{oauthError}</p>}
      {user.openai_connected && (
        <p className="text-xs text-gray-500">
          OpenAI LLM calls use your OAuth token automatically. BYOK keys are not used while OAuth is active.
        </p>
      )}
    </div>
  );
}

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
    <AppLayout>
    <div className="flex-1 overflow-y-auto bg-[var(--app-bg)] p-6">
      <Card className="mx-auto max-w-2xl p-6">
        <h1 className="mb-2 text-xl font-semibold">User Settings</h1>
        <div className="mb-6 flex items-center gap-2">
          <p className="text-sm text-gray-600">{user.email}</p>
          <TierBadge tier={user?.tier ?? 'free'} />
        </div>
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
              onClick={() => navigate('/projects')}
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
        <div className="border-t border-[var(--border)] pt-4 mt-4">
          <h2 className="text-sm font-medium mb-3">Connected Accounts</h2>
          <ConnectedAccounts user={user} onRefresh={refreshProfile} />
        </div>
        <div className="border-t border-[var(--border)] pt-4 mt-4">
          <APIKeyManager />
        </div>
        <div className="border-t border-[var(--border)] pt-4 mt-4">
          <h2 className="text-sm font-medium mb-2">Billing &amp; Usage</h2>
          <Button variant="secondary" onClick={() => navigate('/settings/billing')}>
            Manage Billing
          </Button>
        </div>
      </Card>

      {/* Sandbox Configs — user-level reusable setup profiles */}
      <Card className="mx-auto max-w-2xl mt-6 p-6">
        <div className="flex items-center gap-2 mb-1">
          <Monitor className="w-5 h-5 text-gray-500" />
          <h2 className="text-lg font-semibold">Sandbox Configs</h2>
        </div>
        <p className="text-sm text-gray-500 mb-4">
          Reusable sandbox setup profiles. Each config defines a shell script that runs
          inside agent sandboxes to install apps, load data, or configure the environment.
          Assign configs to agents from the project Settings page.
        </p>
        <SandboxConfigEditor />
      </Card>
    </div>
    </AppLayout>
  );
}
