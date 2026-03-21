/**
 * Billing Page — subscription management and usage overview.
 *
 * Shows:
 *  - Current plan card (tier, status, renewal date)
 *  - Usage bars for headless and desktop compute
 *  - Upgrade cards for free/individual users
 *  - Stripe Portal link for paid subscribers
 */

import { CreditCard, Loader2, AlertCircle, CheckCircle, Zap, Monitor } from 'lucide-react';
import { AppLayout } from '../components/Layout';
import { Button, Card } from '../components/ui';
import { useBilling } from '../hooks/useBilling';
import { createCheckoutSession, createPortalSession } from '../api/client';
import { formatHours } from '../utils/billingUtils';

// ── Helpers ──────────────────────────────────────────────────────────────────

function usagePct(used: number, included: number): number {
  if (included === 0) return 0;
  return Math.min(100, Math.round((used / included) * 100));
}

function barColor(pct: number): string {
  if (pct >= 90) return 'bg-red-500';
  if (pct >= 70) return 'bg-yellow-500';
  return 'bg-green-500';
}

// ── Sub-components ────────────────────────────────────────────────────────────

function UsageBar({
  label,
  used,
  included,
  icon,
}: {
  label: string;
  used: number;
  included: number;
  icon: React.ReactNode;
}) {
  const pct = usagePct(used, included);
  const color = barColor(pct);
  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-sm">
        <span className="flex items-center gap-1.5 font-medium">
          {icon}
          {label}
        </span>
        <span className="text-[var(--text-secondary)]">
          {formatHours(used)} / {formatHours(included)}
        </span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-[var(--surface-muted)]">
        <div
          className={`h-full rounded-full transition-all duration-300 ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-[var(--text-secondary)]">{pct}% used this period</p>
    </div>
  );
}

// ── Plan definitions ──────────────────────────────────────────────────────────

interface PlanDef {
  tier: string;
  label: string;
  price: string;
  description: string;
  highlights: string[];
}

const PLANS: PlanDef[] = [
  {
    tier: 'individual',
    label: 'Individual',
    price: '$20 / month',
    description: 'For solo developers who need more compute.',
    highlights: ['200h headless compute', '200h desktop compute'],
  },
  {
    tier: 'team',
    label: 'Team',
    price: '$50 / month',
    description: 'For teams that need shared agent infrastructure.',
    highlights: ['1000h headless compute', '1000h desktop compute', '3 team seats'],
  },
];

function tierLabel(tier: string): string {
  return tier.charAt(0).toUpperCase() + tier.slice(1);
}

// ── Page ──────────────────────────────────────────────────────────────────────

export function BillingPage() {
  const { subscription, usage, loading, error, refresh } = useBilling();

  const handleUpgrade = async (tier: string) => {
    try {
      const { checkout_url } = await createCheckoutSession(tier, window.location.href);
      window.location.assign(checkout_url);
    } catch (err) {
      console.error('Checkout error', err);
    }
  };

  const handleManage = async () => {
    try {
      const { portal_url } = await createPortalSession(window.location.href);
      window.location.assign(portal_url);
    } catch (err) {
      console.error('Portal error', err);
    }
  };

  const isPaid = subscription?.tier === 'individual' || subscription?.tier === 'team';

  return (
    <AppLayout>
      <div className="min-h-screen bg-[var(--app-bg)] p-6">
        <div className="mx-auto max-w-2xl space-y-6">

          <div className="flex items-center gap-2">
            <CreditCard className="h-5 w-5 text-[var(--text-secondary)]" />
            <h1 className="text-xl font-semibold">Billing &amp; Usage</h1>
          </div>

          {/* Error state */}
          {error && (
            <div className="flex items-center gap-2 rounded-lg border border-[var(--color-danger)]/30 bg-[var(--color-danger-light)] p-4 text-sm text-[var(--color-danger)]">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
              <Button variant="ghost" size="sm" className="ml-auto" onClick={() => void refresh()}>
                Retry
              </Button>
            </div>
          )}

          {/* Loading state */}
          {loading && (
            <div className="flex items-center justify-center py-12 text-[var(--text-muted)]">
              <Loader2 className="h-6 w-6 animate-spin" />
            </div>
          )}

          {!loading && subscription && usage && (
            <>
              {/* Current plan */}
              <Card className="p-6">
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-xs font-medium uppercase tracking-wide text-[var(--text-secondary)]">
                      Current plan
                    </p>
                    <p className="mt-1 text-2xl font-semibold">{tierLabel(subscription.tier)}</p>
                    <p className="mt-0.5 text-sm text-[var(--text-secondary)] capitalize">
                      {subscription.status}
                      {subscription.cancel_at_period_end && ' · cancels at period end'}
                    </p>
                    {subscription.current_period_end && (
                      <p className="mt-0.5 text-xs text-[var(--text-secondary)]">
                        Renews {new Date(subscription.current_period_end).toLocaleDateString()}
                      </p>
                    )}
                  </div>
                  <div className="flex items-center gap-2">
                    {isPaid ? (
                      <CheckCircle className="h-8 w-8 text-green-500" />
                    ) : (
                      <Zap className="h-8 w-8 text-[var(--text-muted)]" />
                    )}
                  </div>
                </div>

                {isPaid && (
                  <div className="mt-4 border-t border-[var(--border)] pt-4">
                    <Button variant="secondary" onClick={() => void handleManage()}>
                      Manage Subscription
                    </Button>
                  </div>
                )}
              </Card>

              {/* Usage */}
              <Card className="p-6">
                <h2 className="mb-4 text-sm font-medium uppercase tracking-wide text-[var(--text-secondary)]">
                  Usage — {new Date(usage.period_start).toLocaleDateString()} to{' '}
                  {new Date(usage.period_end).toLocaleDateString()}
                </h2>
                <div className="space-y-5">
                  <UsageBar
                    label="Headless Compute"
                    used={usage.headless_seconds_used}
                    included={usage.headless_seconds_included}
                    icon={<Zap className="h-3.5 w-3.5" />}
                  />
                  <UsageBar
                    label="Desktop Compute"
                    used={usage.desktop_seconds_used}
                    included={usage.desktop_seconds_included}
                    icon={<Monitor className="h-3.5 w-3.5" />}
                  />
                </div>
              </Card>

              {/* Upgrade cards — only for free/individual */}
              {(!isPaid || subscription.tier === 'individual') && (
                <div className="space-y-3">
                  <h2 className="text-sm font-medium text-[var(--text-secondary)]">
                    {subscription.tier === 'free' ? 'Upgrade your plan' : 'Upgrade to Team'}
                  </h2>
                  <div className="grid gap-4 sm:grid-cols-2">
                    {PLANS.filter((p) =>
                      subscription.tier === 'free' ? true : p.tier === 'team'
                    ).map((plan) => (
                      <Card key={plan.tier} className="p-5">
                        <p className="text-lg font-semibold">{plan.label}</p>
                        <p className="mt-0.5 text-xl font-bold">{plan.price}</p>
                        <p className="mt-1 text-sm text-[var(--text-secondary)]">{plan.description}</p>
                        <ul className="mt-3 space-y-1">
                          {plan.highlights.map((h) => (
                            <li key={h} className="flex items-center gap-1.5 text-sm">
                              <CheckCircle className="h-3.5 w-3.5 text-green-500" />
                              {h}
                            </li>
                          ))}
                        </ul>
                        <Button
                          className="mt-4 w-full"
                          onClick={() => void handleUpgrade(plan.tier)}
                        >
                          Upgrade to {plan.label}
                        </Button>
                      </Card>
                    ))}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </AppLayout>
  );
}
