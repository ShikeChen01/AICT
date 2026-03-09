/**
 * KnowledgeBase — upload, list, delete, and search indexed documents.
 *
 * Minimal but fully functional panel for the Project Settings page.
 */

import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Upload,
  Trash2,
  Search,
  FileText,
  XCircle,
  Loader2,
  AlertCircle,
  Database,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import {
  uploadKnowledgeDocument,
  listKnowledgeDocuments,
  deleteKnowledgeDocument,
  searchKnowledge,
  getKnowledgeStats,
} from '../../api/client';
import type {
  KnowledgeDocument,
  KnowledgeSearchResult,
  KnowledgeStatsResponse,
} from '../../types';

// ── Helpers ──────────────────────────────────────────────────────────────

function fmtBytes(n: number): string {
  if (n >= 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`;
  if (n >= 1024) return `${(n / 1024).toFixed(0)} KB`;
  return `${n} B`;
}

function fmtDate(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    dateStyle: 'short',
    timeStyle: 'short',
  });
}

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  pending:  { label: 'Pending',  className: 'bg-yellow-100 text-yellow-800' },
  indexing: { label: 'Indexing', className: 'bg-blue-100 text-blue-800' },
  indexed:  { label: 'Indexed',  className: 'bg-green-100 text-green-800' },
  failed:   { label: 'Failed',   className: 'bg-red-100 text-red-800' },
};

// ── Props ─────────────────────────────────────────────────────────────────

interface Props {
  projectId: string;
}

// ── Component ─────────────────────────────────────────────────────────────

export function KnowledgeBase({ projectId }: Props) {
  const [docs, setDocs] = useState<KnowledgeDocument[]>([]);
  const [stats, setStats] = useState<KnowledgeStatsResponse | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState<KnowledgeSearchResult[] | null>(null);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [showSearch, setShowSearch] = useState(false);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // ── Load ─────────────────────────────────────────────────────────────

  const loadData = useCallback(async () => {
    setLoadError(null);
    try {
      const [docsData, statsData] = await Promise.all([
        listKnowledgeDocuments(projectId),
        getKnowledgeStats(projectId),
      ]);
      setDocs(docsData);
      setStats(statsData);
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : 'Failed to load knowledge base');
    }
  }, [projectId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // ── Upload ───────────────────────────────────────────────────────────

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = '';  // allow re-upload of same file

    setUploading(true);
    setUploadError(null);
    try {
      const doc = await uploadKnowledgeDocument(projectId, file);
      setDocs(prev => [doc, ...prev]);
      await loadData();  // refresh stats
    } catch (err) {
      setUploadError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  // ── Delete ───────────────────────────────────────────────────────────

  const handleDelete = async (docId: string) => {
    if (!confirm('Delete this document and all its indexed chunks?')) return;
    setDeletingId(docId);
    try {
      await deleteKnowledgeDocument(projectId, docId);
      setDocs(prev => prev.filter(d => d.id !== docId));
      await loadData();
    } catch (err) {
      alert(err instanceof Error ? err.message : 'Delete failed');
    } finally {
      setDeletingId(null);
    }
  };

  // ── Search ───────────────────────────────────────────────────────────

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    setSearching(true);
    setSearchError(null);
    setSearchResults(null);
    try {
      const res = await searchKnowledge(projectId, {
        query: searchQuery,
        limit: 10,
        similarity_threshold: 0.4,
      });
      setSearchResults(res.results);
    } catch (err) {
      setSearchError(err instanceof Error ? err.message : 'Search failed');
    } finally {
      setSearching(false);
    }
  };

  // ── Render ───────────────────────────────────────────────────────────

  return (
    <div className="space-y-5">
      {/* Stats bar */}
      {stats && (
        <div className="grid grid-cols-3 gap-3 text-center">
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
            <div className="text-2xl font-bold text-gray-900">{stats.indexed_documents}</div>
            <div className="text-xs text-gray-500 mt-0.5">Indexed docs</div>
          </div>
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
            <div className="text-2xl font-bold text-gray-900">{stats.total_chunks.toLocaleString()}</div>
            <div className="text-xs text-gray-500 mt-0.5">Chunks</div>
          </div>
          <div className="rounded-lg border border-gray-200 bg-gray-50 p-3">
            <div className="text-2xl font-bold text-gray-900">{fmtBytes(stats.total_bytes)}</div>
            <div className="text-xs text-gray-500 mt-0.5">Storage used</div>
          </div>
        </div>
      )}

      {/* Upload area */}
      <div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.txt,.md,.markdown,.csv"
          onChange={handleFileChange}
          className="hidden"
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={uploading}
          className="flex w-full items-center justify-center gap-2 rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 px-4 py-6 text-sm text-gray-600 transition hover:border-indigo-400 hover:bg-indigo-50 hover:text-indigo-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {uploading ? (
            <Loader2 className="h-5 w-5 animate-spin" />
          ) : (
            <Upload className="h-5 w-5" />
          )}
          {uploading ? 'Uploading & indexing…' : 'Click to upload PDF, TXT, Markdown, or CSV'}
        </button>
        {uploadError && (
          <div className="mt-2 flex items-center gap-1.5 text-sm text-red-600">
            <XCircle className="h-4 w-4 flex-shrink-0" />
            {uploadError}
          </div>
        )}
      </div>

      {/* Search panel (collapsible) */}
      <div className="rounded-lg border border-gray-200">
        <button
          className="flex w-full items-center justify-between px-4 py-3 text-sm font-medium text-gray-700 hover:bg-gray-50"
          onClick={() => {
            setShowSearch(s => !s);
            setSearchResults(null);
            setSearchError(null);
          }}
        >
          <span className="flex items-center gap-2">
            <Search className="h-4 w-4 text-gray-500" />
            Test Knowledge Search
          </span>
          {showSearch ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
        </button>

        {showSearch && (
          <div className="border-t border-gray-200 p-4 space-y-3">
            <div className="flex gap-2">
              <input
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
                placeholder="e.g. authentication flow, database schema…"
                className="flex-1 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
              <button
                onClick={handleSearch}
                disabled={searching || !searchQuery.trim()}
                className="flex items-center gap-1.5 rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {searching ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />}
                Search
              </button>
            </div>

            {searchError && (
              <div className="flex items-center gap-1.5 text-sm text-red-600">
                <AlertCircle className="h-4 w-4" />
                {searchError}
              </div>
            )}

            {searchResults !== null && (
              <div className="space-y-3">
                {searchResults.length === 0 ? (
                  <p className="text-sm text-gray-500">No results found. Try a broader query or lower the threshold.</p>
                ) : (
                  searchResults.map((r, i) => (
                    <div key={r.chunk_id} className="rounded-md border border-gray-200 bg-white p-3">
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-sm font-medium text-gray-800">
                          [{i + 1}] {r.filename}
                          {r.metadata?.page_num != null && (
                            <span className="text-gray-400 font-normal"> — page {String(r.metadata.page_num)}</span>
                          )}
                        </span>
                        <span className="text-xs font-semibold text-indigo-600">
                          {Math.round(r.similarity_score * 100)}% match
                        </span>
                      </div>
                      <p className="text-xs text-gray-600 leading-relaxed line-clamp-4">
                        {r.text_content}
                      </p>
                    </div>
                  ))
                )}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Document list */}
      {loadError && (
        <div className="flex items-center gap-2 text-sm text-red-600">
          <AlertCircle className="h-4 w-4" />
          {loadError}
          <button className="ml-2 underline" onClick={loadData}>Retry</button>
        </div>
      )}

      {docs.length === 0 && !loadError && (
        <div className="flex flex-col items-center gap-2 py-8 text-gray-400">
          <Database className="h-8 w-8" />
          <p className="text-sm">No documents yet — upload one above.</p>
        </div>
      )}

      {docs.length > 0 && (
        <div className="divide-y divide-gray-100 rounded-lg border border-gray-200 bg-white overflow-hidden">
          {docs.map(doc => {
            const badge = STATUS_BADGE[doc.status] ?? STATUS_BADGE.pending;
            return (
              <div key={doc.id} className="flex items-start gap-3 px-4 py-3 hover:bg-gray-50">
                <FileText className="mt-0.5 h-5 w-5 flex-shrink-0 text-gray-400" />
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium text-gray-900 truncate">{doc.filename}</span>
                    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${badge.className}`}>
                      {badge.label}
                    </span>
                    {doc.chunk_count > 0 && (
                      <span className="text-xs text-gray-400">{doc.chunk_count} chunks</span>
                    )}
                  </div>
                  <div className="mt-0.5 text-xs text-gray-400">
                    {fmtBytes(doc.original_size_bytes)} · {doc.file_type.toUpperCase()} · {fmtDate(doc.created_at)}
                  </div>
                  {doc.status === 'failed' && doc.error_message && (
                    <div className="mt-1 flex items-start gap-1 text-xs text-red-600">
                      <XCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
                      <span>{doc.error_message}</span>
                    </div>
                  )}
                </div>
                <button
                  onClick={() => handleDelete(doc.id)}
                  disabled={deletingId === doc.id}
                  className="ml-2 flex-shrink-0 rounded p-1 text-gray-400 hover:bg-red-50 hover:text-red-500 disabled:opacity-50"
                  title="Delete document"
                >
                  {deletingId === doc.id
                    ? <Loader2 className="h-4 w-4 animate-spin" />
                    : <Trash2 className="h-4 w-4" />
                  }
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
