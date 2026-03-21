import { useNavigate } from 'react-router-dom';
import { Button } from './ui';

interface TierLimitError {
  error: 'tier_limit';
  message: string;
  current_tier: string;
  upgrade_url: string;
}

export function UpgradeBanner({ detail }: { detail: TierLimitError }) {
  const navigate = useNavigate();
  return (
    <div className="rounded-lg border border-[var(--color-warning)]/30 bg-[var(--color-warning-light)] p-4">
      <p className="text-sm text-[var(--color-warning)]">{detail.message}</p>
      <Button variant="secondary" size="sm" className="mt-2" onClick={() => navigate(detail.upgrade_url)}>
        View Plans
      </Button>
    </div>
  );
}
