export type PatchHunk = {
  header?: string;
  oldStart: number;
  oldLines: number;
  newStart: number;
  newLines: number;
  lines: string[];
};

export type PatchFile = {
  oldPath: string;
  newPath: string;
  hunks: PatchHunk[];
  isNew?: boolean;
  isDeleted?: boolean;
};

export type Patch = {
  files: PatchFile[];
};
