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

export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;
