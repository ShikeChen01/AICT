import { describe, it, expect } from 'vitest';
import uiReducer, { setDraggedNode, setPotentialParent } from './uiSlice';
import type { UiState } from './uiSlice';

const getInitialState = (): UiState => ({
  selectedIds: [],
  scopeEntityId: null,
  focusMode: 'workspace',
  connectMode: false,
  filters: { status: [], tags: [], languages: [] },
  editPopoverEntityId: null,
  editPopoverPosition: null,
  contextMenuEntityId: null,
  contextMenuPosition: null,
  bucketCreationOpen: false,
  draggedNodeId: null,
  potentialParentId: null,
});

describe('uiSlice', () => {
  describe('setDraggedNode', () => {
    it('sets and clears draggedNodeId', () => {
      let state = uiReducer(getInitialState(), setDraggedNode('node1'));
      expect(state.draggedNodeId).toBe('node1');
      state = uiReducer(state, setDraggedNode(null));
      expect(state.draggedNodeId).toBeNull();
    });
  });

  describe('setPotentialParent', () => {
    it('sets and clears potentialParentId', () => {
      let state = uiReducer(getInitialState(), setPotentialParent('parent1'));
      expect(state.potentialParentId).toBe('parent1');
      state = uiReducer(state, setPotentialParent(null));
      expect(state.potentialParentId).toBeNull();
    });
  });
});
