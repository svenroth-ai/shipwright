/*
 * Project-scoped actions.json loader with bundled-default fallback.
 *
 * Iterate 3 section 03 — plan.md § 2.1 + ADR-036/039.
 *
 * Precedence (verbatim from the spec):
 *   1. `<project.path>/.webui/actions.json` if present and parseable.
 *   2. Otherwise the bundled `webui/server/src/config/default-actions.json`.
 *
 * A malformed user-side file does NOT break the server — the loader
 * falls through to the bundled default and emits a non-blocking
 * diagnostic in the returned `diagnostics` array (external review O24).
 * The route handler surfaces it to the client; the user sees a chip but
 * the Task Board stays usable.
 *
 * Caching follows `profile-loader.ts` — keyed by projectPath, invalidated
 * on actions.json mtime change. Eliminates per-request JSON re-parse for
 * happy-path projects.
 *
 * This module does NOT validate the placeholder allowlist or the schema
 * itself. That is the route layer's job (via
 * `actions-substitute.validateTemplate` + `validateActionsSchema`), so
 * the loader stays pure I/O.
 */

import { readFileSync, statSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import {
  checkContractVersion,
  ACTIONS_SCHEMA_VERSION,
} from "./contract-version.js";

export interface ActionDefinition {
  id: string;
  label: string;
  kind: "external_launch";
  description?: string;
  command_template: string;
  modal_fields?: string[];
}

export interface PhaseDefinition {
  id: string;
  label: string;
  color?: string;
}

export interface PreviewSpec {
  /** `"auto"` (default — follow profile.stack.frontend), `true`, or `false`. */
  enabled: boolean | "auto";
}

export interface ResolvedActions {
  schemaVersion: number;
  defaults: {
    autonomy: "guided" | "autonomous";
  };
  actions: ActionDefinition[];
  phases: PhaseDefinition[];
  preview: PreviewSpec;
}

export interface LoaderDiagnostic {
  code: string;
  path?: string;
  detail?: string;
}

export interface LoadResult {
  /** The resolved config (bundled default on miss / malformed). */
  actions: ResolvedActions;
  /** True when `.webui/actions.json` was used; false when bundled default. */
  fromUser: boolean;
  diagnostics: LoaderDiagnostic[];
}

export interface LoaderDeps {
  readFileSync?: (path: string, encoding: "utf-8" | "utf8") => string;
  statSync?: (path: string) => { mtimeMs: number };
}

interface CacheEntry {
  data: ResolvedActions;
  mtimeMs: number | null; // null = bundled default (no user file)
  fromUser: boolean;
  diagnostics: LoaderDiagnostic[];
}

const cache = new Map<string, CacheEntry>();

/**
 * Resolve the bundled default path: `webui/server/src/config/default-actions.json`.
 * core → src → ../config/default-actions.json.
 */
function defaultPath(): string {
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = dirname(__filename);
  return resolve(__dirname, "..", "config", "default-actions.json");
}

let bundledDefault: ResolvedActions | null = null;
let bundledDefaultLoadedAt = 0;

/**
 * Load (and cache) the bundled default. Runs once per process. A
 * malformed bundled default is a startup-time failure — the whole
 * server aborts because that's a build-level bug, not user input.
 *
 * Uses node's real `fs.readFileSync` regardless of the injected
 * per-project deps — the bundled default is an installation asset, not
 * something that belongs in a unit test's in-memory filesystem.
 */
export function loadBundledDefault(): ResolvedActions {
  if (bundledDefault) return bundledDefault;
  const raw = readFileSync(defaultPath(), "utf-8");
  const parsed = JSON.parse(raw) as ResolvedActions;
  bundledDefault = parsed;
  bundledDefaultLoadedAt = Date.now();
  return parsed;
}

/** Test helper — drops the bundled default + per-project cache. */
export function clearActionsCache(): void {
  cache.clear();
  bundledDefault = null;
  bundledDefaultLoadedAt = 0;
}

/**
 * Load actions for a given project path. Returns the bundled default
 * when the user file is missing / malformed; diagnostics carry any
 * non-fatal warnings (route layer surfaces them as a chip).
 */
export function loadActionsForProject(
  projectPath: string,
  deps: LoaderDeps = {},
): LoadResult {
  const read = deps.readFileSync ?? readFileSync;
  const stat = deps.statSync ?? statSync;

  const userPath = join(projectPath, ".webui", "actions.json");

  // mtime-based cache. mtimeMs = null = cached "no user file" branch.
  let mtimeMs: number | null = null;
  try {
    mtimeMs = stat(userPath).mtimeMs;
  } catch {
    mtimeMs = null;
  }

  const cached = cache.get(projectPath);
  if (cached && cached.mtimeMs === mtimeMs) {
    return {
      actions: cached.data,
      fromUser: cached.fromUser,
      diagnostics: cached.diagnostics,
    };
  }

  if (mtimeMs === null) {
    // No user file — bundled default.
    const bundled = loadBundledDefault();
    const entry: CacheEntry = {
      data: bundled,
      mtimeMs: null,
      fromUser: false,
      diagnostics: [],
    };
    cache.set(projectPath, entry);
    return { actions: bundled, fromUser: false, diagnostics: [] };
  }

  // User file present — try to parse.
  try {
    const raw = read(userPath, "utf-8");
    const parsed = JSON.parse(raw) as ResolvedActions;
    checkContractVersion({
      artefact: ".webui/actions.json",
      path: userPath,
      declared: parsed.schemaVersion,
      knownMax: ACTIONS_SCHEMA_VERSION,
      fieldName: "schemaVersion",
    });
    const entry: CacheEntry = {
      data: parsed,
      mtimeMs,
      fromUser: true,
      diagnostics: [],
    };
    cache.set(projectPath, entry);
    return { actions: parsed, fromUser: true, diagnostics: [] };
  } catch (err) {
    const diag: LoaderDiagnostic = {
      code: "actions_file_malformed",
      path: userPath,
      detail: String(err).slice(0, 200),
    };
    const bundled = loadBundledDefault();
    const entry: CacheEntry = {
      data: bundled,
      mtimeMs,
      fromUser: false,
      diagnostics: [diag],
    };
    cache.set(projectPath, entry);
    // Warn once on the server side so an operator sees it in logs too.
    // Using plain console.warn to match project-manager style.
    console.warn(
      JSON.stringify({
        level: "warn",
        message: "actions.json malformed; falling back to bundled default",
        projectPath,
        path: userPath,
      }),
    );
    return { actions: bundled, fromUser: false, diagnostics: [diag] };
  }
}

/** Non-test diagnostic accessor — lets index.ts report bundled-load age. */
export function bundledDefaultLoadedAtMs(): number {
  return bundledDefaultLoadedAt;
}
