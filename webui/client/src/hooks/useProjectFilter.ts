/*
 * useProjectFilter — single source of truth for the active-project filter.
 *
 * Consumed by Sidebar (project list highlight + click), TaskBoardPage
 * (filter chip bar), and later InboxPage (section 05 filter chip). External
 * review O27 called out: DO NOT duplicate this state per page, or URL and
 * localStorage will drift.
 *
 * Reconciliation order on mount:
 *   1. If URL carries ?projectId=<x>, that wins AND is mirrored into
 *      localStorage so a later navigation without the query still shows
 *      the selection.
 *   2. Otherwise, read localStorage. Missing / null / "" = All Projects
 *      (encoded as null in the hook's state).
 *
 * Reserved literal UNASSIGNED_PROJECT_ID ("unassigned") is a valid value
 * for the synthesized pseudo-project bucket.
 */

import { useCallback, useEffect, useMemo } from "react";
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
    // SSR / tests without localStorage — fall through.
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
    // Ignore — not load-bearing for the in-session filter.
  }
}

export interface UseProjectFilterResult {
  activeProjectId: string | null;
  setActiveProjectId: (id: string | null) => void;
}

export function useProjectFilter(): UseProjectFilterResult {
  const [searchParams, setSearchParams] = useSearchParams();

  const urlValue = normalize(searchParams.get(URL_PARAM));
  const activeProjectId = useMemo<string | null>(() => {
    // URL wins. Empty string → treated as null. Any other value overrides
    // localStorage.
    if (urlValue !== null) return urlValue;
    return readLocalStorage();
  }, [urlValue]);

  // Mirror URL selection into localStorage so later cross-view navigation
  // without the query keeps the filter. Intentionally a one-shot
  // reconciliation effect — the setter below writes localStorage on every
  // explicit set call.
  useEffect(() => {
    if (urlValue !== null) {
      writeLocalStorage(urlValue);
    }
  }, [urlValue]);

  const setActiveProjectId = useCallback(
    (id: string | null) => {
      const normalized = normalize(id);

      // Update localStorage synchronously — avoids tab-to-tab lag and
      // matches the URL commit below.
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
