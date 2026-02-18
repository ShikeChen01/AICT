/**
 * ActivityFeed Component
 * Displays agent activity logs (thoughts, tool calls, results)
 */

import { useEffect, useRef } from 'react';
import { format } from 'date-fns';
import { Bot, Wrench, MessageSquare, AlertCircle, ChevronDown, ChevronRight } from 'lucide-react';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism';
import { MarkdownContent } from '../MarkdownContent';
import type { AgentLogData, AgentRole } from '../../types';

interface ActivityLogItem extends AgentLogData {
  timestamp: string;
  id: string;
}

interface ActivityFeedProps {
  logs: ActivityLogItem[];
  filter?: AgentRole | 'all';
  onFilterChange?: (filter: AgentRole | 'all') => void;
  autoScroll?: boolean;
}

const logTypeIcons: Record<string, React.ReactNode> = {
  thought: <Bot className="w-4 h-4 text-purple-500" />,
  tool_call: <Wrench className="w-4 h-4 text-amber-500" />,
  tool_result: <ChevronRight className="w-4 h-4 text-green-500" />,
  message: <MessageSquare className="w-4 h-4 text-blue-500" />,
  error: <AlertCircle className="w-4 h-4 text-red-500" />,
};

const roleColors: Record<AgentRole, string> = {
  manager: 'bg-purple-100 text-purple-700 border-purple-200',
  gm: 'bg-purple-100 text-purple-700 border-purple-200',
  om: 'bg-cyan-100 text-cyan-700 border-cyan-200',
  engineer: 'bg-green-100 text-green-700 border-green-200',
};

function LogEntry({ log, expanded, onToggle }: { log: ActivityLogItem; expanded: boolean; onToggle: () => void }) {
  const hasDetails = log.tool_input || log.tool_output;

  return (
    <div className="border-b border-gray-100 last:border-0">
      <div
        className={`
          flex items-start gap-3 px-4 py-3 
          ${hasDetails ? 'cursor-pointer hover:bg-gray-50' : ''}
        `}
        onClick={hasDetails ? onToggle : undefined}
      >
        {/* Icon */}
        <div className="flex-shrink-0 mt-0.5">
          {logTypeIcons[log.log_type] || logTypeIcons.message}
        </div>

        {/* Content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={`px-2 py-0.5 text-xs font-medium rounded border ${roleColors[log.agent_role]}`}>
              {log.agent_role}
            </span>
            {log.tool_name && (
              <span className="px-2 py-0.5 text-xs font-mono bg-gray-100 text-gray-600 rounded">
                {log.tool_name}
              </span>
            )}
            <span className="text-xs text-gray-400 ml-auto">
              {format(new Date(log.timestamp), 'HH:mm:ss')}
            </span>
          </div>

          <MarkdownContent className="text-sm text-gray-700">
            {log.content}
          </MarkdownContent>
        </div>

        {/* Expand indicator */}
        {hasDetails && (
          <div className="flex-shrink-0 text-gray-400">
            {expanded ? <ChevronDown className="w-4 h-4" /> : <ChevronRight className="w-4 h-4" />}
          </div>
        )}
      </div>

      {/* Expanded details */}
      {expanded && hasDetails && (
        <div className="px-4 pb-3 pl-11 space-y-2">
          {log.tool_input && (
            <div>
              <span className="text-xs font-medium text-gray-500 uppercase">Input</span>
              <SyntaxHighlighter
                language="json"
                style={oneLight}
                customStyle={{ fontSize: '12px', borderRadius: '6px', margin: '4px 0' }}
              >
                {JSON.stringify(log.tool_input, null, 2)}
              </SyntaxHighlighter>
            </div>
          )}
          {log.tool_output && (
            <div>
              <span className="text-xs font-medium text-gray-500 uppercase">Output</span>
              <SyntaxHighlighter
                language="text"
                style={oneLight}
                customStyle={{ fontSize: '12px', borderRadius: '6px', margin: '4px 0' }}
              >
                {log.tool_output}
              </SyntaxHighlighter>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ActivityFeed({
  logs,
  filter = 'all',
  onFilterChange,
  autoScroll = true,
}: ActivityFeedProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const expandedIds = useRef<Set<string>>(new Set());

  // Auto-scroll to bottom on new logs
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs.length, autoScroll]);

  const filteredLogs = filter === 'all'
    ? logs
    : logs.filter((log) => log.agent_role === filter);

  const toggleExpanded = (id: string) => {
    if (expandedIds.current.has(id)) {
      expandedIds.current.delete(id);
    } else {
      expandedIds.current.add(id);
    }
  };

  return (
    <div className="flex flex-col h-full bg-white rounded-lg border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-200 bg-gray-50">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-gray-900">Activity Feed</h3>
          {onFilterChange && (
            <select
              value={filter}
              onChange={(e) => onFilterChange(e.target.value as AgentRole | 'all')}
              className="text-xs border border-gray-300 rounded px-2 py-1 bg-white"
            >
              <option value="all">All Agents</option>
              <option value="manager">Manager</option>
              <option value="cto">CTO</option>
              <option value="engineer">Engineer</option>
            </select>
          )}
        </div>
      </div>

      {/* Log entries */}
      <div ref={containerRef} className="flex-1 overflow-y-auto">
        {filteredLogs.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-sm text-gray-400">
            No activity yet...
          </div>
        ) : (
          filteredLogs.map((log) => (
            <LogEntry
              key={log.id}
              log={log}
              expanded={expandedIds.current.has(log.id)}
              onToggle={() => toggleExpanded(log.id)}
            />
          ))
        )}
      </div>
    </div>
  );
}

export default ActivityFeed;
