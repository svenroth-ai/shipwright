/*
 * path-guard.ts — pure traversal guard shared by the tree + file routes
 * (section 04a, spec § 5.1).
 *
 * Rationale: a naive `resolved.startsWith(projectRoot)` check is UNSAFE on
 * two axes (plan § 4.2, § 7 O8):
 *   1. sibling-prefix trap — "/projects/repo-ab/secret" starts with
 *      "/projects/repo-a", so startsWith would let the user escape a
 *      same-parent sibling project.
 *   2. Windows case-insensitivity + drive-letter semantics — path.resolve
 *      can land on a different drive without any leading "..".
 *
 * The contract below uses `path.resolve` → `path.relative` and rejects
 * whenever the resulting relative path starts with ".." as its own segment
 * (not as a substring — otherwise a legitimate ".." inside a filename
 * like "..rc.json" would be rejected too; path.relative never produces
 * such output but the check is still segment-wise for correctness).
 *
 * Windows drive-hop attempts are caught via the `absolute_input` branch
 * (e.g. "D:\\stuff" is absolute by isAbsolute, and on POSIX "/etc/passwd"
 * trips the same branch).
 */

import path from "node:path";
import { realpathSync } from "node:fs";

export type PathGuardReason =
  | "traversal"
  | "absolute_input"
  | "drive_change"
  | "symlink_escape";

export type PathGuardResult =
  | { ok: true; absolute: string }
  | { ok: false; reason: PathGuardReason };

/**
 * Check whether `relpath` resolves safely under `projectRoot`.
 *
 * @param projectRoot Absolute path to the project directory.
 * @param relpath     User-supplied path. May be "" or "." to mean root.
 */
export function pathGuard(projectRoot: string, relpath: string): PathGuardResult {
  // Normalize the input. An empty string or "." both mean "project root".
  const input = relpath ?? "";

  // 0. Reject null-byte injection. Node's fs layer rejects these with a
  //    generic ERR_INVALID_ARG_VALUE; catching at the guard boundary gives
  //    a consistent "traversal"-class error code to the UI.
  if (input.indexOf("\0") !== -1) {
    return { ok: false, reason: "traversal" };
  }

  // 1. Reject absolute input — prevents /etc/passwd, D:\stuff, C:/foo
  //    regardless of platform. path.isAbsolute on win32 treats both "/foo"
  //    and "C:\\foo" as absolute; on POSIX only "/foo".
  //
  //    We also check path.win32.isAbsolute explicitly so a POSIX-configured
  //    test run still rejects "D:\\stuff" as absolute_input — the guard
  //    must be safe on both hosts. Likewise path.posix.isAbsolute catches
  //    "/etc/passwd" on a Windows host.
  if (
    input.length > 0 &&
    (path.isAbsolute(input) ||
      path.win32.isAbsolute(input) ||
      path.posix.isAbsolute(input))
  ) {
    return { ok: false, reason: "absolute_input" };
  }

  // 2. Resolve the input against the project root. path.resolve normalizes
  //    "./a/../b" → "b", resolves "..", and on Windows keeps drive letters.
  const resolvedRoot = path.resolve(projectRoot);
  const resolved = path.resolve(resolvedRoot, input);

  // 3. Windows drive-letter change check. On POSIX this is a no-op. On
  //    Windows, if path.resolve produced a path on a different drive than
  //    the project root (possible if the input used "\\\\?\\" UNC-style
  //    prefixes that slipped past isAbsolute), reject.
  if (process.platform === "win32") {
    const rootDrive = resolvedRoot.slice(0, 2).toLowerCase();
    const resolvedDrive = resolved.slice(0, 2).toLowerCase();
    if (
      rootDrive.endsWith(":") &&
      resolvedDrive.endsWith(":") &&
      rootDrive !== resolvedDrive
    ) {
      return { ok: false, reason: "drive_change" };
    }
  }

  // 4. The actual traversal check: compute path.relative and ensure the
  //    result does NOT escape the root. Escape manifests as:
  //      - rel === ".."                         (exact-match upward)
  //      - rel starts with ".." + path.sep      (upward-then-deeper)
  //    We explicitly check path.sep AND "/" because on Windows path.relative
  //    can return "..\\foo" but a POSIX-style "../foo" is also a valid
  //    traversal expression.
  const rel = path.relative(resolvedRoot, resolved);

  if (
    rel === ".." ||
    rel.startsWith(".." + path.sep) ||
    rel.startsWith("../")
  ) {
    return { ok: false, reason: "traversal" };
  }

  // 5. Defense in depth: if path.relative returned an absolute path, the
  //    resolved target is on a completely different root. Treat as
  //    traversal.
  if (path.isAbsolute(rel)) {
    return { ok: false, reason: "drive_change" };
  }

  return { ok: true, absolute: resolved };
}

/**
 * Follow-up guard that resolves symlinks on disk and re-verifies the result
 * still lands under the project root. Must be called AFTER `pathGuard` and
 * ONLY when the path is known to exist (i.e. after a successful stat).
 *
 * Rationale (plan § 7 O8 "Symlink escape"):
 *   path.resolve / path.relative operate on strings, not on the filesystem.
 *   A malicious project could contain `config -> /etc`, and a request for
 *   `config/passwd` would pass the string-only pathGuard because the
 *   textual relative path is "config/passwd". `fs.realpathSync` resolves
 *   the symlink to `/etc/passwd`, which a re-application of path.relative
 *   against the project root will reject as a traversal.
 *
 * On ENOENT (symlink target missing), we return `symlink_escape` as well —
 * safer to refuse than to silently succeed when realpath can't verify.
 * Callers should NOT gate on this failure for the "path doesn't exist"
 * case — they should have already stat()-ed first.
 *
 * Returns the realpath-resolved absolute path on success (the caller may
 * prefer to read from the realpath rather than the possibly-symlinked
 * guard.absolute, though in practice fs reads against either produce the
 * same bytes as long as both land under the root).
 */
export function realPathGuard(
  projectRoot: string,
  absoluteInsideRoot: string,
): PathGuardResult {
  const resolvedRoot = path.resolve(projectRoot);
  let realRoot: string;
  let realTarget: string;
  try {
    realRoot = realpathSync(resolvedRoot);
    realTarget = realpathSync(absoluteInsideRoot);
  } catch {
    // If either side can't be realpath'd (permissions, race), refuse
    // rather than proceed with the unverified path.
    return { ok: false, reason: "symlink_escape" };
  }

  // Re-apply the traversal check against the realpath results.
  if (process.platform === "win32") {
    const rootDrive = realRoot.slice(0, 2).toLowerCase();
    const targetDrive = realTarget.slice(0, 2).toLowerCase();
    if (
      rootDrive.endsWith(":") &&
      targetDrive.endsWith(":") &&
      rootDrive !== targetDrive
    ) {
      return { ok: false, reason: "symlink_escape" };
    }
  }

  const rel = path.relative(realRoot, realTarget);
  if (
    rel === ".." ||
    rel.startsWith(".." + path.sep) ||
    rel.startsWith("../") ||
    path.isAbsolute(rel)
  ) {
    return { ok: false, reason: "symlink_escape" };
  }

  return { ok: true, absolute: realTarget };
}
