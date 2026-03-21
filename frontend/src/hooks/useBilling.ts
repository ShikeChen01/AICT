import { useState, useEffect, useCallback } from 'react';
import { getSubscription, getUsage, type SubscriptionInfo, type UsageSummary } from '../api/client';

export function useBilling() {
  const [subscription, setSubscription] = useState<SubscriptionInfo | null>(null);
  const [usage, setUsage] = useState<UsageSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [sub, usg] = await Promise.all([getSubscription(), getUsage()]);
      setSubscription(sub);
      setUsage(usg);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load billing');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  return { subscription, usage, loading, error, refresh };
}
