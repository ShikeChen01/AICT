export interface DiffHunk {
  header: string;
  lines: string[];
}

export interface DiffFile {
  oldPath: string;
  newPath: string;
  hunks: DiffHunk[];
}

export interface UnifiedDiff {
  files: DiffFile[];
}
