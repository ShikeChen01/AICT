import { useCallback } from 'react';
import { useAppStore } from '../store/appStore';
import type { OnSelectionChangeFunc } from 'reactflow';

/**
 * Sync React Flow selection to appStore.selectedEntityId.
 */
export function useSelectionController(): OnSelectionChangeFunc {
  const setSelectedEntity = useAppStore((s) => s.setSelectedEntity);

  return useCallback<OnSelectionChangeFunc>(
    ({ nodes }) => {
      const selected = nodes.filter((n) => n.selected);
      if (selected.length === 1) {
        setSelectedEntity(selected[0].id);
      } else if (selected.length === 0) {
        setSelectedEntity(null);
      }
      // Multi-select: keep first selected node as "active" for inspector
      else if (selected.length > 1) {
        setSelectedEntity(selected[0].id);
      }
    },
    [setSelectedEntity]
  );
}
