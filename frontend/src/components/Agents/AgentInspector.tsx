import { useEffect, useState } from 'react';
import { getAgentContext } from '../../api/client';
import type { AgentContext } from '../../types';

interface AgentInspectorProps {
  agentId: string | null;
  title?: string;
}

export function AgentInspector({ agentId, title = 'Agent Inspector' }: AgentInspectorProps) {
  const [context, setContext] = useState<AgentContext | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!agentId) {
      setContext(null);
      setError(null);
      return;
    }

    let cancelled = false;

    const loadContext = async () => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await getAgentContext(agentId);
        if (!cancelled) {
          setContext(data as AgentContext);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : 'Failed to load agent context');
          setContext(null);
        }
      } finally {
        if (!cancelled) {
          setIsLoading(false);
        }
      }
    };

    void loadContext();

    return () => {
      cancelled = true;
    };
  }, [agentId]);

  return (
    <section className="h-full bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-200">
        <h3 className="text-sm font-semibold text-gray-900">{title}</h3>
        <p className="text-xs text-gray-500">Inspect prompt, tools, and recent memory</p>
      </div>

      <div className="h-[calc(100%-62px)] overflow-y-auto p-4 space-y-4">
        {!agentId ? (
          <p className="text-sm text-gray-500">Select an agent node to inspect details.</p>
        ) : isLoading ? (
          <p className="text-sm text-gray-500">Loading agent context...</p>
        ) : error ? (
          <p className="text-sm text-red-600">{error}</p>
        ) : !context ? (
          <p className="text-sm text-gray-500">No context available.</p>
        ) : (
          <>
            <div className="rounded border border-gray-200 bg-gray-50 p-3">
              <p className="text-xs uppercase text-gray-500">Agent</p>
              <p className="text-sm font-medium text-gray-900">
                {context.display_name} ({context.role})
              </p>
              <p className="text-xs text-gray-600 mt-1">
                Model: {context.model} · Status: {context.status}
              </p>
              {context.sandbox_id && (
                <p className="text-xs text-gray-600 mt-1">Sandbox: {context.sandbox_id}</p>
              )}
            </div>

            <div>
              <p className="text-xs uppercase text-gray-500 mb-2">System Prompt</p>
              <pre className="text-xs text-gray-700 bg-gray-50 border border-gray-200 rounded p-3 whitespace-pre-wrap">
                {context.system_prompt || 'No system prompt available.'}
              </pre>
            </div>

            <div>
              <p className="text-xs uppercase text-gray-500 mb-2">Available Tools</p>
              {context.available_tools.length === 0 ? (
                <p className="text-sm text-gray-500">No tools listed.</p>
              ) : (
                <ul className="space-y-2">
                  {context.available_tools.map((tool) => (
                    <li key={tool.name} className="border border-gray-200 rounded p-2 bg-white">
                      <p className="text-sm font-medium text-gray-900">{tool.name}</p>
                      {tool.description && (
                        <p className="text-xs text-gray-600 mt-1">{tool.description}</p>
                      )}
                    </li>
                  ))}
                </ul>
              )}
            </div>

            <div>
              <p className="text-xs uppercase text-gray-500 mb-2">Recent Memory</p>
              {context.recent_messages.length === 0 ? (
                <p className="text-sm text-gray-500">No recent messages yet.</p>
              ) : (
                <pre className="text-xs text-gray-700 bg-gray-50 border border-gray-200 rounded p-3 whitespace-pre-wrap">
                  {JSON.stringify(context.recent_messages, null, 2)}
                </pre>
              )}
            </div>
          </>
        )}
      </div>
    </section>
  );
}

export default AgentInspector;
