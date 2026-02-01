/**
 * Redux slice for Agent conversation window state.
 */

import { createSlice, type PayloadAction } from '@reduxjs/toolkit';
import type { EntityId } from '../../../shared/types/entities';
import type {
  ChatMessage,
  AgentMode,
  AgentStatus,
} from '../../../shared/types/canvas';

const AGENT_STORAGE_KEY = 'ai-canvas-agent-window';

function loadStoredPosition(): { x: number; y: number } {
  try {
    const s = localStorage.getItem(AGENT_STORAGE_KEY);
    if (s) {
      const parsed = JSON.parse(s);
      if (typeof parsed?.x === 'number' && typeof parsed?.y === 'number') {
        return { x: parsed.x, y: parsed.y };
      }
    }
  } catch {
    // ignore
  }
  return { x: 24, y: 24 };
}

function loadStoredSize(): { width: number; height: number } {
  try {
    const s = localStorage.getItem(AGENT_STORAGE_KEY);
    if (s) {
      const parsed = JSON.parse(s);
      if (
        typeof parsed?.width === 'number' &&
        typeof parsed?.height === 'number'
      ) {
        return { width: parsed.width, height: parsed.height };
      }
    }
  } catch {
    // ignore
  }
  return { width: 380, height: 420 };
}

export interface AgentState {
  isOpen: boolean;
  isMinimized: boolean;
  position: { x: number; y: number };
  size: { width: number; height: number };
  scopeEntityId: EntityId | null;
  mode: AgentMode;
  history: ChatMessage[];
  status: AgentStatus;
  attachments: EntityId[];
  scopeLocked: boolean;
}

const initialState: AgentState = {
  isOpen: false,
  isMinimized: false,
  position: loadStoredPosition(),
  size: loadStoredSize(),
  scopeEntityId: null,
  mode: 'code+tests',
  history: [],
  status: 'idle',
  attachments: [],
  scopeLocked: true,
};

function persistAgentWindow(state: AgentState): void {
  try {
    localStorage.setItem(
      AGENT_STORAGE_KEY,
      JSON.stringify({
        x: state.position.x,
        y: state.position.y,
        width: state.size.width,
        height: state.size.height,
      })
    );
  } catch {
    // ignore
  }
}

const agentSlice = createSlice({
  name: 'agent',
  initialState,
  reducers: {
    openAgent(state) {
      state.isOpen = true;
      state.isMinimized = false;
    },

    closeAgent(state) {
      state.isOpen = false;
      state.isMinimized = false;
    },

    toggleMinimize(state) {
      state.isMinimized = !state.isMinimized;
    },

    setAgentPosition(
      state,
      action: PayloadAction<{ x: number; y: number }>
    ) {
      state.position = action.payload;
      persistAgentWindow(state);
    },

    setAgentSize(
      state,
      action: PayloadAction<{ width: number; height: number }>
    ) {
      state.size = action.payload;
      persistAgentWindow(state);
    },

    setAgentScope(state, action: PayloadAction<EntityId | null>) {
      state.scopeEntityId = action.payload;
    },

    setAgentMode(state, action: PayloadAction<AgentMode>) {
      state.mode = action.payload;
    },

    setAgentStatus(state, action: PayloadAction<AgentStatus>) {
      state.status = action.payload;
    },

    addChatMessage(state, action: PayloadAction<ChatMessage>) {
      state.history.push(action.payload);
    },

    clearChatHistory(state) {
      state.history = [];
    },

    setAttachments(state, action: PayloadAction<EntityId[]>) {
      state.attachments = action.payload;
    },

    setScopeLocked(state, action: PayloadAction<boolean>) {
      state.scopeLocked = action.payload;
    },

    openAgentWithScope(
      state,
      action: PayloadAction<{ entityId: EntityId; mode?: AgentMode }>
    ) {
      state.isOpen = true;
      state.isMinimized = false;
      state.scopeEntityId = action.payload.entityId;
      if (action.payload.mode !== undefined) {
        state.mode = action.payload.mode;
      }
    },
  },
});

export const {
  openAgent,
  closeAgent,
  toggleMinimize,
  setAgentPosition,
  setAgentSize,
  setAgentScope,
  setAgentMode,
  setAgentStatus,
  addChatMessage,
  clearChatHistory,
  setAttachments,
  setScopeLocked,
  openAgentWithScope,
} = agentSlice.actions;

export default agentSlice.reducer;
