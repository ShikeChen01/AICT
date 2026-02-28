/**
 * MessageInput — user message composer with optional image attachment support.
 *
 * Files are collected locally and returned to the caller via onSend().
 * The caller (AgentChatView) is responsible for uploading them before sending.
 */

import {
  useRef,
  useState,
  useCallback,
  type FormEvent,
  type KeyboardEvent,
  type ChangeEvent,
} from 'react';
import { Button, Textarea } from '../ui';

const ALLOWED_MIME_TYPES = ['image/jpeg', 'image/png', 'image/gif', 'image/webp'];
const MAX_FILE_SIZE_MB = 10;
const MAX_FILES = 5;

interface PendingFile {
  file: File;
  previewUrl: string;
}

interface MessageInputProps {
  onSend: (content: string, files?: File[]) => Promise<unknown>;
  disabled?: boolean;
  isStreaming?: boolean;
}

export function MessageInput({ onSend, disabled, isStreaming }: MessageInputProps) {
  const [content, setContent] = useState('');
  const [isSending, setIsSending] = useState(false);
  const [pendingFiles, setPendingFiles] = useState<PendingFile[]>([]);
  const [fileError, setFileError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const addFiles = useCallback((files: FileList | File[]) => {
    setFileError(null);
    const next: PendingFile[] = [];
    for (const file of Array.from(files)) {
      if (!ALLOWED_MIME_TYPES.includes(file.type)) {
        setFileError(`"${file.name}" is not a supported image type (JPEG, PNG, GIF, WebP).`);
        continue;
      }
      if (file.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
        setFileError(`"${file.name}" exceeds the ${MAX_FILE_SIZE_MB} MB limit.`);
        continue;
      }
      next.push({ file, previewUrl: URL.createObjectURL(file) });
    }

    setPendingFiles((prev) => {
      const combined = [...prev, ...next].slice(0, MAX_FILES);
      // Revoke URLs that got dropped by the slice
      for (const pf of [...prev, ...next].slice(MAX_FILES)) {
        URL.revokeObjectURL(pf.previewUrl);
      }
      return combined;
    });
  }, []);

  const removeFile = useCallback((index: number) => {
    setPendingFiles((prev) => {
      URL.revokeObjectURL(prev[index].previewUrl);
      return prev.filter((_, i) => i !== index);
    });
  }, []);

  const handleFileChange = useCallback(
    (e: ChangeEvent<HTMLInputElement>) => {
      if (e.target.files) addFiles(e.target.files);
      e.target.value = '';
    },
    [addFiles]
  );

  const handlePaste = useCallback(
    (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
      const items = Array.from(e.clipboardData.items).filter(
        (item) => item.kind === 'file' && ALLOWED_MIME_TYPES.includes(item.type)
      );
      if (items.length > 0) {
        const files = items
          .map((item) => item.getAsFile())
          .filter((f): f is File => f !== null);
        if (files.length) addFiles(files);
      }
    },
    [addFiles]
  );

  const handleDrop = useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault();
      if (e.dataTransfer.files.length) addFiles(e.dataTransfer.files);
    },
    [addFiles]
  );

  const handleSubmit = useCallback(
    async (e?: FormEvent) => {
      e?.preventDefault();
      const trimmed = content.trim();
      if ((!trimmed && pendingFiles.length === 0) || isSending || disabled) return;
      if (trimmed === '' && pendingFiles.length === 0) return;
      setIsSending(true);
      try {
        await onSend(trimmed || ' ', pendingFiles.map((pf) => pf.file));
        setContent('');
        setPendingFiles((prev) => {
          prev.forEach((pf) => URL.revokeObjectURL(pf.previewUrl));
          return [];
        });
        setFileError(null);
      } catch (err) {
        console.error('Failed to send message:', err);
      } finally {
        setIsSending(false);
      }
    },
    [content, pendingFiles, isSending, disabled, onSend]
  );

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        void handleSubmit();
      }
    },
    [handleSubmit]
  );

  const isDisabled = disabled || isSending;
  const canSend = (content.trim().length > 0 || pendingFiles.length > 0) && !isDisabled;

  return (
    <div
      className="border-t border-[var(--border-color)] bg-[var(--surface-muted)] p-4"
      onDragOver={(e) => e.preventDefault()}
      onDrop={handleDrop}
    >
      {isStreaming && (
        <div className="mb-2 flex items-center gap-2 text-sm text-amber-700">
          <div className="w-2 h-2 bg-amber-500 rounded-full animate-pulse" />
          Agent is responding...
        </div>
      )}

      {/* Image previews */}
      {pendingFiles.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {pendingFiles.map((pf, i) => (
            <div key={i} className="relative group w-16 h-16 flex-shrink-0">
              <img
                src={pf.previewUrl}
                alt={pf.file.name}
                className="w-full h-full object-cover rounded-lg border border-[var(--border-color)]"
              />
              <button
                type="button"
                onClick={() => removeFile(i)}
                className="absolute -top-1.5 -right-1.5 w-5 h-5 bg-red-500 text-white rounded-full text-xs flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity"
                aria-label={`Remove ${pf.file.name}`}
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      {fileError && (
        <p className="mb-2 text-xs text-red-600">{fileError}</p>
      )}

      <form onSubmit={handleSubmit} className="flex gap-2 items-end">
        {/* Hidden file input */}
        <input
          ref={fileInputRef}
          type="file"
          accept={ALLOWED_MIME_TYPES.join(',')}
          multiple
          className="hidden"
          onChange={handleFileChange}
          disabled={isDisabled}
        />

        {/* Attach image button */}
        <button
          type="button"
          onClick={() => fileInputRef.current?.click()}
          disabled={isDisabled || pendingFiles.length >= MAX_FILES}
          title="Attach image (JPEG, PNG, GIF, WebP — max 10 MB each)"
          className="h-12 w-10 flex items-center justify-center rounded-xl border border-[var(--border-color)] bg-[var(--surface)] text-[var(--text-muted)] hover:text-[var(--text)] hover:bg-[var(--surface-hover)] disabled:opacity-40 transition-colors flex-shrink-0"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z"
            />
          </svg>
        </button>

        <Textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          onKeyDown={handleKeyDown}
          onPaste={handlePaste}
          placeholder="Type your message… (Enter to send, Shift+Enter for new line, paste or drag images)"
          disabled={isDisabled}
          rows={1}
          className="min-h-[48px] max-h-[120px] flex-1 resize-none"
        />

        <Button
          type="submit"
          disabled={!canSend}
          className="h-12 rounded-xl px-6 flex-shrink-0"
        >
          {isSending ? (
            <>
              <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24" aria-hidden>
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
              </svg>
              Sending
            </>
          ) : (
            <>
              <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
              </svg>
              Send
            </>
          )}
        </Button>
      </form>
    </div>
  );
}

export default MessageInput;
