/**
 * ArchitecturePage — view, edit, and version-control per-project architecture documents.
 *
 * Users can:
 * - Read documents (rendered markdown)
 * - Switch to edit mode and save changes (creates a version snapshot)
 * - Browse version history and revert to any past version
 * - Chat with the manager agent to have it update docs
 *
 * Documents are also written by the manager agent via write_architecture_doc.
 * Real-time: WebSocket document_updated events trigger refetches.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  createWebSocketClient,
  getAgents,
  getDocument,
  listDocuments,
  sendMessage,
  editDocument,
  listDocumentVersions,
  getDocumentVersion,
  revertDocument,
} from '../../api/client';
import type {
  Agent,
  DocumentUpdatedData,
  DocumentVersionSummary,
  ProjectDocument,
  ProjectDocumentSummary,
} from '../../types';
import {
  Edit3,
  Eye,
  History,
  RotateCcw,
  Save,
  X,
  Loader2,
  ChevronRight,
} from 'lucide-react';

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
  architecture_source_of_truth: `# Architecture Source of Truth\n\n*This document has not been written yet.*\n\nAsk the manager agent to document the system architecture here.\nExample: "Please write the architecture source of truth for this project."`,
  arc42_lite: `# arc42-lite\n\n*This document has not been written yet.*\n\nAsk the manager agent to fill out the arc42-lite template.`,
  c4_diagrams: `# C4 Diagrams\n\n*No diagrams yet.*\n\nAsk the manager agent to create C4 diagrams using Mermaid fenced blocks.`,
};

function emptyPlaceholder(docType: string): string {
  if (EMPTY_STATE_PLACEHOLDERS[docType]) return EMPTY_STATE_PLACEHOLDERS[docType];
  if (docType.startsWith('adr/')) return `# ${docType}\n\n*This ADR has not been written yet.*`;
  return `*No content yet for "${docType}".*`;
}

function fmtAuthor(v: DocumentVersionSummary): string {
  if (v.edited_by_user_id) return 'You (user)';
  if (v.edited_by_agent_id) return 'Agent';
  return 'Unknown';
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
      await sendMessage({ project_id: projectId, target_agent_id: managerAgent.id, content: text.trim() });
      setText('');
      setSent(true);
      setTimeout(() => { setSent(false); setOpen(false); }, 1500);
    } catch (err) {
      console.error('[ArchitecturePage] send failed', err);
    } finally {
      setSending(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void handleSend(); }
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col items-end gap-2">
      {open && (
        <div className="w-80 rounded-xl border border-slate-700 bg-slate-900 shadow-2xl">
          <div className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
            <span className="text-sm font-semibold text-white">Chat with Manager</span>
            <button onClick={() => setOpen(false)} className="text-slate-400 hover:text-white" aria-label="Close">✕</button>
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
                {!managerAgent && <p className="mt-1 text-xs text-amber-400">No manager agent found.</p>}
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

// ── Version History Sidebar ───────────────────────────────────────────────────

interface VersionHistoryProps {
  projectId: string;
  docType: string;
  currentVersion: number;
  onPreview: (versionNumber: number, content: string) => void;
  onRevert: (versionNumber: number) => Promise<void>;
  onClose: () => void;
}

function VersionHistory({ projectId, docType, currentVersion, onPreview, onRevert, onClose }: VersionHistoryProps) {
  const [versions, setVersions] = useState<DocumentVersionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [reverting, setReverting] = useState<number | null>(null);
  const [previewingVersion, setPreviewingVersion] = useState<number | null>(null);

  useEffect(() => {
    setLoading(true);
    listDocumentVersions(projectId, docType)
      .then(setVersions)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [projectId, docType]);

  const handlePreview = async (vn: number) => {
    if (previewingVersion === vn) {
      setPreviewingVersion(null);
      return;
    }
    try {
      const version = await getDocumentVersion(projectId, docType, vn);
      setPreviewingVersion(vn);
      onPreview(vn, version.content ?? '');
    } catch (err) {
      console.error('Failed to load version', err);
    }
  };

  const handleRevert = async (vn: number) => {
    if (!confirm(`Revert to version ${vn}? This creates a new version — the current content is preserved in history.`)) return;
    setReverting(vn);
    try {
      await onRevert(vn);
    } finally {
      setReverting(null);
    }
  };

  return (
    <div className="w-72 flex-shrink-0 border-l border-slate-800 bg-slate-950 flex flex-col">
      <div className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-slate-400" />
          <span className="text-sm font-semibold text-slate-200">Version History</span>
        </div>
        <button onClick={onClose} className="text-slate-500 hover:text-slate-300">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {loading && (
          <div className="flex items-center gap-2 p-4 text-slate-500">
            <Loader2 className="w-4 h-4 animate-spin" />
            <span className="text-sm">Loading…</span>
          </div>
        )}
        {!loading && versions.length === 0 && (
          <p className="text-sm text-slate-500 p-4">No version history yet.</p>
        )}
        {versions.map((v) => (
          <div
            key={v.id}
            className={`rounded-lg border px-3 py-2 text-sm cursor-pointer transition-colors ${
              previewingVersion === v.version_number
                ? 'border-blue-500 bg-slate-800'
                : v.version_number === currentVersion
                ? 'border-slate-600 bg-slate-900'
                : 'border-transparent hover:border-slate-700 hover:bg-slate-900'
            }`}
          >
            <div className="flex items-center justify-between mb-0.5">
              <span className="font-medium text-slate-200">v{v.version_number}</span>
              {v.version_number === currentVersion && (
                <span className="text-xs text-blue-400 font-medium">current</span>
              )}
            </div>
            <div className="text-xs text-slate-500 mb-1">
              {fmtAuthor(v)} · {new Date(v.created_at).toLocaleString()}
            </div>
            {v.edit_summary && (
              <div className="text-xs text-slate-400 truncate mb-2">{v.edit_summary}</div>
            )}
            <div className="flex gap-2">
              <button
                onClick={() => void handlePreview(v.version_number)}
                className="text-xs text-blue-400 hover:text-blue-300 flex items-center gap-1"
              >
                <Eye className="w-3 h-3" />
                {previewingVersion === v.version_number ? 'Close' : 'Preview'}
              </button>
              {v.version_number !== currentVersion && (
                <button
                  onClick={() => void handleRevert(v.version_number)}
                  disabled={reverting === v.version_number}
                  className="text-xs text-orange-400 hover:text-orange-300 flex items-center gap-1 disabled:opacity-40"
                >
                  {reverting === v.version_number ? (
                    <Loader2 className="w-3 h-3 animate-spin" />
                  ) : (
                    <RotateCcw className="w-3 h-3" />
                  )}
                  Revert
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
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

  // Edit mode
  const [editMode, setEditMode] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [editSummary, setEditSummary] = useState('');
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Version history
  const [showHistory, setShowHistory] = useState(false);
  const [previewContent, setPreviewContent] = useState<string | null>(null);

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
    setEditMode(false);
    setPreviewContent(null);
    try {
      const doc = await getDocument(projectId, docType);
      setDocument(doc);
    } catch (err: unknown) {
      if ((err as { status?: number }).status !== 404) {
        console.error('[ArchitecturePage] getDocument failed', err);
      }
      setDocument(null);
    } finally {
      setLoadingDoc(false);
    }
  }, [projectId]);

  useEffect(() => { void fetchList(); getAgents(projectId).then(setAgents).catch(console.error); }, [fetchList, projectId]);
  useEffect(() => { void fetchDoc(activeDocType); }, [fetchDoc, activeDocType]);

  // Real-time WS subscription
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
      if (data.doc_type === activeDocTypeRef.current) void fetchDoc(activeDocTypeRef.current);
    });
    return () => { unsub(); client.disconnect(); };
  }, [projectId, fetchList, fetchDoc]);

  const handleEnterEdit = () => {
    setEditContent(document?.content ?? '');
    setEditSummary('');
    setSaveError(null);
    setEditMode(true);
  };

  const handleSaveEdit = async () => {
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await editDocument(projectId, activeDocType, {
        content: editContent,
        edit_summary: editSummary.trim() || undefined,
      });
      setDocument(updated);
      setEditMode(false);
      setPreviewContent(null);
      void fetchList();
    } catch (err: unknown) {
      setSaveError(err instanceof Error ? err.message : 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleRevert = async (versionNumber: number) => {
    const reverted = await revertDocument(projectId, activeDocType, versionNumber);
    setDocument(reverted);
    setPreviewContent(null);
    setShowHistory(false);
    void fetchList();
  };

  const contentToShow = previewContent ?? document?.content ?? null;

  // Build tab list
  const defaultTypes = ['architecture_source_of_truth', 'arc42_lite', 'c4_diagrams'];
  const extraTypes = summaries.map((s) => s.doc_type).filter((t) => !defaultTypes.includes(t));
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

      {/* Toolbar */}
      {!editMode && (
        <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950 px-6 py-2">
          <div className="flex items-center gap-1 text-xs text-slate-500">
            {document?.updated_by_user_id && <span>Last edited by user</span>}
            {document?.updated_by_agent_id && !document?.updated_by_user_id && <span>Last edited by agent</span>}
            {document && <span>· v{document.current_version}</span>}
            {previewContent !== null && (
              <span className="ml-2 text-orange-400 font-medium flex items-center gap-1">
                <Eye className="w-3 h-3" /> Previewing old version
              </span>
            )}
          </div>
          <div className="flex items-center gap-2">
            {previewContent !== null && (
              <button
                onClick={() => setPreviewContent(null)}
                className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-200"
              >
                <X className="w-3 h-3" /> Exit preview
              </button>
            )}
            <button
              onClick={() => setShowHistory(!showHistory)}
              className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                showHistory ? 'bg-slate-700 text-slate-200' : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800'
              }`}
            >
              <History className="w-3.5 h-3.5" />
              History
            </button>
            <button
              onClick={handleEnterEdit}
              className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-500"
            >
              <Edit3 className="w-3.5 h-3.5" />
              Edit
            </button>
          </div>
        </div>
      )}

      {/* Edit toolbar */}
      {editMode && (
        <div className="flex items-center justify-between border-b border-slate-800 bg-slate-950 px-6 py-2">
          <input
            value={editSummary}
            onChange={(e) => setEditSummary(e.target.value)}
            placeholder="Edit summary (optional)…"
            className="rounded border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-blue-500 w-64"
          />
          <div className="flex items-center gap-2">
            {saveError && <span className="text-xs text-red-400">{saveError}</span>}
            <button
              onClick={() => setEditMode(false)}
              className="flex items-center gap-1.5 text-xs text-slate-400 hover:text-slate-200"
            >
              <X className="w-3.5 h-3.5" />
              Cancel
            </button>
            <button
              onClick={() => void handleSaveEdit()}
              disabled={saving}
              className="flex items-center gap-1.5 rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-500 disabled:opacity-50"
            >
              {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              Save
            </button>
          </div>
        </div>
      )}

      {/* Main content area */}
      <div className="flex flex-1 min-h-0">
        {/* Document content */}
        <div className="flex-1 overflow-y-auto bg-slate-900 px-8 py-6">
          {loadingList || loadingDoc ? (
            <div className="flex h-full items-center justify-center text-slate-400">
              <Loader2 className="w-5 h-5 animate-spin mr-2" />
              Loading…
            </div>
          ) : editMode ? (
            <textarea
              value={editContent}
              onChange={(e) => setEditContent(e.target.value)}
              className="w-full h-full min-h-[calc(100vh-16rem)] resize-none rounded-lg border border-slate-700 bg-slate-800 px-6 py-4 font-mono text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Write markdown here…"
              autoFocus
            />
          ) : (
            <article className="prose prose-invert prose-slate max-w-4xl text-slate-200 prose-headings:text-slate-100 prose-p:text-slate-200 prose-li:text-slate-200 prose-strong:text-slate-100">
              <ReactMarkdown>
                {contentToShow ?? emptyPlaceholder(activeDocType)}
              </ReactMarkdown>
            </article>
          )}
        </div>

        {/* Version history sidebar */}
        {showHistory && !editMode && (
          <VersionHistory
            projectId={projectId}
            docType={activeDocType}
            currentVersion={document?.current_version ?? 1}
            onPreview={(_, content) => setPreviewContent(content)}
            onRevert={handleRevert}
            onClose={() => { setShowHistory(false); setPreviewContent(null); }}
          />
        )}
      </div>

      {/* Floating chat bar */}
      <FloatingChatBar projectId={projectId} managerAgent={managerAgent} />
    </div>
  );
}

export default ArchitecturePage;
