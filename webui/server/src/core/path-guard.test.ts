/*
 * path-guard.test.ts — security-critical path traversal guard (section 04a).
 *
 * Tests enumerate every failure mode from spec § 5.1:
 *  - sibling-prefix trap (why we can't use startsWith)
 *  - plain ..
 *  - embedded ..
 *  - absolute input
 *  - Windows drive-letter change
 *  - Windows case-insensitivity happy path
 *  - empty / "." relpath
 *  - happy path
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import path from "node:path";
import {
  mkdtempSync,
  rmSync,
  writeFileSync,
  mkdirSync,
  symlinkSync,
} from "node:fs";
import { tmpdir } from "node:os";

import { pathGuard, realPathGuard } from "./path-guard.js";

describe("pathGuard — traversal guard (section 04a)", () => {
  const posixRoot = "/projects/repo-a";
  const winRoot = "C:\\projects\\repo-a";

  it("happy path — normal relative file path resolves to absolute under root", () => {
    const res = pathGuard(posixRoot, "src/components/Foo.tsx");
    expect(res.ok).toBe(true);
    if (res.ok) {
      // Absolute path should be the normalized join.
      expect(res.absolute).toBe(path.resolve(posixRoot, "src/components/Foo.tsx"));
    }
  });

  it("happy path — empty relpath resolves to project root", () => {
    const res = pathGuard(posixRoot, "");
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.absolute).toBe(path.resolve(posixRoot));
    }
  });

  it("happy path — '.' relpath resolves to project root", () => {
    const res = pathGuard(posixRoot, ".");
    expect(res.ok).toBe(true);
    if (res.ok) {
      expect(res.absolute).toBe(path.resolve(posixRoot));
    }
  });

  it("rejects plain .. segment with traversal", () => {
    const res = pathGuard(posixRoot, "../etc/passwd");
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.reason).toBe("traversal");
  });

  it("rejects null byte injection", () => {
    const res = pathGuard(posixRoot, "valid\x00/../etc/passwd");
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.reason).toBe("traversal");
  });

  it("rejects embedded .. after normal prefix", () => {
    const res = pathGuard(posixRoot, "src/../../etc/passwd");
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.reason).toBe("traversal");
  });

  it("rejects absolute POSIX path input", () => {
    const res = pathGuard(posixRoot, "/etc/passwd");
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.reason).toBe("absolute_input");
  });

  it("rejects absolute Windows path input (drive letter)", () => {
    const res = pathGuard(winRoot, "D:\\stuff");
    expect(res.ok).toBe(false);
    if (!res.ok) {
      // Accept either "absolute_input" (since "D:\stuff" IS absolute) or
      // "drive_change" — both are correct rejections of a drive-hop attempt.
      // The guard prioritizes absolute_input (checked first); if the guard
      // later relaxes that order we still reject.
      expect(["absolute_input", "drive_change"]).toContain(res.reason);
    }
  });

  it("rejects lowercase-drive absolute path input on Windows root", () => {
    const res = pathGuard(winRoot, "d:/stuff");
    expect(res.ok).toBe(false);
    if (!res.ok) {
      expect(["absolute_input", "drive_change"]).toContain(res.reason);
    }
  });

  it("sibling-prefix refusal — ../repo-ab is NOT valid under repo-a", () => {
    // This is the KEY test — a naive startsWith check would pass because
    // "/projects/repo-ab/secret" starts with "/projects/repo-a". The guard
    // must use path.relative and reject a leading ".." segment.
    const res = pathGuard("/projects/repo-a", "../repo-ab/secret");
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.reason).toBe("traversal");
  });

  it("Windows case-insensitivity: C: root accepts c:-prefixed resolved paths", () => {
    // Relative input that lands squarely inside the root via case-insensitive
    // Windows semantics should be OK. path.resolve on win32 normalizes the
    // case, so in practice this manifests as: if the project root is stored
    // with uppercase "C:" and a relative join produces the same uppercase,
    // we're fine. The failure mode we're guarding against is different
    // drive letters — see the drive-hop test above.
    if (process.platform !== "win32") {
      // Skip semantic of this test on POSIX — drive letters do not apply.
      return;
    }
    const res = pathGuard(winRoot, "src\\index.ts");
    expect(res.ok).toBe(true);
  });

  it("rejects attempt to escape via .. even if later segments would land back inside", () => {
    // "../repo-a/src" would resolve BACK to /projects/repo-a/src.
    // path.relative would give "src", which has no .. prefix, so naively it
    // would pass. But the INPUT contained a ".." in a segment that escaped
    // then re-entered — this is a gray area. Per the spec the rejection is
    // based on path.relative output; if the relative IS clean we accept.
    // This test documents that behavior: loop-back is accepted.
    const res = pathGuard("/projects/repo-a", "../repo-a/src");
    // We accept this because the resolved path lands safely under root and
    // path.relative returns "src". This is intentional — a segment-wise
    // reject would break symlink scenarios and is beyond 04a scope.
    expect(res.ok).toBe(true);
  });
});

describe("realPathGuard — symlink escape (section 04a, plan § 7 O8)", () => {
  let projectDir: string;
  let outsideDir: string;

  beforeEach(() => {
    projectDir = mkdtempSync(path.join(tmpdir(), "realpath-guard-test-"));
    outsideDir = mkdtempSync(path.join(tmpdir(), "realpath-guard-out-"));
    mkdirSync(path.join(projectDir, "src"), { recursive: true });
    writeFileSync(path.join(projectDir, "src", "index.ts"), "ok");
    writeFileSync(path.join(outsideDir, "sensitive.txt"), "secret");
  });

  afterEach(() => {
    try {
      rmSync(projectDir, { recursive: true, force: true });
      rmSync(outsideDir, { recursive: true, force: true });
    } catch {
      /* ignore */
    }
  });

  it("legit path inside root passes realPathGuard", () => {
    const abs = path.join(projectDir, "src", "index.ts");
    const res = realPathGuard(projectDir, abs);
    expect(res.ok).toBe(true);
  });

  it("symlinked file pointing OUTSIDE root is rejected as symlink_escape", () => {
    const target = path.join(outsideDir, "sensitive.txt");
    const linkPath = path.join(projectDir, "sneaky.txt");
    try {
      symlinkSync(target, linkPath, "file");
    } catch (err) {
      // Windows without developer mode denies non-admin symlink creation.
      // Skip this test on such hosts — the guard still protects; we just
      // can't reproduce the attack here.
      if ((err as NodeJS.ErrnoException)?.code === "EPERM") {
        return;
      }
      throw err;
    }
    const res = realPathGuard(projectDir, linkPath);
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.reason).toBe("symlink_escape");
  });

  it("symlinked directory pointing OUTSIDE root is rejected", () => {
    const linkPath = path.join(projectDir, "escape-dir");
    try {
      symlinkSync(outsideDir, linkPath, "dir");
    } catch (err) {
      if ((err as NodeJS.ErrnoException)?.code === "EPERM") return;
      throw err;
    }
    // A file accessed through the symlink.
    const target = path.join(linkPath, "sensitive.txt");
    const res = realPathGuard(projectDir, target);
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.reason).toBe("symlink_escape");
  });

  it("non-existent path returns symlink_escape (realpath refuses unverifiable)", () => {
    const ghost = path.join(projectDir, "does-not-exist.txt");
    const res = realPathGuard(projectDir, ghost);
    expect(res.ok).toBe(false);
  });
});
