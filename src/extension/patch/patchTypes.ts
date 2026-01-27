export interface PatchHunk {
  header: string;
  lines: string[];
}

export interface PatchFile {
  oldPath: string;
  newPath: string;
  hunks: PatchHunk[];
}

export interface Patch {
  files: PatchFile[];
}
