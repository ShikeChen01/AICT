import type { EdgeProps } from 'reactflow';

function DefaultEdge({ id }: EdgeProps) {
  return null;
}

export const edgeTypes = {
  containment: DefaultEdge,
  dependency: DefaultEdge
};
