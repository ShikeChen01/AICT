/**
 * Redux slice for UI state: selection, scope, focus mode, filters.
 */

import { createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type { EntityId, EntityStatus } from '../../../shared/types/entities';
import type { FocusMode } from '../../../shared/types/canvas';

export interface UiState {
  selectedIds: EntityId[];
  scopeEntityId: EntityId | null;
  focusMode: FocusMode;
  connectMode: boolean;
  filters: {
    status: EntityStatus[];
    tags: string[];
    languages: string[];
  };
  editPopoverEntityId: EntityId | null;
  editPopoverPosition: { x: number; y: number } | null;
  contextMenuEntityId: EntityId | null;
  contextMenuPosition: { x: number; y: number } | null;
  bucketCreationOpen: boolean;
  draggedNodeId: EntityId | null;
  potentialParentId: EntityId | null;
}

const initialState: UiState = {
  selectedIds: [],
  scopeEntityId: null,
  focusMode: 'workspace',
  connectMode: false,
  filters: {
    status: [],
    tags: [],
    languages: [],
  },
  editPopoverEntityId: null,
  editPopoverPosition: null,
  contextMenuEntityId: null,
  contextMenuPosition: null,
  bucketCreationOpen: false,
  draggedNodeId: null,
  potentialParentId: null,
};

const uiSlice = createSlice({
  name: 'ui',
  initialState,
  reducers: {
    setSelection(state, action: PayloadAction<EntityId[]>) {
      state.selectedIds = action.payload;
    },

    selectOne(state, action: PayloadAction<EntityId>) {
      state.selectedIds = [action.payload];
    },

    toggleSelection(state, action: PayloadAction<EntityId>) {
      const id = action.payload;
      const idx = state.selectedIds.indexOf(id);
      if (idx === -1) {
        state.selectedIds.push(id);
      } else {
        state.selectedIds.splice(idx, 1);
      }
    },

    addToSelection(state, action: PayloadAction<EntityId>) {
      const id = action.payload;
      if (!state.selectedIds.includes(id)) {
        state.selectedIds.push(id);
      }
    },

    clearSelection(state) {
      state.selectedIds = [];
    },

    setScope(state, action: PayloadAction<EntityId | null>) {
      state.scopeEntityId = action.payload;
    },

    setFocusMode(state, action: PayloadAction<FocusMode>) {
      state.focusMode = action.payload;
    },

    enterScope(state, action: PayloadAction<{ entityId: EntityId; mode: FocusMode }>) {
      state.scopeEntityId = action.payload.entityId;
      state.focusMode = action.payload.mode;
    },

    exitScope(state) {
      state.scopeEntityId = null;
      state.focusMode = 'workspace';
    },

    setConnectMode(state, action: PayloadAction<boolean>) {
      state.connectMode = action.payload;
    },

    setFilters(
      state,
      action: PayloadAction<{
        status?: EntityStatus[];
        tags?: string[];
        languages?: string[];
      }>
    ) {
      const { status, tags, languages } = action.payload;
      if (status !== undefined) state.filters.status = status;
      if (tags !== undefined) state.filters.tags = tags;
      if (languages !== undefined) state.filters.languages = languages;
    },

    setEditPopover(state, action: PayloadAction<EntityId | null>) {
      state.editPopoverEntityId = action.payload;
      state.editPopoverPosition = null;
    },

    setEditPopoverWithPosition(
      state,
      action: PayloadAction<{ entityId: EntityId; x: number; y: number } | null>
    ) {
      if (action.payload === null) {
        state.editPopoverEntityId = null;
        state.editPopoverPosition = null;
      } else {
        state.editPopoverEntityId = action.payload.entityId;
        state.editPopoverPosition = { x: action.payload.x, y: action.payload.y };
      }
    },

    setContextMenu(state, action: PayloadAction<EntityId | null>) {
      state.contextMenuEntityId = action.payload;
      state.contextMenuPosition = null;
    },

    setContextMenuWithPosition(
      state,
      action: PayloadAction<{ entityId: EntityId; x: number; y: number } | null>
    ) {
      if (action.payload === null) {
        state.contextMenuEntityId = null;
        state.contextMenuPosition = null;
      } else {
        state.contextMenuEntityId = action.payload.entityId;
        state.contextMenuPosition = { x: action.payload.x, y: action.payload.y };
      }
    },

    setBucketCreationOpen(state, action: PayloadAction<boolean>) {
      state.bucketCreationOpen = action.payload;
    },

    setDraggedNode(state, action: PayloadAction<EntityId | null>) {
      state.draggedNodeId = action.payload;
    },

    setPotentialParent(state, action: PayloadAction<EntityId | null>) {
      state.potentialParentId = action.payload;
    },
  },
});

export const {
  setSelection,
  selectOne,
  toggleSelection,
  addToSelection,
  clearSelection,
  setScope,
  setFocusMode,
  enterScope,
  exitScope,
  setConnectMode,
  setFilters,
  setEditPopover,
  setEditPopoverWithPosition,
  setContextMenu,
  setContextMenuWithPosition,
  setBucketCreationOpen,
  setDraggedNode,
  setPotentialParent,
} = uiSlice.actions;

export default uiSlice.reducer;
