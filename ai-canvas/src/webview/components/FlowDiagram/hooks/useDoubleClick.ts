import { useCallback } from 'react';
import { useAppSelector } from '../../../store/hooks';
import type { CommandRegistry } from '../../../commands/CommandRegistry';

export function useDoubleClick(commandRegistry: CommandRegistry) {
  const entities = useAppSelector((s) => s.entities.byId);

  const handleDoubleClick = useCallback(
    (nodeId: string) => {
      const entity = entities[nodeId];
      if (
        entity &&
        (entity.type === 'bucket' || entity.type === 'module')
      ) {
        commandRegistry.execute({
          type: 'SET_SCOPE',
          payload: { entityId: nodeId },
        });
      }
    },
    [entities, commandRegistry]
  );

  return { handleDoubleClick };
}
