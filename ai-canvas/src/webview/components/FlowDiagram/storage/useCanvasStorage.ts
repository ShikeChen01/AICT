import { useEffect, useRef } from 'react';
import { useAppSelector } from '../../../store/hooks';
import { selectStateForSave } from '../../../store/selectors/entitySelectors';
import { CanvasStorage } from './CanvasStorage';
import type { RpcClient } from '../../../rpcClient/rpcClient';

export function useCanvasStorage(rpcClient: RpcClient | null): CanvasStorage | null {
  const storageRef = useRef<CanvasStorage | null>(null);
  const stateForSave = useAppSelector(selectStateForSave);

  useEffect(() => {
    if (!rpcClient) return;
    storageRef.current = new CanvasStorage(rpcClient);
    return () => {
      storageRef.current?.dispose();
      storageRef.current = null;
    };
  }, [rpcClient]);

  useEffect(() => {
    if (storageRef.current && stateForSave) {
      storageRef.current.save({
        entities: stateForSave.entities,
        canvas: stateForSave.canvas,
      });
    }
  }, [stateForSave]);

  return storageRef.current;
}
