type DiffHunk = {
  old_start: number;
  old_lines: number;
  new_start: number;
  new_lines: number;
  header?: string;
  lines: string[];
};

type DiffFile = {
  old_path: string;
  new_path: string;
  hunks: DiffHunk[];
  is_new?: boolean;
  is_deleted?: boolean;
};

type UnifiedDiff = {
  text: string;
  files: DiffFile[];
};

export type { UnifiedDiff, DiffFile, DiffHunk };
