const TIER_COLORS: Record<string, string> = {
  free: 'bg-gray-100 text-gray-700',
  individual: 'bg-blue-100 text-blue-700',
  team: 'bg-purple-100 text-purple-700',
};

export function TierBadge({ tier }: { tier: string }) {
  const colors = TIER_COLORS[tier] ?? TIER_COLORS.free;
  return (
    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ${colors}`}>
      {tier.charAt(0).toUpperCase() + tier.slice(1)}
    </span>
  );
}
