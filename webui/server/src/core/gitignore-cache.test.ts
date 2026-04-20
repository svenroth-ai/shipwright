/*
 * gitignore-cache.test.ts — (projectRoot, mtime)-keyed cache around the
 * `ignore` package (section 04a).
 *
 * Contract:
 *   - Defaults pre-loaded: .git, node_modules, dist, build, .shipwright-webui, .webui
 *   - `.gitignore` at project root is loaded when present
 *   - Cache invalidates when .gitignore mtime changes
 *   - Cache survives repeat calls with no mtime change (parser invoked once)
 *   - Missing .gitignore is OK; defaults still apply
 */

import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  mkdtempSync,
  rmSync,
  writeFileSync,
  utimesSync,
} from "node:fs";
import path from "node:path";
import { tmpdir } from "node:os";

import {
  loadIgnore,
  __clearGitignoreCacheForTests,
  __getGitignoreCacheStatsForTests,
} from "./gitignore-cache.js";

describe("gitignore-cache — (projectRoot, mtime) cache (section 04a)", () => {
  let projectDir: string;

  beforeEach(() => {
    projectDir = mkdtempSync(path.join(tmpdir(), "gitignore-cache-test-"));
    __clearGitignoreCacheForTests();
  });

  afterEach(() => {
    try {
      rmSync(projectDir, { recursive: true, force: true });
    } catch {
      /* ignore */
    }
  });

  it("defaults: .git, node_modules, dist, build, .shipwright-webui, .webui always ignored", () => {
    const ig = loadIgnore(projectDir);
    expect(ig.ignores(".git")).toBe(true);
    expect(ig.ignores("node_modules")).toBe(true);
    expect(ig.ignores("dist")).toBe(true);
    expect(ig.ignores("build")).toBe(true);
    expect(ig.ignores(".shipwright-webui")).toBe(true);
    expect(ig.ignores(".webui")).toBe(true);
  });

  it("non-ignored files return false", () => {
    const ig = loadIgnore(projectDir);
    expect(ig.ignores("src/index.ts")).toBe(false);
    expect(ig.ignores("README.md")).toBe(false);
  });

  it("honors .gitignore entries at project root", () => {
    // Note: `secrets/` in gitignore matches files under secrets/, not the
    // dir name on its own. For directory-level matching in our tree route
    // we'll test with the trailing slash variant explicitly.
    writeFileSync(path.join(projectDir, ".gitignore"), "secrets\n*.log\n");
    const ig = loadIgnore(projectDir);
    expect(ig.ignores("secrets")).toBe(true);
    expect(ig.ignores("secrets/credentials.txt")).toBe(true);
    expect(ig.ignores("app.log")).toBe(true);
    // non-matching file
    expect(ig.ignores("app.ts")).toBe(false);
  });

  it("cache: two calls with no mtime change → parser invoked once", () => {
    writeFileSync(path.join(projectDir, ".gitignore"), "secrets/\n");
    const ig1 = loadIgnore(projectDir);
    const ig2 = loadIgnore(projectDir);
    // Same instance returned for the same cache key
    expect(ig1).toBe(ig2);
    const stats = __getGitignoreCacheStatsForTests();
    expect(stats.parses).toBe(1);
  });

  it("cache invalidation: mtime change triggers re-parse", async () => {
    const gitignorePath = path.join(projectDir, ".gitignore");
    writeFileSync(gitignorePath, "secrets\n");
    const ig1 = loadIgnore(projectDir);
    expect(ig1.ignores("secrets")).toBe(true);
    expect(ig1.ignores("cache")).toBe(false);

    // Bump mtime by at least 1 second (filesystem mtime precision on some
    // systems is seconds) — write new content AND explicitly set utimes.
    writeFileSync(gitignorePath, "cache\n");
    const future = new Date(Date.now() + 2000);
    utimesSync(gitignorePath, future, future);

    const ig2 = loadIgnore(projectDir);
    expect(ig1).not.toBe(ig2);
    expect(ig2.ignores("cache")).toBe(true);
    expect(ig2.ignores("secrets")).toBe(false);
    const stats = __getGitignoreCacheStatsForTests();
    expect(stats.parses).toBe(2);
  });

  it("missing .gitignore: defaults still apply, parser still invoked (cached after)", () => {
    // No .gitignore written
    const ig1 = loadIgnore(projectDir);
    const ig2 = loadIgnore(projectDir);
    expect(ig1).toBe(ig2);
    expect(ig1.ignores("node_modules")).toBe(true);
    expect(ig1.ignores("src/index.ts")).toBe(false);
  });

  it("different project roots: independent cache entries", () => {
    const projectB = mkdtempSync(path.join(tmpdir(), "gitignore-cache-test-b-"));
    try {
      writeFileSync(path.join(projectDir, ".gitignore"), "a-specific\n");
      writeFileSync(path.join(projectB, ".gitignore"), "b-specific\n");
      const igA = loadIgnore(projectDir);
      const igB = loadIgnore(projectB);
      expect(igA).not.toBe(igB);
      expect(igA.ignores("a-specific")).toBe(true);
      expect(igA.ignores("b-specific")).toBe(false);
      expect(igB.ignores("b-specific")).toBe(true);
      expect(igB.ignores("a-specific")).toBe(false);
    } finally {
      rmSync(projectB, { recursive: true, force: true });
    }
  });
});
