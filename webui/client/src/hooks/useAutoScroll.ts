import { useEffect, useCallback, useRef, useState } from 'react';

const THRESHOLD = 50;

export function useAutoScroll(containerRef: React.RefObject<HTMLElement | null>, deps: unknown[]) {
  const [isAtBottom, setIsAtBottom] = useState(true);
  const userScrolledRef = useRef(false);

  const checkAtBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < THRESHOLD;
    setIsAtBottom(atBottom);
    userScrolledRef.current = !atBottom;
  }, [containerRef]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    el.addEventListener('scroll', checkAtBottom);
    return () => el.removeEventListener('scroll', checkAtBottom);
  }, [containerRef, checkAtBottom]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el || userScrolledRef.current) return;
    el.scrollTop = el.scrollHeight;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  const scrollToBottom = useCallback(() => {
    const el = containerRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
    userScrolledRef.current = false;
    setIsAtBottom(true);
  }, [containerRef]);

  return { isAtBottom, scrollToBottom };
}
