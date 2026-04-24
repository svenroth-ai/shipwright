import { readFileSync, statSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import {
  checkContractVersion,
  PROFILE_SCHEMA_VERSION,
} from "./contract-version.js";

/**
 * Cached profile JSON loader.
 *
 * Reads profile definitions from a profiles directory, caches them in-memory
 * keyed by profile name, and invalidates on file mtime change so hot reloads
 * during dev pick up edits without a server restart.
 *
 * Used by:
 *   - ProjectManager.hasPreviewCapability() — to check dev_server.command.
 *   - GET /api/profiles route.
 */

export interface ProfileConfig {
  name: string;
  label?: string;
  description?: string;
  dev_server?: { command: string; port: number; [key: string]: unknown };
  [key: string]: unknown;
}

interface CacheEntry {
  data: ProfileConfig;
  mtimeMs: number;
}

const cache = new Map<string, CacheEntry>();

/**
 * Walk up from the given start directory until we find the WebUI server's
 * own `package.json` (identified by its `name` field). Works for both the
 * dev layout (`webui/server/src/core/`) and the build layout
 * (`webui/server/dist/core/`), because both ancestor chains pass through
 * `webui/server/` where the package.json lives.
 *
 * Exported so tests can drive it with a synthetic start directory.
 */
export function findServerRoot(startDir?: string): string | null {
  const start = startDir ?? dirname(fileURLToPath(import.meta.url));
  let current = start;
  for (let i = 0; i < 12; i++) {
    const pkg = join(current, "package.json");
    try {
      const raw = readFileSync(pkg, "utf-8");
      const parsed = JSON.parse(raw) as { name?: string };
      if (parsed.name?.startsWith("shipwright-command-center-server")) {
        return current;
      }
    } catch {
      // package.json not at this level (or unreadable); keep walking.
    }
    const parent = dirname(current);
    if (parent === current) return null; // reached filesystem root
    current = parent;
  }
  return null;
}

/**
 * Resolve the profiles directory in priority order:
 *
 *   1. `SHIPWRIGHT_PROFILES_DIR` — explicit user/operator override.
 *   2. `SHIPWRIGHT_MONOREPO_PATH` + `shared/profiles` — dev-loop helper so
 *      the WebUI reads live profiles while iterating on the Shipwright
 *      monorepo (instead of the stale bundled snapshot).
 *   3. Bundled `<server-root>/profiles/` — the default once the WebUI
 *      lives in its own repo. Resolution is layout-agnostic: see
 *      `findServerRoot`.
 *
 * Returns a path even if it does not exist — `loadProfile` is fail-soft
 * and will simply return `null` for unknown names.
 */
export function getProfilesDir(): string {
  const override = process.env.SHIPWRIGHT_PROFILES_DIR?.trim();
  if (override) return override;

  const monorepoPath = process.env.SHIPWRIGHT_MONOREPO_PATH?.trim();
  if (monorepoPath) return resolve(monorepoPath, "shared", "profiles");

  const serverRoot = findServerRoot();
  if (serverRoot) return resolve(serverRoot, "profiles");

  // Last-resort fallback — if the marker walk ever fails we still return
  // *something* so callers don't crash. loadProfile will null out cleanly.
  const here = dirname(fileURLToPath(import.meta.url));
  return resolve(here, "..", "..", "profiles");
}

/**
 * Load a profile by name. Returns parsed ProfileConfig or null if the file
 * does not exist or fails to parse. Fail-soft by design — a broken profile
 * must never crash the server or break project listing.
 */
export function loadProfile(
  profileName: string,
  profilesDir: string,
): ProfileConfig | null {
  if (!profileName) return null;
  const path = join(profilesDir, `${profileName}.json`);
  try {
    const stat = statSync(path);
    const cached = cache.get(profileName);
    if (cached && cached.mtimeMs === stat.mtimeMs) return cached.data;
    const raw = readFileSync(path, "utf-8");
    const data = JSON.parse(raw) as ProfileConfig;
    cache.set(profileName, { data, mtimeMs: stat.mtimeMs });
    return data;
  } catch {
    return null;
  }
}

let profileSchemaVersionChecked = false;

/** Test helper — drops the in-memory cache so tests can seed fresh state. */
export function clearProfileCache(): void {
  cache.clear();
  profileSchemaVersionChecked = false;
}

/**
 * Read `<profilesDir>/PROFILE_SCHEMA_VERSION` once and compare against
 * the library's known max. Idempotent — subsequent calls are no-ops
 * unless `clearProfileCache` is invoked (tests). No-op when the marker
 * file is absent (older bundles / upstream monorepos without the
 * marker). Call this at server startup or on first load — it is not
 * required for correctness, only for drift visibility.
 */
export function verifyProfileSchemaVersion(profilesDir: string): void {
  if (profileSchemaVersionChecked) return;
  profileSchemaVersionChecked = true;

  const markerPath = join(profilesDir, "PROFILE_SCHEMA_VERSION");
  let raw: string;
  try {
    raw = readFileSync(markerPath, "utf-8").trim();
  } catch {
    // Marker absent — nothing to verify, no warning needed.
    return;
  }
  const declared = Number.parseInt(raw, 10);
  checkContractVersion({
    artefact: "PROFILE_SCHEMA_VERSION",
    path: markerPath,
    declared: Number.isFinite(declared) ? declared : raw,
    knownMax: PROFILE_SCHEMA_VERSION,
    fieldName: "PROFILE_SCHEMA_VERSION",
  });
}
