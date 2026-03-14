/**
 * ContextBudgetChart — SVG donut chart showing how the context window is allocated.
 *
 * Segments (7, no "Available" — the full window is allocated):
 *   Static:
 *   - System Prompt: measured from enabled blocks (excl. memory content)
 *   - Tool Schemas:  measured from enabled tool configs
 *   - Incoming Msgs: fixed cap (user-editable)
 *   - Image Reserve: tokens_per_image × max_images (outside context window; user-editable for Claude)
 *   Dynamic (scale with model context window):
 *   - Memory:         % of dynamic pool (user-editable)
 *   - Past Sessions:  % of dynamic pool (user-editable)
 *   - Current Session: remainder (user-editable)
 */

import { Lock } from 'lucide-react';
import type { PromptMeta } from '../../types';

// ── Token estimation (mirrors backend/prompts/assembly.py:estimate_tokens) ──

// eslint-disable-next-line react-refresh/only-export-components
export function estimateTokens(text: string): number {
  return Math.max(1, Math.floor(text.length / 4));
}

// ── Donut chart segment geometry ─────────────────────────────────────────────

interface Segment {
  label: string;
  tokens: number;
  color: string;
  group: 'static' | 'dynamic';
}

function polarToCartesian(cx: number, cy: number, r: number, angleDeg: number) {
  const rad = ((angleDeg - 90) * Math.PI) / 180;
  return { x: cx + r * Math.cos(rad), y: cy + r * Math.sin(rad) };
}

function describeArc(cx: number, cy: number, r: number, startDeg: number, endDeg: number) {
  const safeEnd = endDeg >= 360 ? 359.999 : endDeg;
  const start = polarToCartesian(cx, cy, r, safeEnd);
  const end = polarToCartesian(cx, cy, r, startDeg);
  const largeArc = endDeg - startDeg > 180 ? 1 : 0;
  return `M ${start.x} ${start.y} A ${r} ${r} 0 ${largeArc} 0 ${end.x} ${end.y}`;
}

// ── Component ─────────────────────────────────────────────────────────────────

interface ContextBudgetChartProps {
  meta: PromptMeta;
  /** When set (e.g. during block edit), use this for System Prompt segment instead of meta. */
  overrideSystemPromptTokens?: number;
}

export function ContextBudgetChart({ meta, overrideSystemPromptTokens }: ContextBudgetChartProps) {
  const total = meta.total_budget_tokens ?? meta.context_window_tokens + (meta.image_reserve_tokens ?? 0);
  const imageReserve = meta.image_reserve_tokens ?? 0;
  const systemPromptTokens = overrideSystemPromptTokens ?? meta.system_prompt_tokens;

  const segments: Segment[] = [
    // Static sections
    { label: 'System Prompt',   tokens: systemPromptTokens,                color: '#7c3aed', group: 'static' },
    { label: 'Tool Schemas',    tokens: meta.tool_schema_tokens,            color: '#ec4899', group: 'static' },
    { label: 'Incoming Msgs',   tokens: meta.incoming_msg_budget_tokens,    color: '#f59e0b', group: 'static' },
    ...(imageReserve > 0
      ? [{ label: 'Image Reserve', tokens: imageReserve, color: '#0ea5e9', group: 'static' as const }]
      : []),
    // Dynamic sections
    { label: 'Memory',          tokens: meta.memory_budget_tokens,          color: '#8b5cf6', group: 'dynamic' },
    { label: 'Past Sessions',   tokens: meta.past_session_budget_tokens,    color: '#6366f1', group: 'dynamic' },
    { label: 'Current Session', tokens: meta.current_session_budget_tokens, color: '#10b981', group: 'dynamic' },
  ];

  // Build donut path arcs
  const cx = 80;
  const cy = 80;
  const r = 64;
  const thickness = 20;

  let currentDeg = 0;
  const arcs = segments.map((seg) => {
    const sweep = total > 0 ? (seg.tokens / total) * 360 : 0;
    const startDeg = currentDeg;
    const endDeg = currentDeg + sweep;
    currentDeg = endDeg;
    return { ...seg, startDeg, endDeg, sweep };
  });

  const fmt = (n: number) =>
    n >= 1_000_000
      ? `${(n / 1_000_000).toFixed(1)}M`
      : n >= 1000
      ? `${(n / 1000).toFixed(1)}k`
      : `${n}`;

  return (
    <div className="flex flex-col gap-4">
      {/* Donut + center label */}
      <div className="flex items-center gap-6">
        <svg width={160} height={160} viewBox="0 0 160 160" className="flex-shrink-0">
          {arcs.map((arc) =>
            arc.sweep < 0.1 ? null : (
              <path
                key={arc.label}
                d={describeArc(cx, cy, r, arc.startDeg, arc.endDeg)}
                fill="none"
                stroke={arc.color}
                strokeWidth={thickness}
              />
            )
          )}
          {/* Inner circle */}
          <circle cx={cx} cy={cy} r={r - thickness} fill="var(--surface-card)" />
          {/* Center text */}
          <text
            x={cx}
            y={cy - 8}
            textAnchor="middle"
            dominantBaseline="middle"
            style={{ fontSize: 13, fontWeight: 700, fill: 'var(--text-primary)' }}
          >
            {fmt(total)}
          </text>
          <text
            x={cx}
            y={cy + 10}
            textAnchor="middle"
            dominantBaseline="middle"
            style={{ fontSize: 9, fill: 'var(--text-muted)' }}
          >
            tokens
          </text>
        </svg>

        {/* Legend */}
        <div className="flex flex-col gap-1.5 text-xs min-w-0">
          <div className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-0.5">Static</div>
          {segments.filter(s => s.group === 'static').map((seg) => (
            <div key={seg.label} className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ backgroundColor: seg.color }} />
              <span className="text-[var(--text-secondary)] truncate flex-1" title={seg.label}>{seg.label}</span>
              <span className="font-mono text-[var(--text-primary)] font-medium tabular-nums flex-shrink-0">{fmt(seg.tokens)}</span>
              <span className="text-[var(--text-muted)] tabular-nums w-9 text-right flex-shrink-0">
                {total > 0 ? `${Math.round((seg.tokens / total) * 100)}%` : '0%'}
              </span>
            </div>
          ))}
          <div className="text-[10px] font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-0.5 mt-1">Dynamic</div>
          {segments.filter(s => s.group === 'dynamic').map((seg) => (
            <div key={seg.label} className="flex items-center gap-2">
              <span className="w-2.5 h-2.5 rounded-sm flex-shrink-0" style={{ backgroundColor: seg.color }} />
              <span className="text-[var(--text-secondary)] truncate flex-1" title={seg.label}>{seg.label}</span>
              <span className="font-mono text-[var(--text-primary)] font-medium tabular-nums flex-shrink-0">{fmt(seg.tokens)}</span>
              <span className="text-[var(--text-muted)] tabular-nums w-9 text-right flex-shrink-0">
                {total > 0 ? `${Math.round((seg.tokens / total) * 100)}%` : '0%'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Token budget bars */}
      <div className="space-y-1.5">
        {segments.map((seg) => (
          <div key={seg.label}>
            <div className="flex justify-between text-xs text-[var(--text-muted)] mb-0.5">
              <span>{seg.label}</span>
              <span className="font-mono">{fmt(seg.tokens)} / {fmt(total)}</span>
            </div>
            <div className="h-1.5 bg-[var(--surface-muted)] rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{
                  width: `${Math.min(100, total > 0 ? (seg.tokens / total) * 100 : 0)}%`,
                  backgroundColor: seg.color,
                }}
              />
            </div>
          </div>
        ))}
      </div>

      {/* Image reserve note — shown when model supports vision */}
      {meta.model_supports_vision && (
        <div className="rounded-lg border border-[var(--color-info)]/20 bg-[var(--color-info)]/5 px-3 py-2.5 space-y-1">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-[var(--color-info)]">
            <Lock className="w-3 h-3 flex-shrink-0" />
            <span>Image Reserve</span>
            <span className="ml-auto font-mono font-medium">{fmt(imageReserve)}</span>
          </div>
          <p className="text-[10px] text-[var(--color-info)] leading-relaxed">
            {meta.image_effective_max_images} image{meta.image_effective_max_images !== 1 ? 's' : ''} ×{' '}
            {fmt(meta.image_tokens_per_image)} tokens/image — reserved outside the {fmt(meta.context_window_tokens)} context window.
          </p>
        </div>
      )}
    </div>
  );
}
