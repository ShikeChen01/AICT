import { useEffect, useMemo, useRef, useState } from 'react';
import { Button } from '../ui';
import type { BackendLogItem } from '../../types';

const MAX_BACKEND_LOGS = 1000;

interface BackendLogsViewProps {
  logs: BackendLogItem[];
  onClear: () => void;
}

type LogLevelFilter = 'all' | 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';

const levelClass: Record<string, string> = {
  DEBUG: 'bg-slate-100 text-slate-700 border-slate-200',
  INFO: 'bg-blue-100 text-blue-700 border-blue-200',
  WARNING: 'bg-amber-100 text-amber-700 border-amber-200',
  ERROR: 'bg-red-100 text-red-700 border-red-200',
  CRITICAL: 'bg-rose-100 text-rose-700 border-rose-200',
};

export function BackendLogsView({ logs, onClear }: BackendLogsViewProps) {
  const [level, setLevel] = useState<LogLevelFilter>('all');
  const [query, setQuery] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!autoScroll) return;
    const el = containerRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [logs.length, autoScroll]);

  const filteredLogs = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    return logs.filter((log) => {
      const levelMatch = level === 'all' || log.level === level;
      if (!levelMatch) return false;
      if (!normalizedQuery) return true;
      return (
        log.logger.toLowerCase().includes(normalizedQuery) ||
        log.message.toLowerCase().includes(normalizedQuery) ||
        log.level.toLowerCase().includes(normalizedQuery)
      );
    });
  }, [logs, level, query]);

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden rounded-xl border border-[var(--border-color)] bg-[var(--surface-card)] shadow-sm">
      <div className="flex items-center justify-between gap-3 border-b border-[var(--border-color)] px-5 py-4">
        <div>
          <h2 className="text-base font-semibold text-[var(--text-primary)]">Backend logs</h2>
          <p className="mt-0.5 text-xs text-[var(--text-muted)]">
            Realtime backend application logs over websocket{' '}
            <span className={logs.length >= MAX_BACKEND_LOGS ? 'font-semibold text-amber-500' : ''}>
              ({logs.length} / {MAX_BACKEND_LOGS} buffered{logs.length >= MAX_BACKEND_LOGS ? ' - oldest dropped' : ''})
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

      <div className="grid grid-cols-1 gap-3 border-b border-[var(--border-color)] px-5 py-3 md:grid-cols-[160px_1fr]">
        <select
          value={level}
          onChange={(e) => setLevel(e.target.value as LogLevelFilter)}
          className="h-10 rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] px-3 text-sm text-[var(--text-primary)]"
        >
          <option value="all">All levels</option>
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARNING">WARNING</option>
          <option value="ERROR">ERROR</option>
          <option value="CRITICAL">CRITICAL</option>
        </select>
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search logger or message"
          className="h-10 rounded-lg border border-[var(--border-color)] bg-[var(--surface-card)] px-3 text-sm text-[var(--text-primary)]"
        />
      </div>

      <div ref={containerRef} className="min-h-0 flex-1 overflow-y-auto">
        {filteredLogs.length === 0 ? (
          <div className="flex h-32 items-center justify-center text-sm text-[var(--text-muted)]">
            No backend logs received yet.
          </div>
        ) : (
          <div className="divide-y divide-[var(--border-color)]">
            {filteredLogs.map((log) => (
              <div key={log.seq} className="px-5 py-3">
                <div className="mb-1 flex items-center gap-2">
                  <span className={`rounded border px-2 py-0.5 text-[11px] font-semibold ${levelClass[log.level] ?? levelClass.INFO}`}>
                    {log.level}
                  </span>
                  <span className="font-mono text-xs text-[var(--text-muted)]">{new Date(log.ts).toLocaleTimeString()}</span>
                  <span className="font-mono text-xs text-[var(--text-muted)]">{log.logger}</span>
                </div>
                <pre className="whitespace-pre-wrap break-words font-mono text-xs text-[var(--text-primary)]">
                  {log.message}
                </pre>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

export default BackendLogsView;
