/*
 * useThreePaneLayout tests — spec § 5.7.
 *
 *  - localStorage round-trip for all 4 keys
 *  - arrow-key resize step (10 px via nudgeLeft/nudgeRight)
 *  - Enter toggles collapse (via toggleLeftCollapsed / toggleRightCollapsed)
 *  - min/max clamps
 *  - invalid localStorage values → defaults, no throw
 */

import { describe, it, expect, beforeEach, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";

import {
  useThreePaneLayout,
  STORAGE_KEYS,
  DEFAULT_LEFT,
  DEFAULT_RIGHT,
  LEFT_MIN,
  LEFT_MAX,
  RIGHT_MIN,
  RIGHT_MAX,
  STEP_PX,
} from "./useThreePaneLayout";

beforeEach(() => {
  localStorage.clear();
  vi.useFakeTimers();
});

function flushDebounce() {
  act(() => {
    vi.advanceTimersByTime(300);
  });
}

describe("useThreePaneLayout — defaults + seeding", () => {
  it("initialises to defaults when no keys set", () => {
    const { result } = renderHook(() => useThreePaneLayout());
    expect(result.current.leftWidth).toBe(DEFAULT_LEFT);
    expect(result.current.rightWidth).toBe(DEFAULT_RIGHT);
    expect(result.current.leftCollapsed).toBe(false);
    expect(result.current.rightCollapsed).toBe(false);
  });

  it("reads seeded values from localStorage on mount", () => {
    localStorage.setItem(STORAGE_KEYS.leftWidth, JSON.stringify(300));
    localStorage.setItem(STORAGE_KEYS.rightWidth, JSON.stringify(520));
    localStorage.setItem(STORAGE_KEYS.leftCollapsed, JSON.stringify(true));
    localStorage.setItem(STORAGE_KEYS.rightCollapsed, JSON.stringify(false));

    const { result } = renderHook(() => useThreePaneLayout());
    expect(result.current.leftWidth).toBe(300);
    expect(result.current.rightWidth).toBe(520);
    expect(result.current.leftCollapsed).toBe(true);
    expect(result.current.rightCollapsed).toBe(false);
  });

  it("falls back to defaults when localStorage has invalid JSON", () => {
    localStorage.setItem(STORAGE_KEYS.leftWidth, "not-json");
    localStorage.setItem(STORAGE_KEYS.rightWidth, "{broken");
    localStorage.setItem(STORAGE_KEYS.leftCollapsed, "maybe");
    localStorage.setItem(STORAGE_KEYS.rightCollapsed, "[1,2");

    const { result } = renderHook(() => useThreePaneLayout());
    expect(result.current.leftWidth).toBe(DEFAULT_LEFT);
    expect(result.current.rightWidth).toBe(DEFAULT_RIGHT);
    expect(result.current.leftCollapsed).toBe(false);
    expect(result.current.rightCollapsed).toBe(false);
  });

  it("clamps out-of-range localStorage values", () => {
    localStorage.setItem(STORAGE_KEYS.leftWidth, JSON.stringify(9999));
    localStorage.setItem(STORAGE_KEYS.rightWidth, JSON.stringify(50));
    const { result } = renderHook(() => useThreePaneLayout());
    expect(result.current.leftWidth).toBe(LEFT_MAX);
    expect(result.current.rightWidth).toBe(RIGHT_MIN);
  });
});

describe("useThreePaneLayout — mutations", () => {
  it("setLeftWidth clamps + debounces the localStorage write", () => {
    const { result } = renderHook(() => useThreePaneLayout());
    act(() => {
      result.current.setLeftWidth(320);
    });
    expect(result.current.leftWidth).toBe(320);
    // Before debounce: nothing written yet.
    expect(localStorage.getItem(STORAGE_KEYS.leftWidth)).toBeNull();
    flushDebounce();
    expect(localStorage.getItem(STORAGE_KEYS.leftWidth)).toBe("320");
  });

  it("setLeftWidth clamps values above max", () => {
    const { result } = renderHook(() => useThreePaneLayout());
    act(() => {
      result.current.setLeftWidth(5000);
    });
    expect(result.current.leftWidth).toBe(LEFT_MAX);
  });

  it("setLeftWidth clamps values below min", () => {
    const { result } = renderHook(() => useThreePaneLayout());
    act(() => {
      result.current.setLeftWidth(10);
    });
    expect(result.current.leftWidth).toBe(LEFT_MIN);
  });

  it("setRightWidth clamps + persists", () => {
    const { result } = renderHook(() => useThreePaneLayout());
    act(() => {
      result.current.setRightWidth(1000);
    });
    expect(result.current.rightWidth).toBe(RIGHT_MAX);
    flushDebounce();
    expect(localStorage.getItem(STORAGE_KEYS.rightWidth)).toBe(
      String(RIGHT_MAX),
    );
  });

  it("nudgeLeft steps 10px and clamps", () => {
    const { result } = renderHook(() => useThreePaneLayout());
    const start = result.current.leftWidth;
    act(() => {
      result.current.nudgeLeft(STEP_PX);
    });
    expect(result.current.leftWidth).toBe(start + STEP_PX);
    act(() => {
      result.current.nudgeLeft(-STEP_PX * 100);
    });
    expect(result.current.leftWidth).toBe(LEFT_MIN);
  });

  it("nudgeRight steps 10px and clamps", () => {
    const { result } = renderHook(() => useThreePaneLayout());
    const start = result.current.rightWidth;
    act(() => {
      result.current.nudgeRight(-STEP_PX);
    });
    expect(result.current.rightWidth).toBe(start - STEP_PX);
    act(() => {
      result.current.nudgeRight(STEP_PX * 1000);
    });
    expect(result.current.rightWidth).toBe(RIGHT_MAX);
  });

  it("toggleLeftCollapsed flips + persists immediately", () => {
    const { result } = renderHook(() => useThreePaneLayout());
    expect(result.current.leftCollapsed).toBe(false);
    act(() => {
      result.current.toggleLeftCollapsed();
    });
    expect(result.current.leftCollapsed).toBe(true);
    // Collapsed flags persist eagerly (no debounce).
    expect(localStorage.getItem(STORAGE_KEYS.leftCollapsed)).toBe("true");
    act(() => {
      result.current.toggleLeftCollapsed();
    });
    expect(result.current.leftCollapsed).toBe(false);
    expect(localStorage.getItem(STORAGE_KEYS.leftCollapsed)).toBe("false");
  });

  it("toggleRightCollapsed flips + persists immediately", () => {
    const { result } = renderHook(() => useThreePaneLayout());
    act(() => {
      result.current.toggleRightCollapsed();
    });
    expect(result.current.rightCollapsed).toBe(true);
    expect(localStorage.getItem(STORAGE_KEYS.rightCollapsed)).toBe("true");
  });
});
