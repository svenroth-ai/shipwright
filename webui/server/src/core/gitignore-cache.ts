/*
 * gitignore-cache.ts — (projectRoot, mtime)-keyed cache around the
 * `ignore` package (section 04a, spec § 5.2 / § 7 O17).
 *
 * Contract:
 *   - loadIgnore(projectRoot) returns an `ignore` instance pre-loaded with
 *     platform defaults (.git, node_modules, dist, build, .shipwright-webui, .webui)
 *     plus any patterns from <projectRoot>/.gitignore when present.
 *   - Cache key is (projectRoot, .gitignore mtime_ms). When .gitignore is
 *     absent the "mtime" slot is a sentinel 0 so the defaults-only instance
 *     is still cached.
 *   - Cache invalidates when the mtime changes (edit or touch).
 *   - Cache survives absence (stat → ENOENT is cached with mtime 0).
 *
 * This avoids re-parsing .gitignore on every tree-route expand request.
 */

import { statSync, readFileSync } from "node:fs";
import path from "node:path";
import ignoreModule, { type Ignore } from "ignore";

// The `ignore` package ships CJS with a `default` export that TS can't
// resolve as callable under NodeNext + esModuleInterop in every tsc edge
// case (the default import lands on the whole module-namespace object).
// Normalize at the module boundary so the call-site below stays clean.
const ignore = (ignoreModule as unknown as {
  default?: () => Ignore;
}).default ?? (ignoreModule as unknown as () => Ignore);

/**
 * Defaults applied to every project regardless of .gitignore presence.
 * These are always ignored (muted in the tree UI) — they rarely contain
 * anything the user wants to preview through SmartViewer and expanding
 * them on a large node_modules would stall the UI.
 */
const DEFAULT_IGNORED = [
  ".git",
  "node_modules",
  "dist",
  "build",
  ".shipwright-webui",
  ".webui",
];

interface CacheEntry {
  /** mtimeMs of .gitignore at load time, or 0 when the file was absent. */
  mtimeMs: number;
  /** The ignore() instance — safe to share across calls (no per-call state). */
  ig: Ignore;
}

/** Internal module-scoped cache. Keyed by absolute projectRoot. */
const cache = new Map<string, CacheEntry>();

/** Test instrumentation — counts parser invocations. */
let _parses = 0;

/**
 * Load (or reuse) an `ignore` instance for the given project root.
 *
 * The returned instance has the default patterns + any .gitignore patterns
 * pre-applied. `ig.ignores(relpath)` returns true when the path matches.
 */
export function loadIgnore(projectRoot: string): Ignore {
  const absRoot = path.resolve(projectRoot);
  const gitignorePath = path.join(absRoot, ".gitignore");

  // Probe .gitignore mtime. If the file doesn't exist we use mtimeMs=0 as
  // the cache sentinel; a subsequent `touch` that creates the file will
  // produce a non-zero mtimeMs and invalidate the cache entry.
  let currentMtimeMs = 0;
  let gitignoreContent = "";
  try {
    const st = statSync(gitignorePath);
    currentMtimeMs = st.mtimeMs;
  } catch (err) {
    if ((err as NodeJS.ErrnoException)?.code !== "ENOENT") {
      // Permission or I/O failure — propagate so the caller can 500
      // rather than silently ship a defaults-only guard.
      throw err;
    }
  }

  const cached = cache.get(absRoot);
  if (cached && cached.mtimeMs === currentMtimeMs) {
    return cached.ig;
  }

  // (Re)parse. Defaults first, then .gitignore rules.
  if (currentMtimeMs > 0) {
    try {
      gitignoreContent = readFileSync(gitignorePath, "utf-8");
    } catch (err) {
      // Race window: file vanished between stat() and readFileSync().
      // Treat as absent; will retry on next call if it reappears.
      if ((err as NodeJS.ErrnoException)?.code !== "ENOENT") {
        throw err;
      }
      currentMtimeMs = 0;
    }
  }

  const ig = ignore();
  ig.add(DEFAULT_IGNORED);
  if (gitignoreContent.trim().length > 0) {
    ig.add(gitignoreContent);
  }
  _parses++;

  cache.set(absRoot, { mtimeMs: currentMtimeMs, ig });
  return ig;
}

/** Test-only: clear the module-scoped cache between tests. */
export function __clearGitignoreCacheForTests(): void {
  cache.clear();
  _parses = 0;
}

/** Test-only: expose the parse counter so tests can verify cache behavior. */
export function __getGitignoreCacheStatsForTests(): { parses: number; size: number } {
  return { parses: _parses, size: cache.size };
}
