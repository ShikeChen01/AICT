import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '../ui';
import type { UsageUpdateData } from '../../types';

const MAX_DISPLAY = 500;

interface UsageStreamViewProps {
  events: UsageUpdateData[];
  onClear: () => void;
}

const providerColor: Record<string, string> = {
  anthropic: 'bg-orange-100 text-orange-700 border-orange-200',
  google:    'bg-blue-100 text-blue-700 border-blue-200',
  openai:    'bg-green-100 text-green-700 border-green-200',
};

function fmtTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(2)}M`;
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`;
  return String(n);
}

function fmtCost(n: number): string {
  if (n === 0) return '$0.00';
  if (n < 0.0001) return `<$0.0001`;
  return `$${n.toFixed(4)}`;
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString();
  } catch {
    return iso;
  }
}

type ProviderFilter = 'all' | 'anthropic' | 'google' | 'openai';

export function UsageStreamView({ events, onClear }: UsageStreamViewProps) {
  const [autoScroll, setAutoScroll] = useState(true);
  const [providerFilter, setProviderFilter] = useState<ProviderFilter>('all');
  const [modelQuery, setModelQuery] = useState('');
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!autoScroll) return;
    const el = containerRef.current;
    if (el) el.scrollTop = 0;
  }, [events.length, autoScroll]);

  const filtered = useMemo(() => {
    const q = modelQuery.trim().toLowerCase();
    return events
      .filter((e) => providerFilter === 'all' || e.provider === providerFilter)
      .filter((e) => !q || e.model.toLowerCase().includes(q))
      .slice(0, MAX_DISPLAY);
  }, [events, providerFilter, modelQuery]);

  const totals = useMemo(() => {
    return events.reduce(
      (acc, e) => ({
        calls: acc.calls + 1,
        inputTokens: acc.inputTokens + e.input_tokens,
        outputTokens: acc.outputTokens + e.output_tokens,
        cost: acc.cost + e.estimated_cost_usd,
      }),
      { calls: 0, inputTokens: 0, outputTokens: 0, cost: 0 }
    );
  }, [events]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-[var(--border-color)] bg-[var(--surface-card)] shadow-sm">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-[var(--border-color)] px-5 py-4">
        <div>
          <h2 className="text-base font-semibold text-[var(--text-primary)]">AI Usage Stream</h2>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            Live LLM call events via WebSocket &mdash;{' '}
            <span className={events.length >= MAX_DISPLAY ? 'font-semibold text-amber-500' : ''}>
              {events.length} event{events.length !== 1 ? 's' : ''} buffered
              {events.length >= MAX_DISPLAY ? ' (oldest dropped)' : ''}
            </span>
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button variant="secondary" size="sm" onClick={() => setAutoScroll((v) => !v)}>
            {autoScroll ? 'Pause scroll' : 'Resume scroll'}
          </Button>
          <Button variant="secondary" size="sm" onClick={onClear}>
            Clear
          </Button>
        </div>
      </div>

      {/* Summary stats */}
      <div className="grid grid-cols-2 gap-3 border-b border-[var(--border-color)] px-5 py-3 md:grid-cols-4">
        {[
          { label: 'Total calls', value: totals.calls.toLocaleString() },
          { label: 'Input tokens', value: fmtTokens(totals.inputTokens) },
          { label: 'Output tokens', value: fmtTokens(totals.outputTokens) },
          { label: 'Est. cost', value: fmtCost(totals.cost) },
        ].map(({ label, value }) => (
          <div key={label} className="rounded-lg border border-[var(--border-color)] bg-[var(--surface-hover)] px-3 py-2">
            <div className="text-[11px] uppercase tracking-wide text-[var(--text-muted)]">{label}</div>
            <div className="mt-0.5 text-lg font-semibold tabular-nums text-[var(--text-primary)]">{value}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div className="grid grid-cols-1 gap-3 border-b border-[var(--border-color)] px-5 py-3 md:grid-cols-[160px_1fr]">
        <select
          value={providerFilter}
          onChange={(e) => setProviderFilter(e.target.value as ProviderFilter)}
          className="h-10 rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] px-3 text-sm text-[var(--text-primary)]"
        >
          <option value="all">All providers</option>
          <option value="anthropic">Anthropic</option>
          <option value="google">Google</option>
          <option value="openai">OpenAI</option>
        </select>
        <input
          type="text"
          value={modelQuery}
          onChange={(e) => setModelQuery(e.target.value)}
          placeholder="Filter by model name"
          className="h-10 rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] px-3 text-sm text-[var(--text-primary)]"
        />
      </div>

      {/* Event list */}
      <div ref={containerRef} className="min-h-0 flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="flex h-32 flex-col items-center justify-center gap-2 text-sm text-[var(--text-muted)]">
            <svg className="h-8 w-8 opacity-30" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
                d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
            Waiting for LLM calls&hellip;
          </div>
        ) : (
          <table className="w-full text-sm">
            <thead className="sticky top-0 z-10 bg-[var(--surface-card)]">
              <tr className="border-b border-[var(--border-color)] text-left text-[11px] uppercase tracking-wide text-[var(--text-muted)]">
                <th className="px-4 py-2">Time</th>
                <th className="px-4 py-2">Provider</th>
                <th className="px-4 py-2">Model</th>
                <th className="px-4 py-2 text-right">In</th>
                <th className="px-4 py-2 text-right">Out</th>
                <th className="px-4 py-2 text-right">Cost</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border-color)]">
              {filtered.map((e, i) => (
                <tr key={`${e.created_at}-${i}`} className="hover:bg-[var(--surface-hover)]">
                  <td className="px-4 py-2.5 font-mono text-xs text-[var(--text-muted)]">
                    {fmtTime(e.created_at)}
                  </td>
                  <td className="px-4 py-2.5">
                    <span className={`inline-block rounded border px-2 py-0.5 text-[11px] font-semibold ${providerColor[e.provider] ?? 'bg-slate-100 text-slate-700 border-slate-200'}`}>
                      {e.provider}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 font-mono text-xs text-[var(--text-primary)]">
                    {e.model}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-[var(--text-secondary)]">
                    {fmtTokens(e.input_tokens)}
                  </td>
                  <td className="px-4 py-2.5 text-right font-mono text-xs tabular-nums text-[var(--text-secondary)]">
                    {fmtTokens(e.output_tokens)}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-mono text-xs tabular-nums font-semibold ${e.estimated_cost_usd > 0 ? 'text-emerald-600' : 'text-[var(--text-muted)]'}`}>
                    {fmtCost(e.estimated_cost_usd)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

export default UsageStreamView;
