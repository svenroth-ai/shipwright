/*
 * useProjectFilter — single source of truth for the active-project filter.
 *
 * Consumed by TaskBoardPage (column body), ProjectFilterDropdown (header),
 * later InboxPage + Sidebar. External review O27: DO NOT duplicate this
 * state per page, or URL + localStorage will drift.
 *
 * Reconciliation order:
 *   1. URL ?projectId=<x> wins when present.
 *   2. Otherwise, read localStorage.
 *   3. Missing / null / "" = All Projects (encoded as null).
 *
 * Iterate 3.7h (Sven UAT 2026-04-22) — BUG FIX:
 *   The prior shape used `useState` inside the hook, so each component that
 *   called `useProjectFilter()` got ITS OWN state cell. When the dropdown
 *   component's setter fired setActiveProjectIdState(null) + setSearchParams
 *   + writeLocalStorage(null), only the dropdown's state flipped. The URL-
 *   reconcile effect skipped `urlValue === null` (it only reconciled when
 *   urlValue was non-null), so other hook instances (TaskBoardPage) kept
 *   their stale "X" in local state → columns stayed filtered → bug reported
 *   across iterates 3.7c-1, 3.7f, 3.7g.
 *
 *   New shape: the hook is purely derived from a module-level store +
 *   useSyncExternalStore. Every consumer reads the same cell, re-renders on
 *   every setter fire, no drift possible.
 */

import { useCallback, useEffect, useSyncExternalStore } from "react";
import { useSearchParams } from "react-router-dom";

export const PROJECT_FILTER_STORAGE_KEY = "webui.activeProjectId";
const URL_PARAM = "projectId";

function normalize(value: string | null | undefined): string | null {
  if (value === null || value === undefined) return null;
  const trimmed = value.trim();
  return trimmed === "" ? null : trimmed;
}

function readLocalStorage(): string | null {
  try {
    return normalize(localStorage.getItem(PROJECT_FILTER_STORAGE_KEY));
  } catch {
    return null;
  }
}

function writeLocalStorage(value: string | null): void {
  try {
    if (value === null) {
      localStorage.removeItem(PROJECT_FILTER_STORAGE_KEY);
    } else {
      localStorage.setItem(PROJECT_FILTER_STORAGE_KEY, value);
    }
  } catch {
    /* ignore */
  }
}

/* ── module-level store ────────────────────────────────────────────── */

let currentValue: string | null =
  typeof window === "undefined" ? null : readLocalStorage();
const listeners = new Set<() => void>();

function emit() {
  for (const l of listeners) l();
}

function setCurrent(next: string | null) {
  if (currentValue !== next) {
    currentValue = next;
    emit();
  }
}

function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function getSnapshot() {
  return currentValue;
}

/* If another tab writes to localStorage, pick that up. */
if (typeof window !== "undefined") {
  window.addEventListener("storage", (ev) => {
    if (ev.key === PROJECT_FILTER_STORAGE_KEY) {
      setCurrent(normalize(ev.newValue));
    }
  });
}

export interface UseProjectFilterResult {
  activeProjectId: string | null;
  setActiveProjectId: (id: string | null) => void;
}

export function useProjectFilter(): UseProjectFilterResult {
  const [searchParams, setSearchParams] = useSearchParams();
  const urlValue = normalize(searchParams.get(URL_PARAM));

  // URL wins over the module store when present (deep-link / back-fwd nav).
  // Sync in an effect rather than render so we don't mutate the store
  // during render (React rule).
  // Also: lazy-adopt localStorage into the module store when neither URL
  // nor store carry a value — covers the test case where beforeEach clears
  // localStorage, seeds a new value, then mounts the hook; the module
  // `currentValue` seeded at module-load time is already stale by then.
  useEffect(() => {
    if (urlValue !== null) {
      if (urlValue !== currentValue) {
        setCurrent(urlValue);
        writeLocalStorage(urlValue);
      }
      return;
    }
    // urlValue is null — reconcile module store against localStorage. This
    // covers both the test scenario (beforeEach clears localStorage and
    // remounts) and runtime (cross-route navigations back to "/").
    const stored = readLocalStorage();
    if (stored !== currentValue) {
      setCurrent(stored);
    }
  }, [urlValue]);

  const activeProjectId = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getSnapshot,
  );

  const setActiveProjectId = useCallback(
    (id: string | null) => {
      const normalized = normalize(id);
      setCurrent(normalized);
      writeLocalStorage(normalized);
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          if (normalized === null) {
            next.delete(URL_PARAM);
          } else {
            next.set(URL_PARAM, normalized);
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  return { activeProjectId, setActiveProjectId };
}
