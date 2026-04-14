import { readFileSync, statSync } from "node:fs";
import { join, dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * Iterate 14.1 — cached profile JSON loader.
 *
 * Reads profile definitions from `shared/profiles/{name}.json`, caches them
 * in-memory keyed by profile name, and invalidates on file mtime change so
 * hot reloads during dev pick up edits without a server restart.
 *
 * Used by:
 *   - ProjectManager.hasPreviewCapability() — to check dev_server.command.
 *   - (future) GET /api/profiles route.
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
 * Resolve the default `shared/profiles/` directory from the server source
 * location: `webui/server/src/core/profile-loader.ts` → repo root is 4 levels
 * up (core → src → server → webui → repo), then `shared/profiles`.
 *
 * Exported so callers (routes, manager) can pass it explicitly — avoids
 * spreading `__dirname` resolution code across the codebase.
 */
export function getProfilesDir(): string {
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = dirname(__filename);
  // core → src → server → webui → repo root
  return resolve(__dirname, "..", "..", "..", "..", "shared", "profiles");
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

/** Test helper — drops the in-memory cache so tests can seed fresh state. */
export function clearProfileCache(): void {
  cache.clear();
}
