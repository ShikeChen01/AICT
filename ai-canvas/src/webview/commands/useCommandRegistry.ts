/**
 * React hook that provides the shared CommandRegistry instance.
 */

import { useMemo } from 'react';
import { useStore } from 'react-redux';
import { CommandRegistry } from './CommandRegistry';
import { CommandHistory } from './CommandHistory';
import type { RootState, AppDispatch } from '../store/store';

let sharedHistory: CommandHistory | null = null;

export function useCommandRegistry(): CommandRegistry {
  const store = useStore<RootState>();
  const dispatch = store.dispatch as AppDispatch;
  const getState = store.getState;

  return useMemo(() => {
    if (!sharedHistory) {
      sharedHistory = new CommandHistory();
    }
    return new CommandRegistry(dispatch, getState, sharedHistory);
  }, [dispatch, getState]);
}
