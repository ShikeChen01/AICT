import { useState, useEffect, useCallback } from 'react';
import { Key, Check, X, Trash2, Loader2 } from 'lucide-react';

import { listAPIKeys, upsertAPIKey, deleteAPIKey, testAPIKey, type UserAPIKey } from '../api/client';
import { Button } from './ui';

const PROVIDERS = [
  { id: 'anthropic', name: 'Anthropic (Claude)', placeholder: 'sk-ant-api03-...' },
  { id: 'openai', name: 'OpenAI', placeholder: 'sk-...' },
  { id: 'google', name: 'Google (Gemini)', placeholder: 'AIza...' },
  { id: 'moonshot', name: 'Moonshot (Kimi)', placeholder: 'sk-...' },
];

export function APIKeyManager() {
  const [keys, setKeys] = useState<UserAPIKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingProvider, setEditingProvider] = useState<string | null>(null);
  const [keyInput, setKeyInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ provider: string; valid: boolean; error?: string } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listAPIKeys();
      setKeys(data);
    } catch {
      // silently fail
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  const handleSave = async (provider: string) => {
    if (!keyInput.trim()) return;
    setSaving(true);
    try {
      await upsertAPIKey(provider, keyInput.trim());
      setKeyInput('');
      setEditingProvider(null);
      await refresh();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Failed to save key');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (provider: string) => {
    try {
      await deleteAPIKey(provider);
      await refresh();
    } catch {
      // key may not exist
    }
  };

  const handleTest = async (provider: string) => {
    setTesting(provider);
    setTestResult(null);
    try {
      const result = await testAPIKey(provider);
      setTestResult({ provider, ...result });
    } catch (err) {
      setTestResult({ provider, valid: false, error: err instanceof Error ? err.message : 'Test failed' });
    } finally {
      setTesting(null);
    }
  };

  const getKeyForProvider = (provider: string) => keys.find(k => k.provider === provider);

  if (loading) return <div className="text-sm text-[var(--text-muted)]">Loading API keys...</div>;

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Key size={16} />
        <h2 className="text-sm font-medium">LLM API Keys</h2>
      </div>
      <p className="text-xs text-[var(--text-muted)]">
        Add your own API keys so agents use your account directly. Server keys are used as fallback.
      </p>

      {PROVIDERS.map(({ id, name, placeholder }) => {
        const existing = getKeyForProvider(id);
        const isEditing = editingProvider === id;

        return (
          <div key={id} className="rounded border border-[var(--border)] p-3 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">{name}</span>
                {existing && (
                  <span className={`text-xs px-1.5 py-0.5 rounded ${existing.is_valid ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                    {existing.is_valid ? 'Active' : 'Invalid'}
                  </span>
                )}
              </div>
              <div className="flex items-center gap-1">
                {existing && (
                  <>
                    <span className="text-xs text-[var(--text-muted)] font-mono">{existing.display_hint}</span>
                    <Button variant="ghost" size="sm" onClick={() => handleTest(id)} disabled={testing === id}>
                      {testing === id ? <Loader2 size={12} className="animate-spin" /> : 'Test'}
                    </Button>
                    <Button variant="ghost" size="sm" onClick={() => handleDelete(id)}>
                      <Trash2 size={12} />
                    </Button>
                  </>
                )}
                <Button variant="ghost" size="sm" onClick={() => { setEditingProvider(isEditing ? null : id); setKeyInput(''); }}>
                  {isEditing ? 'Cancel' : existing ? 'Update' : 'Add'}
                </Button>
              </div>
            </div>

            {testResult?.provider === id && (
              <div className={`text-xs flex items-center gap-1 ${testResult.valid ? 'text-green-600' : 'text-red-600'}`}>
                {testResult.valid ? <Check size={12} /> : <X size={12} />}
                {testResult.valid ? 'Key is valid' : testResult.error}
              </div>
            )}

            {isEditing && (
              <div className="flex gap-2">
                <input
                  type="password"
                  value={keyInput}
                  onChange={e => setKeyInput(e.target.value)}
                  placeholder={placeholder}
                  className="flex-1 rounded border border-[var(--border)] bg-[var(--bg-primary)] px-2 py-1 text-sm font-mono"
                  onKeyDown={e => e.key === 'Enter' && handleSave(id)}
                />
                <Button size="sm" onClick={() => handleSave(id)} disabled={saving || !keyInput.trim()}>
                  {saving ? <Loader2 size={12} className="animate-spin" /> : 'Save'}
                </Button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
