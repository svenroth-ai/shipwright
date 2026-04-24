/**
 * Cross-repo contract version check.
 *
 * The WebUI reads JSON artefacts that are written by the Shipwright
 * plugins (a *different* repo once the split lands). To make silent
 * schema drift visible we stamp each cross-repo artefact with a
 * `contractVersion` / `schemaVersion` integer that the WebUI compares
 * against a library-side "known max".
 *
 * Intentionally fail-soft: an unknown-higher version logs a warning
 * and the caller proceeds. Failing the read would lock users out of
 * otherwise-functioning projects just because their plugin side is
 * newer than the observer — the opposite of what the WebUI should do.
 */

/**
 * Highest `contractVersion` this WebUI build knows how to read for
 * `shipwright_run_config.json`. Bump in lockstep with the plugin
 * writer (plugins/shipwright-project/scripts/write_run_config.py).
 */
export const RUN_CONFIG_CONTRACT_VERSION = 1;

/**
 * Highest `schemaVersion` this WebUI build knows how to read for
 * `<project>/.webui/actions.json`.
 */
export const ACTIONS_SCHEMA_VERSION = 1;

/**
 * Highest schema version this WebUI build knows how to parse for the
 * stack-profile JSON envelope (the shape of files in
 * `server/profiles/*.json` or `shared/profiles/*.json`). Compared
 * against the integer content of `<profilesDir>/PROFILE_SCHEMA_VERSION`
 * when present.
 */
export const PROFILE_SCHEMA_VERSION = 1;

interface WarnOnceKey {
  artefact: string;
  path: string;
  observedVersion: number;
}

const warnedOnce = new Set<string>();

function warnKey(k: WarnOnceKey): string {
  return `${k.artefact}::${k.path}::${k.observedVersion}`;
}

/**
 * Check a parsed artefact's declared version against the library's
 * known max. Logs one JSON warning per (artefact, path, version)
 * triple; subsequent calls with the same triple stay silent so we
 * don't spam the log.
 *
 * Returns `true` when the version is within the known range (the
 * common case); `false` when a warning was emitted. Callers use the
 * return value only for testability — production code ignores it.
 */
export function checkContractVersion(input: {
  artefact: string;
  path: string;
  declared: unknown;
  knownMax: number;
  fieldName?: string;
}): boolean {
  const { artefact, path, declared, knownMax, fieldName = "contractVersion" } =
    input;

  // Undefined/missing is fine — contract versions only landed in v0.3.2;
  // older artefacts on disk won't have them, and that's the whole point
  // of "fail-soft": keep reading.
  if (declared === undefined || declared === null) return true;

  if (typeof declared !== "number" || !Number.isInteger(declared)) {
    // Not a blocker either — but emit once so we notice corruption.
    const k = warnKey({ artefact, path, observedVersion: -1 });
    if (!warnedOnce.has(k)) {
      warnedOnce.add(k);
      console.warn(
        JSON.stringify({
          level: "warn",
          event: "contract_version_malformed",
          artefact,
          path,
          field: fieldName,
          declared: String(declared).slice(0, 64),
        }),
      );
    }
    return false;
  }

  if (declared > knownMax) {
    const k = warnKey({ artefact, path, observedVersion: declared });
    if (!warnedOnce.has(k)) {
      warnedOnce.add(k);
      console.warn(
        JSON.stringify({
          level: "warn",
          event: "contract_version_ahead",
          artefact,
          path,
          field: fieldName,
          declared,
          knownMax,
          hint:
            "WebUI build is older than the plugin side. Reading proceeds; " +
            "unknown fields are ignored. Update the WebUI if behaviour drifts.",
        }),
      );
    }
    return false;
  }

  return true;
}

/** Test helper — reset the one-shot warn memo between tests. */
export function _resetWarnMemo(): void {
  warnedOnce.clear();
}
