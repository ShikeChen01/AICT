/**
 * Renders markdown content with GFM (tables, lists, etc.) for agent output.
 * Used in chat bubbles and activity logs. Styled for compact display.
 */

import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import type { Components } from 'react-markdown';

const compactComponents: Components = {
  p: ({ children }) => <p className="mb-2 last:mb-0 text-sm leading-relaxed">{children}</p>,
  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
  code: ({ children, className }) => {
    const isBlock = className != null;
    if (isBlock) {
      return (
        <code className="block my-1 px-2 py-1 rounded bg-gray-100 text-xs font-mono overflow-x-auto">
          {children}
        </code>
      );
    }
    return <code className="px-1 rounded bg-gray-100 text-xs font-mono">{children}</code>;
  },
  ul: ({ children }) => <ul className="my-2 ml-4 list-disc space-y-0.5 text-sm">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 ml-4 list-decimal space-y-0.5 text-sm">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  table: ({ children }) => (
    <div className="my-2 overflow-x-auto">
      <table className="min-w-full border border-gray-200 text-xs">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-gray-100">{children}</thead>,
  tbody: ({ children }) => <tbody className="divide-y divide-gray-200">{children}</tbody>,
  tr: ({ children }) => <tr className="divide-x divide-gray-200">{children}</tr>,
  th: ({ children }) => (
    <th className="px-2 py-1.5 text-left font-medium text-gray-700 border-gray-200">
      {children}
    </th>
  ),
  td: ({ children }) => <td className="px-2 py-1.5 text-gray-800 border-gray-200">{children}</td>,
  h1: ({ children }) => <h1 className="text-base font-semibold mt-2 mb-1 first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="text-sm font-semibold mt-2 mb-1 first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="text-sm font-medium mt-2 mb-1 first:mt-0">{children}</h3>,
};

export interface MarkdownContentProps {
  children: string;
  className?: string;
}

export function MarkdownContent({ children, className = '' }: MarkdownContentProps) {
  if (!children?.trim()) {
    return null;
  }
  return (
    <div className={`markdown-content break-words ${className}`.trim()}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={compactComponents}>
        {children}
      </ReactMarkdown>
    </div>
  );
}

export default MarkdownContent;
