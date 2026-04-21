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
 *
 * Iterate 3 remediation v2 — Surface 1 (2026-04-21):
 *   Rewritten to back the read value with `useState` instead of deriving
 *   it via `useMemo(() => readLocalStorage(), [urlValue])` on every render.
 *   The previous shape could leave the dropdown UI stale when switching to
 *   "All Projects" because the memo dep was `[urlValue]` only — a state
 *   change where urlValue did not move (e.g. clicking All Projects while
 *   already on All Projects via localStorage) would not trigger a new
 *   localStorage read, and because React re-renders could commit before
 *   the localStorage write the memo would observe stale value. The new
 *   shape uses a single committed state var, synchronously updated in the
 *   setter, and a URL-reconciliation effect that mirrors URL → state.
 *   Cross-tab sync is intentionally out of scope.
 */

import { useCallback, useEffect, useState } from "react";
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

  // Seed from URL (wins) or localStorage (fallback). Lazy initializer so
  // tests and SSR don't touch localStorage before it's safe.
  const [activeProjectId, setActiveProjectIdState] = useState<string | null>(
    () => (urlValue !== null ? urlValue : readLocalStorage()),
  );

  // Reconcile on URL change (back/forward nav, direct URL paste, or setter
  // pushing a new ?projectId=). The setter already updates state eagerly —
  // this effect catches the remaining URL-first entry paths and mirrors
  // them back to localStorage. Note we intentionally do NOT clear
  // localStorage when urlValue becomes null; the setter handles that path
  // explicitly, and a bare navigation to `/` shouldn't wipe the preference.
  useEffect(() => {
    if (urlValue !== null) {
      if (urlValue !== activeProjectId) {
        setActiveProjectIdState(urlValue);
      }
      writeLocalStorage(urlValue);
    }
    // `activeProjectId` intentionally omitted from deps — including it
    // causes a feedback loop where the setter already updated state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlValue]);

  const setActiveProjectId = useCallback(
    (id: string | null) => {
      const normalized = normalize(id);

      // 1. Commit state eagerly so the next render shows the new filter
      //    without waiting for URL → state reconciliation. Eliminates the
      //    "All Projects" stale-dropdown class of bug.
      setActiveProjectIdState(normalized);

      // 2. Persist to localStorage synchronously so sibling tabs (and the
      //    next mount) see the new selection.
      writeLocalStorage(normalized);

      // 3. Mirror into the URL so deep-linked screenshots / bug reports
      //    round-trip the filter. `replace: true` keeps the history stack
      //    clean (filter toggling is not a navigation event).
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
