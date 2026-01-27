import { useEffect, useState } from "react";
import type { Edge, Node, OnSelectionChangeParams } from "reactflow";
import { useCanvasStore } from "../store/canvasStore";

export interface SelectionController {
  selectedNodeIds: string[];
  selectedEdgeIds: string[];
  isMultiSelect: boolean;
  onSelectionChange: (params: OnSelectionChangeParams) => void;
}

export function useSelectionController(): SelectionController {
  const setSelection = useCanvasStore((state) => state.setSelection);
  const [isMultiSelect, setIsMultiSelect] = useState(false);
  const [selectedNodeIds, setSelectedNodeIds] = useState<string[]>([]);
  const [selectedEdgeIds, setSelectedEdgeIds] = useState<string[]>([]);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Shift" || event.key === "Control" || event.key === "Meta") {
        setIsMultiSelect(true);
      }
    };
    const onKeyUp = (event: KeyboardEvent) => {
      if (event.key === "Shift" || event.key === "Control" || event.key === "Meta") {
        setIsMultiSelect(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("keyup", onKeyUp);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("keyup", onKeyUp);
    };
  }, []);

  const onSelectionChange = (params: OnSelectionChangeParams) => {
    const nodes = (params.nodes ?? []) as Node[];
    const edges = (params.edges ?? []) as Edge[];
    const nodeIds = nodes.map((node) => node.id);
    const edgeIds = edges.map((edge) => edge.id);
    setSelectedNodeIds(nodeIds);
    setSelectedEdgeIds(edgeIds);
    setSelection(nodeIds, edgeIds);
  };

  return { selectedNodeIds, selectedEdgeIds, isMultiSelect, onSelectionChange };
}
