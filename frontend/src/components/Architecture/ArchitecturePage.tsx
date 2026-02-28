/**
 * ArchitecturePage — read-only view of per-project architecture documents.
 *
 * Documents are written exclusively by the manager agent via write_architecture_doc.
 * Users can read documents and chat with the manager via the floating overlay.
 * The page re-fetches documents in real-time on DOCUMENT_UPDATED WebSocket events.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import { createWebSocketClient, getAgents, getDocument, listDocuments, sendMessage } from '../../api/client';
import type { Agent, DocumentUpdatedData, ProjectDocument, ProjectDocumentSummary } from '../../types';

const DOC_TYPE_LABELS: Record<string, string> = {
  architecture_source_of_truth: 'Source of Truth',
  arc42_lite: 'arc42-lite',
  c4_diagrams: 'C4 Diagrams',
};

function docLabel(docType: string): string {
  if (DOC_TYPE_LABELS[docType]) return DOC_TYPE_LABELS[docType];
  if (docType.startsWith('adr/')) return `ADR: ${docType.slice(4)}`;
  return docType;
}

const EMPTY_STATE_PLACEHOLDERS: Record<string, string> = {
  architecture_source_of_truth: `# Architecture Source of Truth

*This document has not been written yet.*

Ask the manager agent to document the system architecture here.
Example: "Please write the architecture source of truth for this project."`,

  arc42_lite: `# arc42-lite

*This document has not been written yet.*

Ask the manager agent to fill out the arc42-lite template.`,

  c4_diagrams: `# C4 Diagrams

*No diagrams yet.*

Ask the manager agent to create C4 diagrams using Mermaid fenced blocks.`,
};

function emptyPlaceholder(docType: string): string {
  if (EMPTY_STATE_PLACEHOLDERS[docType]) return EMPTY_STATE_PLACEHOLDERS[docType];
  if (docType.startsWith('adr/')) {
    return `# ${docType}\n\n*This ADR has not been written yet.*`;
  }
  return `*No content yet for "${docType}".*`;
}

// ── Floating chat bar ─────────────────────────────────────────────────────────

interface FloatingChatBarProps {
  projectId: string;
  managerAgent: Agent | null;
}

function FloatingChatBar({ projectId, managerAgent }: FloatingChatBarProps) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [sent, setSent] = useState(false);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (open) textareaRef.current?.focus();
  }, [open]);

  const handleSend = async () => {
    if (!text.trim() || !managerAgent || sending) return;
    setSending(true);
    try {
      await sendMessage({
        project_id: projectId,
        target_agent_id: managerAgent.id,
        content: text.trim(),
      });
      setText('');
      setSent(true);
      setTimeout(() => {
        setSent(false);
        setOpen(false);
      }, 1500);
    } catch (err) {
      console.error('[ArchitecturePage] send failed', err);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-2">
      {open && (
        <div className="w-80 rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
          <div className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
            <span className="text-sm font-semibold text-white">Chat with Manager</span>
            <button
              onClick={() => setOpen(false)}
              className="text-slate-400 hover:text-white"
              aria-label="Close"
            >
              ✕
            </button>
          </div>
          <div className="p-3">
            {sent ? (
              <p className="py-2 text-center text-sm text-green-400">Message sent.</p>
            ) : (
              <>
                <textarea
                  ref={textareaRef}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  onKeyDown={handleKeyDown}
                  rows={3}
                  placeholder="Ask the manager to update architecture docs…"
                  className="w-full resize-none rounded-lg border border-slate-600 bg-slate-800 px-3 py-2 text-sm text-white placeholder-slate-500 focus:border-blue-500 focus:outline-none"
                  disabled={sending}
                />
                <div className="mt-2 flex items-center justify-between">
                  <span className="text-xs text-slate-500">⏎ to send, Shift+⏎ for newline</span>
                  <button
                    onClick={() => void handleSend()}
                    disabled={!text.trim() || sending || !managerAgent}
                    className="rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500 disabled:opacity-40"
                  >
                    {sending ? 'Sending…' : 'Send'}
                  </button>
                </div>
                {!managerAgent && (
                  <p className="mt-1 text-xs text-amber-400">No manager agent found in this project.</p>
                )}
              </>
            )}
          </div>
        </div>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-full bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white shadow-lg hover:bg-blue-500 active:scale-95 transition-transform"
      >
        <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z" />
        </svg>
        Chat with Manager
      </button>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

interface ArchitecturePageProps {
  projectId: string;
}

export function ArchitecturePage({ projectId }: ArchitecturePageProps) {
  const [summaries, setSummaries] = useState<ProjectDocumentSummary[]>([]);
  const [activeDocType, setActiveDocType] = useState<string>('architecture_source_of_truth');
  const [document, setDocument] = useState<ProjectDocument | null>(null);
  const [loadingDoc, setLoadingDoc] = useState(false);
  const [loadingList, setLoadingList] = useState(true);
  const [agents, setAgents] = useState<Agent[]>([]);

  const managerAgent = agents.find((a) => a.role === 'manager') ?? null;

  const fetchList = useCallback(async () => {
    setLoadingList(true);
    try {
      const docs = await listDocuments(projectId);
      setSummaries(docs);
    } catch (err) {
      console.error('[ArchitecturePage] listDocuments failed', err);
    } finally {
      setLoadingList(false);
    }
  }, [projectId]);

  const fetchDoc = useCallback(async (docType: string) => {
    setLoadingDoc(true);
    setDocument(null);
    try {
      const doc = await getDocument(projectId, docType);
      setDocument(doc);
    } catch (err: unknown) {
      // 404 is expected when no content written yet
      if ((err as { status?: number }).status !== 404) {
        console.error('[ArchitecturePage] getDocument failed', err);
      }
      setDocument(null);
    } finally {
      setLoadingDoc(false);
    }
  }, [projectId]);

  // Initial load
  useEffect(() => {
    void fetchList();
    getAgents(projectId).then(setAgents).catch(console.error);
  }, [fetchList, projectId]);

  useEffect(() => {
    void fetchDoc(activeDocType);
  }, [fetchDoc, activeDocType]);

  // Real-time: lightweight WS subscription for document_updated only
  const activeDocTypeRef = useRef(activeDocType);
  activeDocTypeRef.current = activeDocType;

  useEffect(() => {
    const client = createWebSocketClient(projectId, 'documents');
    client.connect();
    const unsub = client.subscribe((event) => {
      if (event.type !== 'document_updated') return;
      const data = event.data as DocumentUpdatedData;
      if (data.project_id !== projectId) return;
      void fetchList();
      if (data.doc_type === activeDocTypeRef.current) {
        void fetchDoc(activeDocTypeRef.current);
      }
    });
    return () => {
      unsub();
      client.disconnect();
    };
  }, [projectId, fetchList, fetchDoc]);

  // Build tab list: fixed well-known types + any extras from the DB
  const defaultTypes = ['architecture_source_of_truth', 'arc42_lite', 'c4_diagrams'];
  const extraTypes = summaries
    .map((s) => s.doc_type)
    .filter((t) => !defaultTypes.includes(t));
  const allTypes = [...defaultTypes, ...extraTypes];

  return (
    <div className="flex h-full min-h-0 flex-col">
      {/* Tab bar */}
      <div className="flex items-center gap-1 overflow-x-auto border-b border-slate-800 bg-slate-950 px-4 pt-3">
        {allTypes.map((dt) => {
          const hasContent = summaries.some((s) => s.doc_type === dt);
          return (
            <button
              key={dt}
              onClick={() => setActiveDocType(dt)}
              className={[
                'flex-shrink-0 rounded-t-lg px-4 py-2 text-sm font-medium transition-colors',
                activeDocType === dt
                  ? 'border-b-2 border-blue-500 bg-slate-900 text-white'
                  : 'text-slate-400 hover:text-slate-200',
              ].join(' ')}
            >
              {docLabel(dt)}
              {!hasContent && (
                <span className="ml-1.5 rounded-full bg-slate-700 px-1.5 py-0.5 text-[10px] text-slate-400">
                  empty
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Document content */}
      <div className="flex-1 overflow-y-auto bg-slate-900 px-8 py-6">
        {loadingList || loadingDoc ? (
          <div className="flex h-full items-center justify-center text-slate-400">Loading…</div>
        ) : (
          <article className="prose prose-invert prose-slate max-w-4xl">
            <ReactMarkdown>
              {document?.content ?? emptyPlaceholder(activeDocType)}
            </ReactMarkdown>
          </article>
        )}
      </div>

      {/* Floating chat bar */}
      <FloatingChatBar projectId={projectId} managerAgent={managerAgent} />
    </div>
  );
}

export default ArchitecturePage;
