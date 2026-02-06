/**
 * Redux store configuration.
 */

import { configureStore } from '@reduxjs/toolkit';
import entitiesReducer from './slices/entitiesSlice';
import canvasReducer from './slices/canvasSlice';
import uiReducer from './slices/uiSlice';
import agentReducer from './slices/agentSlice';

export const store = configureStore({
  reducer: {
    entities: entitiesReducer,
    canvas: canvasReducer,
    ui: uiReducer,
    agent: agentReducer,
  },
});

// Expose store for E2E testing/debugging
(window as unknown as Record<string, unknown>).__store = store;

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
