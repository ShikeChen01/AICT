import { useCallback, useEffect, useMemo, useState } from 'react';

interface UseAutoFollowOptions {
  dependencyKey: string | number;
  threshold?: number;
}

export function useAutoFollow<T extends HTMLElement>({
  dependencyKey,
  threshold = 24,
}: UseAutoFollowOptions) {
  const [container, setContainer] = useState<T | null>(null);
  const [isAutoFollow, setIsAutoFollow] = useState(true);

  const attachRef = useCallback((el: T | null) => {
    setContainer(el);
  }, []);

  const atBottom = useCallback(() => {
    if (!container) return true;
    const distance = container.scrollHeight - (container.scrollTop + container.clientHeight);
    return distance <= threshold;
  }, [container, threshold]);

  const scrollToBottom = useCallback(
    (behavior: ScrollBehavior = 'auto') => {
      if (!container) return;
      if (typeof container.scrollTo === 'function') {
        container.scrollTo({ top: container.scrollHeight, behavior });
      } else {
        container.scrollTop = container.scrollHeight;
      }
    },
    [container]
  );

  const onScroll = useCallback(() => {
    setIsAutoFollow(atBottom());
  }, [atBottom]);

  useEffect(() => {
    if (!container) return;
    if (isAutoFollow) {
      scrollToBottom();
    }
  }, [container, dependencyKey, isAutoFollow, scrollToBottom]);

  useEffect(() => {
    if (!container) return;
    const onResize = () => {
      if (isAutoFollow) {
        scrollToBottom();
      }
    };
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, [container, isAutoFollow, scrollToBottom]);

  return useMemo(
    () => ({
      attachRef,
      onScroll,
      isAutoFollow,
      jumpToLatest: () => {
        scrollToBottom('smooth');
        setIsAutoFollow(true);
      },
    }),
    [attachRef, isAutoFollow, onScroll, scrollToBottom]
  );
}

export default useAutoFollow;

