/*
 * useHideIgnored — per-project "Hide ignored entries" toggle for the
 * TaskDetail FolderTree (iterate 3 section 04, FR-03.33).
 *
 * Storage key pattern: `webui.tree.hideIgnored.<projectId>` (plan § 7 O6).
 * Default is **false** — ignored entries render muted by default. Toggle
 * state persists per project, so switching to another project restores
 * that project's preference independently.
 */

import { useCallback, useEffect, useState } from "react";

const KEY_PREFIX = "webui.tree.hideIgnored.";

function storageKey(projectId: string): string {
  return `${KEY_PREFIX}${projectId}`;
}

function readFlag(projectId: string): boolean {
  if (typeof localStorage === "undefined") return false;
  try {
    const raw = localStorage.getItem(storageKey(projectId));
    if (raw === null) return false;
    const parsed = JSON.parse(raw);
    return parsed === true;
  } catch {
    return false;
  }
}

export function useHideIgnored(
  projectId: string,
): [boolean, (next: boolean) => void] {
  const [hide, setHide] = useState<boolean>(() => readFlag(projectId));

  // When the projectId changes (user nav'd to a task under a different
  // project), re-read the per-project flag so we don't carry the previous
  // project's preference.
  useEffect(() => {
    setHide(readFlag(projectId));
  }, [projectId]);

  const set = useCallback(
    (next: boolean) => {
      setHide(next);
      try {
        localStorage.setItem(storageKey(projectId), JSON.stringify(next));
      } catch {
        /* ignore quota / disabled */
      }
    },
    [projectId],
  );

  return [hide, set];
}
