import * as fs from 'fs/promises';
import * as path from 'path';
import { getWorkspaceFilePath } from './storagePaths';
import { WorkspaceStateSchema } from '../../shared/schemas/entitySchema';
import type { WorkspaceState } from './storageTypes';
import { StorageError } from './storageTypes';

const defaultState: WorkspaceState = {
  entities: [],
  canvas: undefined
};

/**
 * Load and validate workspace state from .vibecanvas.json.
 * Returns default state if file is missing or invalid.
 */
export async function loadWorkspaceState(root: string): Promise<WorkspaceState> {
  const filePath = getWorkspaceFilePath(root);
  try {
    const raw = await fs.readFile(filePath, 'utf-8');
    const json = JSON.parse(raw) as unknown;
    const parsed = WorkspaceStateSchema.safeParse(json);
    if (!parsed.success) {
      return defaultState;
    }
    return parsed.data as WorkspaceState;
  } catch (err) {
    const nodeErr = err as NodeJS.ErrnoException;
    if (nodeErr?.code === 'ENOENT') {
      return defaultState;
    }
    throw new StorageError(
      `Failed to load workspace state: ${nodeErr?.message ?? err}`,
      'LOAD_FAILED',
      err
    );
  }
}

/**
 * Validate state, write atomically (temp file + rename), then resolve.
 */
export async function saveWorkspaceState(
  root: string,
  state: WorkspaceState
): Promise<void> {
  const filePath = getWorkspaceFilePath(root);
  const parsed = WorkspaceStateSchema.safeParse(state);
  if (!parsed.success) {
    throw new StorageError(
      `Invalid workspace state: ${parsed.error.message}`,
      'VALIDATION_FAILED'
    );
  }
  const dir = path.dirname(filePath);
  const tempPath = path.join(dir, `.vibecanvas.json.${Date.now()}.tmp`);
  try {
    await fs.mkdir(dir, { recursive: true });
    await fs.writeFile(tempPath, JSON.stringify(parsed.data, null, 2), 'utf-8');
    await fs.rename(tempPath, filePath);
  } catch (err) {
    const nodeErr = err as NodeJS.ErrnoException;
    try {
      await fs.unlink(tempPath).catch(() => {});
    } catch {
      // ignore
    }
    throw new StorageError(
      `Failed to save workspace state: ${nodeErr?.message ?? err}`,
      'SAVE_FAILED',
      err
    );
  }
}
