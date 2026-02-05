import { useCallback } from 'react';
import { useAppDispatch, useAppSelector } from '../../../store/hooks';
import { setSelection } from '../../../store/slices/uiSlice';

export function useSelection() {
  const dispatch = useAppDispatch();
  const selectedIds = useAppSelector((s) => s.ui.selectedIds);

  const select = useCallback(
    (id: string, additive = false) => {
      if (additive) {
        dispatch(setSelection([...selectedIds, id]));
      } else {
        dispatch(setSelection([id]));
      }
    },
    [selectedIds, dispatch]
  );

  const deselect = useCallback(
    (id: string) => {
      dispatch(setSelection(selectedIds.filter((s) => s !== id)));
    },
    [selectedIds, dispatch]
  );

  const clearSelection = useCallback(() => {
    dispatch(setSelection([]));
  }, [dispatch]);

  return { selectedIds, select, deselect, clearSelection };
}
