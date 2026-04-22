/*
 * Auto-scroll hook — fallback for the CSS `overflow-anchor: auto` path.
 *
 * The transcript container relies on `overflow-anchor` to pin the viewport
 * to the last bubble during polling-driven appends. CSS handles the steady
 * state cleanly. This hook covers three known-flaky cases:
 *
 *   1. First mount with seeded content — `overflow-anchor` isn't engaged
 *      yet because the user hasn't scrolled. We jump to the bottom on
 *      mount + when the dep first transitions from empty.
 *   2. Late-loading code blocks / images expanding height after a paint —
 *      we run a small "near-bottom?" check on each dep tick and re-scroll
 *      if the user hadn't manually scrolled away.
 *   3. Virtualized lists where row measurement happens asynchronously —
 *      `overflow-anchor` cannot anchor to a node that doesn't exist yet in
 *      the DOM. A ResizeObserver on the inner container re-pins to bottom
 *      whenever scrollable height grows while the user is at bottom.
 *
 * Decision recorded in ADR-035: CSS-first; this hook is the safety net.
 *
 * Iterate 3.7c-2 UAT fix (2026-04-21):
 *   - double-rAF scroll so virtualizer has finished its measurement pass
 *     before we read scrollHeight.
 *   - initial-mount setTimeout fallback for first paint where rAF might
 *     race react-virtual's measureElement callback.
 *   - ResizeObserver on inner container covers the 3-pane layout case
 *     where pane widths change (splitter drag) and content re-flows.
 *
 * The hook returns the `isAtBottom` flag so callers can render a "Jump to
 * latest" affordance when the user has scrolled up far enough to detach.
 */

import { useEffect, useLayoutEffect, useRef, useState } from "react";

const NEAR_BOTTOM_THRESHOLD_PX = 64;

export function useAutoScroll(
  containerRef: React.RefObject<HTMLElement | null>,
  dep: unknown,
): { isAtBottom: boolean; scrollToBottom: () => void } {
  const [isAtBottom, setIsAtBottom] = useState(true);
  // `userDetached` stays true until the user scrolls back near the bottom.
  // Initialized to false so the first mount auto-scrolls to the end.
  const userDetached = useRef(false);
  const didInitialScroll = useRef(false);

  // Attach scroll listener once per container. Track whether the user has
  // manually scrolled up — if so, pause auto-scroll until they come back.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onScroll = () => {
      const distance = el.scrollHeight - el.scrollTop - el.clientHeight;
      const atBottom = distance < NEAR_BOTTOM_THRESHOLD_PX;
      setIsAtBottom(atBottom);
      userDetached.current = !atBottom;
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [containerRef]);

  // On every dep change (new content / tail growth / filter flip) re-pin
  // to the bottom unless the user has scrolled away. Double-rAF so the
  // scroll happens after virtualizer measurement has written the final
  // scrollHeight; a setTimeout fallback handles the first-mount case
  // where rAF can still race react-virtual's measurement callback.
  useLayoutEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    if (userDetached.current) return;
    const run = () => {
      const node = containerRef.current;
      if (!node) return;
      node.scrollTop = node.scrollHeight;
    };
    requestAnimationFrame(() => {
      run();
      requestAnimationFrame(run);
    });
    if (!didInitialScroll.current) {
      didInitialScroll.current = true;
      const t = window.setTimeout(run, 60);
      return () => window.clearTimeout(t);
    }
  }, [dep, containerRef]);

  // Safety net for virtualization: ResizeObserver on the inner content
  // re-pins when measurement bumps scrollHeight while the user is at
  // the bottom.
  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const inner = el.firstElementChild;
    if (!inner) return;
    const ro = new ResizeObserver(() => {
      if (userDetached.current) return;
      const node = containerRef.current;
      if (!node) return;
      node.scrollTop = node.scrollHeight;
    });
    ro.observe(inner);
    return () => ro.disconnect();
  }, [containerRef, dep]);

  const scrollToBottom = () => {
    const el = containerRef.current;
    if (!el) return;
    userDetached.current = false;
    el.scrollTop = el.scrollHeight;
    setIsAtBottom(true);
  };

  return { isAtBottom, scrollToBottom };
}
