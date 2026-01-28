import { useCallback } from "react";
import { useAppStore } from "src/webview/store/appStore";

export const useSelectionController = () => {
  const setSelected = useAppStore((state) => state.setSelectedEntityId);

  return useCallback(
    (entityId: string | null) => {
      setSelected(entityId);
    },
    [setSelected],
  );
};
