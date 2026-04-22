/*
 * useThreePaneLayout — persisted layout state for the TaskDetail 3-pane
 * body (section 04 of iterate 3).
 *
 * Four localStorage keys (plan § 7 O5):
 *   webui.taskDetail.leftWidth        number, default 240 (min 180 / max 480)
 *   webui.taskDetail.rightWidth       number, default 480 (min 320 / max 720)
 *   webui.taskDetail.leftCollapsed    boolean, default false
 *   webui.taskDetail.rightCollapsed   boolean, default false
 *
 * Widths are clamped on read AND on write — a corrupt/out-of-range
 * localStorage value falls back to the default instead of throwing. Writes
 * are debounced 200 ms so a rapid drag doesn't fire 60 writes/sec.
 *
 * Keyboard-resize helpers are exposed (`nudgeLeft`, `nudgeRight`) so the
 * splitter handles can move widths in 10 px steps on ArrowLeft/Right;
 * `toggleLeftCollapsed` / `toggleRightCollapsed` wire to the Enter key on
 * the splitter. Callers never touch localStorage directly.
 */

import { useCallback, useEffect, useRef, useState } from "react";

export const STORAGE_KEYS = {
  leftWidth: "webui.taskDetail.leftWidth",
  rightWidth: "webui.taskDetail.rightWidth",
  leftCollapsed: "webui.taskDetail.leftCollapsed",
  rightCollapsed: "webui.taskDetail.rightCollapsed",
} as const;

export const LEFT_MIN = 180;
export const LEFT_MAX = 480;
export const RIGHT_MIN = 320;
export const RIGHT_MAX = 720;
export const DEFAULT_LEFT = 240;
export const DEFAULT_RIGHT = 480;
export const STEP_PX = 10;
export const COLLAPSED_LEFT_PX = 48;
export const COLLAPSED_RIGHT_PX = 0;

const DEBOUNCE_MS = 200;

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return (min + max) / 2;
  return Math.min(max, Math.max(min, Math.round(value)));
}

function readNumber(
  key: string,
  defaultValue: number,
  min: number,
  max: number,
): number {
  if (typeof localStorage === "undefined") return defaultValue;
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return defaultValue;
    const parsed = JSON.parse(raw);
    if (typeof parsed !== "number" || !Number.isFinite(parsed)) return defaultValue;
    return clamp(parsed, min, max);
  } catch {
    return defaultValue;
  }
}

function readBoolean(key: string, defaultValue: boolean): boolean {
  if (typeof localStorage === "undefined") return defaultValue;
  try {
    const raw = localStorage.getItem(key);
    if (raw === null) return defaultValue;
    const parsed = JSON.parse(raw);
    return typeof parsed === "boolean" ? parsed : defaultValue;
  } catch {
    return defaultValue;
  }
}

export interface ThreePaneLayoutState {
  leftWidth: number;
  rightWidth: number;
  leftCollapsed: boolean;
  rightCollapsed: boolean;
}

export interface ThreePaneLayoutApi extends ThreePaneLayoutState {
  setLeftWidth: (value: number) => void;
  setRightWidth: (value: number) => void;
  toggleLeftCollapsed: () => void;
  toggleRightCollapsed: () => void;
  nudgeLeft: (deltaPx: number) => void;
  nudgeRight: (deltaPx: number) => void;
}

export function useThreePaneLayout(): ThreePaneLayoutApi {
  const [leftWidth, setLeftWidthState] = useState<number>(() =>
    readNumber(STORAGE_KEYS.leftWidth, DEFAULT_LEFT, LEFT_MIN, LEFT_MAX),
  );
  const [rightWidth, setRightWidthState] = useState<number>(() =>
    readNumber(STORAGE_KEYS.rightWidth, DEFAULT_RIGHT, RIGHT_MIN, RIGHT_MAX),
  );
  const [leftCollapsed, setLeftCollapsed] = useState<boolean>(() =>
    readBoolean(STORAGE_KEYS.leftCollapsed, false),
  );
  const [rightCollapsed, setRightCollapsed] = useState<boolean>(() =>
    readBoolean(STORAGE_KEYS.rightCollapsed, false),
  );

  // Debounced writes.
  const leftTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rightTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (leftTimer.current) clearTimeout(leftTimer.current);
    leftTimer.current = setTimeout(() => {
      try {
        localStorage.setItem(STORAGE_KEYS.leftWidth, JSON.stringify(leftWidth));
      } catch {
        /* quota or disabled — ignore */
      }
    }, DEBOUNCE_MS);
    return () => {
      if (leftTimer.current) clearTimeout(leftTimer.current);
    };
  }, [leftWidth]);

  useEffect(() => {
    if (rightTimer.current) clearTimeout(rightTimer.current);
    rightTimer.current = setTimeout(() => {
      try {
        localStorage.setItem(STORAGE_KEYS.rightWidth, JSON.stringify(rightWidth));
      } catch {
        /* ignore */
      }
    }, DEBOUNCE_MS);
    return () => {
      if (rightTimer.current) clearTimeout(rightTimer.current);
    };
  }, [rightWidth]);

  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_KEYS.leftCollapsed,
        JSON.stringify(leftCollapsed),
      );
    } catch {
      /* ignore */
    }
  }, [leftCollapsed]);

  useEffect(() => {
    try {
      localStorage.setItem(
        STORAGE_KEYS.rightCollapsed,
        JSON.stringify(rightCollapsed),
      );
    } catch {
      /* ignore */
    }
  }, [rightCollapsed]);

  const setLeftWidth = useCallback((value: number) => {
    setLeftWidthState(clamp(value, LEFT_MIN, LEFT_MAX));
  }, []);
  const setRightWidth = useCallback((value: number) => {
    setRightWidthState(clamp(value, RIGHT_MIN, RIGHT_MAX));
  }, []);
  const toggleLeftCollapsed = useCallback(
    () => setLeftCollapsed((v) => !v),
    [],
  );
  const toggleRightCollapsed = useCallback(
    () => setRightCollapsed((v) => !v),
    [],
  );
  const nudgeLeft = useCallback((deltaPx: number) => {
    setLeftWidthState((prev) => clamp(prev + deltaPx, LEFT_MIN, LEFT_MAX));
  }, []);
  const nudgeRight = useCallback((deltaPx: number) => {
    setRightWidthState((prev) => clamp(prev + deltaPx, RIGHT_MIN, RIGHT_MAX));
  }, []);

  return {
    leftWidth,
    rightWidth,
    leftCollapsed,
    rightCollapsed,
    setLeftWidth,
    setRightWidth,
    toggleLeftCollapsed,
    toggleRightCollapsed,
    nudgeLeft,
    nudgeRight,
  };
}
