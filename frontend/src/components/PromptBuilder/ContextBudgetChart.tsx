/**
 * ContextBudgetChart — SVG donut chart showing how the 200k context window is allocated.
 *
 * Segments:
 *   - System Prompt: sum of all enabled blocks' estimated tokens
 *   - History:       60% of conversation budget (~114k tokens)
 *   - Tool Results:  30% of conversation budget (~57k tokens)
 *   - Messages:      incoming messages budget (~8k tokens)
 *   - Available:     remainder
 */

import type { PromptMeta, PromptBlockConfig } from '../../types';

// ── Token estimation (mirrors backend/prompts/assembly.py:estimate_tokens) ──

export function estimateTokens(text: string): number {
  return Math.max(1, Math.floor(text.length / 4));
}

// ── Donut chart segment geometry ─────────────────────────────────────────────

interface Segment {
  label: string;
  tokens: number;
  color: string;
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
  blocks: PromptBlockConfig[];
}

export function ContextBudgetChart({ meta, blocks }: ContextBudgetChartProps) {
  const total = meta.context_window_tokens;

  const systemTokens = blocks
    .filter((b) => b.enabled)
    .reduce((sum, b) => sum + estimateTokens(b.content), 0);

  const historyTokens = meta.budgets['history']?.tokens ?? 0;
  const toolTokens = meta.budgets['tool_results']?.tokens ?? 0;
  const msgTokens = meta.budgets['incoming_messages']?.tokens ?? 0;
  const allocatedTokens = systemTokens + historyTokens + toolTokens + msgTokens;
  const availableTokens = Math.max(0, total - allocatedTokens);

  const segments: Segment[] = [
    { label: 'System Prompt', tokens: systemTokens, color: '#7c3aed' },
    { label: 'History',       tokens: historyTokens, color: '#3b82f6' },
    { label: 'Tool Results',  tokens: toolTokens,    color: '#10b981' },
    { label: 'Messages',      tokens: msgTokens,     color: '#f59e0b' },
    { label: 'Available',     tokens: availableTokens, color: '#e5e7eb' },
  ];

  // Build donut path arcs
  const cx = 80;
  const cy = 80;
  const r = 64;
  const thickness = 20;
  const innerR = r - thickness;

  let currentDeg = 0;
  const arcs = segments.map((seg) => {
    const sweep = (seg.tokens / total) * 360;
    const startDeg = currentDeg;
    const endDeg = currentDeg + sweep;
    currentDeg = endDeg;
    return { ...seg, startDeg, endDeg, sweep };
  });

  const fmt = (n: number) =>
    n >= 1000 ? `${(n / 1000).toFixed(1)}k` : `${n}`;

  return (
    <div className="flex flex-col gap-4">
      {/* Donut + center label */}
      <div className="flex items-center gap-6">
        <svg width={160} height={160} viewBox="0 0 160 160" className="flex-shrink-0">
          {/* Outer donut ring (segments) */}
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
          {/* Inner circle to create donut hole */}
          <circle cx={cx} cy={cy} r={innerR} fill="white" />
          {/* Center text */}
          <text
            x={cx}
            y={cy - 8}
            textAnchor="middle"
            dominantBaseline="middle"
            className="text-xs font-bold fill-gray-800"
            style={{ fontSize: 13, fontWeight: 700, fill: '#1f2937' }}
          >
            {fmt(total)}
          </text>
          <text
            x={cx}
            y={cy + 10}
            textAnchor="middle"
            dominantBaseline="middle"
            style={{ fontSize: 9, fill: '#6b7280' }}
          >
            tokens
          </text>
        </svg>

        {/* Legend */}
        <div className="flex flex-col gap-1.5 text-xs min-w-0">
          {segments.map((seg) => (
            <div key={seg.label} className="flex items-center gap-2">
              <span
                className="w-2.5 h-2.5 rounded-sm flex-shrink-0"
                style={{ backgroundColor: seg.color }}
              />
              <span className="text-gray-600 truncate flex-1">{seg.label}</span>
              <span className="font-mono text-gray-800 font-medium tabular-nums">
                {fmt(seg.tokens)}
              </span>
              <span className="text-gray-400 tabular-nums w-9 text-right">
                {total > 0 ? `${Math.round((seg.tokens / total) * 100)}%` : '0%'}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Token budget bars */}
      <div className="space-y-1.5">
        {segments.filter((s) => s.label !== 'Available').map((seg) => (
          <div key={seg.label}>
            <div className="flex justify-between text-xs text-gray-500 mb-0.5">
              <span>{seg.label}</span>
              <span className="font-mono">{fmt(seg.tokens)} / {fmt(total)}</span>
            </div>
            <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full rounded-full transition-all duration-300"
                style={{
                  width: `${Math.min(100, (seg.tokens / total) * 100)}%`,
                  backgroundColor: seg.color,
                }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
