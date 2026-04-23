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
  // 2026-04-23 — iterate-20260423-chat-followups AC-2: track scrollHeight
  // from the previous ResizeObserver callback so we can answer "was the
  // user at bottom of the PREVIOUS content?" inside the callback — not
  // "is the user at bottom NOW", which is always false after growth.
  // Initialized to 0 and reset on dep change so session swaps don't
  // inherit the previous session's height budget.
  const prevScrollHeight = useRef(0);

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
  // re-pins when measurement bumps scrollHeight WHILE the user was at
  // the bottom of the previous height. The "pre-growth" check fixes the
  // expand-a-tool-card-mid-transcript regression reported in ADR-054
  // live-test (chat-followups AC-2) — we only follow growth that
  // continues a stream the user was already tailing, not ad-hoc
  // expansions of historical content.
  useEffect(() => {
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const inner = el.firstElementChild;
    if (!inner) return;
    // Seed prev-height from current layout at observer-attach time so the
    // first callback fire has a valid baseline. Without this the first
    // callback would compute a nonsensical distance against prev=0.
    prevScrollHeight.current = el.scrollHeight;
    const ro = new ResizeObserver(() => {
      const node = containerRef.current;
      if (!node) return;
      const prev = prevScrollHeight.current;
      const now = node.scrollHeight;
      try {
        // Skip when user has explicitly scrolled away.
        if (userDetached.current) return;
        // Only re-pin on GROWTH (not shrink/no-op).
        if (now <= prev) return;
        // Was the user at the bottom of the PREVIOUS content? Use a
        // negative-tolerant check (prev may equal scrollTop+clientHeight,
        // or fall short if we just scrolled past it in a prior callback).
        const distanceFromPrevBottom = prev - (node.scrollTop + node.clientHeight);
        if (distanceFromPrevBottom > NEAR_BOTTOM_THRESHOLD_PX) return;
        node.scrollTop = now;
      } finally {
        // Always refresh the baseline — covers growth, shrink, and
        // no-op transitions. A stale baseline would misclassify the
        // next callback.
        prevScrollHeight.current = now;
      }
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
