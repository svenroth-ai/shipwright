/*
 * useAutoScroll unit coverage — 2026-04-23 iterate-20260423-chat-followups AC-2.
 *
 * Covers the pre-growth at-bottom gate that prevents unwanted viewport
 * jumps when the user expands a ToolCard mid-transcript. The ResizeObserver
 * callback is captured via a mock and invoked manually with controlled
 * scrollHeight / scrollTop / clientHeight values to simulate growth
 * scenarios without a real layout engine.
 */

import { act, renderHook } from "@testing-library/react";
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { useAutoScroll } from "./useAutoScroll";
import { createRef } from "react";

type ROCallback = (entries: ResizeObserverEntry[], obs: ResizeObserver) => void;

// Captured callbacks from every ResizeObserver instantiated during the test.
let capturedCallbacks: ROCallback[] = [];
let originalResizeObserver: typeof ResizeObserver | undefined;

class MockResizeObserver {
  constructor(cb: ROCallback) {
    capturedCallbacks.push(cb);
  }
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn();
}

beforeEach(() => {
  capturedCallbacks = [];
  originalResizeObserver = globalThis.ResizeObserver as typeof ResizeObserver | undefined;
  (globalThis as { ResizeObserver: typeof ResizeObserver }).ResizeObserver =
    MockResizeObserver as unknown as typeof ResizeObserver;
});

afterEach(() => {
  if (originalResizeObserver) {
    (globalThis as { ResizeObserver: typeof ResizeObserver }).ResizeObserver =
      originalResizeObserver;
  }
  document.body.innerHTML = "";
});

/**
 * jsdom exposes scrollHeight / clientHeight as read-only properties
 * (backed by the computed layout, which jsdom doesn't run). For the
 * test we override them with writable accessors so we can drive the
 * RO callback with controlled growth/shrink scenarios.
 */
function setScrollHeight(el: HTMLElement, value: number) {
  Object.defineProperty(el, "scrollHeight", {
    configurable: true,
    get: () => value,
  });
}

function setClientHeight(el: HTMLElement, value: number) {
  Object.defineProperty(el, "clientHeight", {
    configurable: true,
    get: () => value,
  });
}

function makeContainer({
  scrollHeight = 1000,
  scrollTop = 0,
  clientHeight = 500,
}: {
  scrollHeight?: number;
  scrollTop?: number;
  clientHeight?: number;
} = {}) {
  const outer = document.createElement("div");
  const inner = document.createElement("div");
  outer.appendChild(inner);
  document.body.appendChild(outer);

  setScrollHeight(outer, scrollHeight);
  setClientHeight(outer, clientHeight);
  // scrollTop is writable in jsdom; assign directly.
  outer.scrollTop = scrollTop;

  return outer;
}

describe("useAutoScroll — AC-2 pre-growth at-bottom gate", () => {
  it("does NOT scroll on RO growth when user was mid-transcript (far from prev bottom)", () => {
    // Setup: prev scrollHeight 1000, clientHeight 500, scrollTop 100.
    // distanceFromPrevBottom = 1000 - 100 - 500 = 400 > threshold (64).
    const el = makeContainer({ scrollHeight: 1000, scrollTop: 100, clientHeight: 500 });
    const ref = createRef<HTMLDivElement>();
    (ref as { current: HTMLDivElement | null }).current = el;

    renderHook(() => useAutoScroll(ref, "dep-0"));

    // Simulate tool-card expansion: scrollHeight grows from 1000 → 1300.
    setScrollHeight(el, 1300);

    // Fire the RO callback that was registered on mount.
    act(() => {
      for (const cb of capturedCallbacks) {
        cb([], {} as ResizeObserver);
      }
    });

    // User was mid-transcript; scrollTop should NOT have been forced to scrollHeight.
    expect(el.scrollTop).toBe(100);
  });

  it("DOES scroll on RO growth when user was within threshold of prev bottom", () => {
    // distanceFromPrevBottom = 1000 - 460 - 500 = 40 < 64.
    const el = makeContainer({ scrollHeight: 1000, scrollTop: 460, clientHeight: 500 });
    const ref = createRef<HTMLDivElement>();
    (ref as { current: HTMLDivElement | null }).current = el;

    renderHook(() => useAutoScroll(ref, "dep-0"));

    setScrollHeight(el, 1300);
    act(() => {
      for (const cb of capturedCallbacks) {
        cb([], {} as ResizeObserver);
      }
    });

    // User was near bottom pre-growth; expect a re-pin to the new bottom.
    expect(el.scrollTop).toBe(1300);
  });

  it("does NOT scroll on SHRINK (collapsing a tool card)", () => {
    // scrollHeight 1000 → 700. User was at bottom previously, but we
    // don't want a shrink to snap them anywhere.
    const el = makeContainer({ scrollHeight: 1000, scrollTop: 500, clientHeight: 500 });
    const ref = createRef<HTMLDivElement>();
    (ref as { current: HTMLDivElement | null }).current = el;

    renderHook(() => useAutoScroll(ref, "dep-0"));

    setScrollHeight(el, 700);
    act(() => {
      for (const cb of capturedCallbacks) {
        cb([], {} as ResizeObserver);
      }
    });

    // Scroll position untouched on shrink.
    expect(el.scrollTop).toBe(500);
  });

  it("uses current scrollHeight as baseline after each callback (handles sequential growths)", () => {
    // Two-step growth: user at bottom of 1000, grows to 1300 (scroll happens),
    // then grows to 1500. Second growth should also scroll because the
    // previous-height was updated to 1300 after the first callback.
    const el = makeContainer({ scrollHeight: 1000, scrollTop: 480, clientHeight: 500 });
    const ref = createRef<HTMLDivElement>();
    (ref as { current: HTMLDivElement | null }).current = el;

    renderHook(() => useAutoScroll(ref, "dep-0"));

    // First growth: 1000 → 1300, user at 480 (distance 20 < 64) → scroll.
    setScrollHeight(el, 1300);
    act(() => {
      for (const cb of capturedCallbacks) cb([], {} as ResizeObserver);
    });
    expect(el.scrollTop).toBe(1300);

    // After scroll, scrollTop = 1300. clientHeight 500. prev=1300.
    // distance = 1300 - 1300 - 500 = -500 (negative = past bottom).
    setScrollHeight(el, 1500);
    act(() => {
      for (const cb of capturedCallbacks) cb([], {} as ResizeObserver);
    });
    // User was at/past bottom; expect re-pin to new bottom.
    expect(el.scrollTop).toBe(1500);
  });

  it("rehydrates the prev-height baseline on dep change (transcript-swap hygiene)", () => {
    // Simulate session-swap: same ref, new dep. The RO useEffect
    // re-fires (teardown + re-attach) with a fresh scrollHeight baseline
    // from the new container. Without this the first callback after
    // the swap would compare against a stale prev from the previous
    // session and misclassify growth vs shrink.
    const el = makeContainer({ scrollHeight: 1000, scrollTop: 500, clientHeight: 500 });
    const ref = createRef<HTMLDivElement>();
    (ref as { current: HTMLDivElement | null }).current = el;

    const { rerender } = renderHook(
      ({ d }: { d: string }) => useAutoScroll(ref, d),
      { initialProps: { d: "session-a" } },
    );
    // Drop the old observer by switching dep. The effect re-runs and
    // re-observes against the current scrollHeight.
    setScrollHeight(el, 400);
    rerender({ d: "session-b" });

    // New session's content grows from 400 → 1000. User position in
    // current scrollTop = 500 (stale from previous session). Distance
    // from NEW-baseline (400) bottom = 400 - 500 - 500 = -600 (already
    // past bottom). So growth should re-pin.
    setScrollHeight(el, 1000);
    act(() => {
      for (const cb of capturedCallbacks) cb([], {} as ResizeObserver);
    });
    expect(el.scrollTop).toBe(1000);
  });

  it("does NOT scroll after the user manually scrolls away (userDetached)", () => {
    const el = makeContainer({ scrollHeight: 1000, scrollTop: 480, clientHeight: 500 });
    const ref = createRef<HTMLDivElement>();
    (ref as { current: HTMLDivElement | null }).current = el;

    renderHook(() => useAutoScroll(ref, "dep-0"));

    // User scrolls up (away from bottom). distance = 1000 - 100 - 500 = 400 > 64.
    el.scrollTop = 100;
    el.dispatchEvent(new Event("scroll"));

    // Now content grows — user moved away, should NOT be yanked back.
    setScrollHeight(el, 1300);
    act(() => {
      for (const cb of capturedCallbacks) cb([], {} as ResizeObserver);
    });
    expect(el.scrollTop).toBe(100);
  });
});
