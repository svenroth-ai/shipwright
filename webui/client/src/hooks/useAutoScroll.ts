/*
 * Auto-scroll hook — fallback for the CSS `overflow-anchor: auto` path.
 *
 * The transcript container relies on `overflow-anchor` to pin the viewport
 * to the last bubble during polling-driven appends. CSS handles the steady
 * state cleanly. This hook covers two known-flaky cases:
 *
 *   1. First mount with seeded content — `overflow-anchor` isn't engaged
 *      yet because the user hasn't scrolled. We jump to the bottom on
 *      mount + when the dep first transitions from empty.
 *   2. Late-loading code blocks / images expanding height after a paint —
 *      we run a small "near-bottom?" check on each dep tick and re-scroll
 *      if the user hadn't manually scrolled away.
 *
 * Decision recorded in ADR-035: CSS-first; this hook is the safety net.
 *
 * The hook returns the `isAtBottom` flag so callers can render a "Jump to
 * latest" affordance when the user has scrolled up far enough to detach.
 */

import { useEffect, useRef, useState } from "react";

const NEAR_BOTTOM_THRESHOLD_PX = 64;

export function useAutoScroll(
  containerRef: React.RefObject<HTMLElement | null>,
  dep: unknown,
): { isAtBottom: boolean; scrollToBottom: () => void } {
  const [isAtBottom, setIsAtBottom] = useState(true);
  const userDetached = useRef(false);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onScroll = () => {
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      const atBottom = distance < NEAR_BOTTOM_THRESHOLD_PX;
      setIsAtBottom(atBottom);
      // Once the user scrolls away, suppress auto-scroll until they
      // come back down on their own.
      userDetached.current = !atBottom;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [containerRef]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    if (userDetached.current) return;
    // Schedule after layout so freshly inserted bubbles have measured.
    requestAnimationFrame(() => {
      if (containerRef.current) {
        containerRef.current.scrollTop = containerRef.current.scrollHeight;
      }
    });
  }, [dep, containerRef]);

  const scrollToBottom = () => {
    const el = containerRef.current;
    if (!el) return;
    userDetached.current = false;
    el.scrollTop = el.scrollHeight;
    setIsAtBottom(true);
  };

  return { isAtBottom, scrollToBottom };
}
