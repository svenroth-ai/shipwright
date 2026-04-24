import { describe, it, expect, beforeEach, afterEach } from "vitest";
import {
  mkdtempSync,
  writeFileSync,
  rmSync,
  utimesSync,
  mkdirSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join, resolve } from "node:path";
import {
  loadProfile,
  clearProfileCache,
  getProfilesDir,
  findServerRoot,
} from "./profile-loader.js";

describe("profile-loader", () => {
  let dir: string;

  beforeEach(() => {
    clearProfileCache();
    dir = mkdtempSync(join(tmpdir(), "sw-profiles-"));
  });

  afterEach(() => {
    rmSync(dir, { recursive: true, force: true });
  });

  it("returns parsed profile when file exists", () => {
    const data = {
      name: "supabase-nextjs",
      description: "test",
      dev_server: { command: "npm run dev", port: 3000 },
    };
    writeFileSync(join(dir, "supabase-nextjs.json"), JSON.stringify(data));
    const got = loadProfile("supabase-nextjs", dir);
    expect(got).not.toBeNull();
    expect(got?.name).toBe("supabase-nextjs");
    expect(got?.dev_server?.command).toBe("npm run dev");
  });

  it("returns cached instance on second call (same mtime)", () => {
    writeFileSync(join(dir, "foo.json"), JSON.stringify({ name: "foo" }));
    const a = loadProfile("foo", dir);
    const b = loadProfile("foo", dir);
    expect(a).toBe(b); // identity — same cached object
  });

  it("reloads when mtime changes", () => {
    const file = join(dir, "foo.json");
    writeFileSync(file, JSON.stringify({ name: "foo", label: "v1" }));
    const first = loadProfile("foo", dir);
    expect(first?.label).toBe("v1");

    // Rewrite with a future mtime so the cache entry is invalidated.
    writeFileSync(file, JSON.stringify({ name: "foo", label: "v2" }));
    const futureMs = Date.now() + 60_000;
    utimesSync(file, futureMs / 1000, futureMs / 1000);

    const second = loadProfile("foo", dir);
    expect(second?.label).toBe("v2");
    expect(second).not.toBe(first);
  });

  it("returns null when file is missing", () => {
    expect(loadProfile("does-not-exist", dir)).toBeNull();
  });

  it("returns null for empty profile name", () => {
    expect(loadProfile("", dir)).toBeNull();
  });

  it("returns null when JSON is malformed (fail-soft)", () => {
    writeFileSync(join(dir, "broken.json"), "{not json");
    expect(loadProfile("broken", dir)).toBeNull();
  });
});

describe("getProfilesDir cascade", () => {
  const originalOverride = process.env.SHIPWRIGHT_PROFILES_DIR;
  const originalMonorepo = process.env.SHIPWRIGHT_MONOREPO_PATH;

  afterEach(() => {
    if (originalOverride === undefined) {
      delete process.env.SHIPWRIGHT_PROFILES_DIR;
    } else {
      process.env.SHIPWRIGHT_PROFILES_DIR = originalOverride;
    }
    if (originalMonorepo === undefined) {
      delete process.env.SHIPWRIGHT_MONOREPO_PATH;
    } else {
      process.env.SHIPWRIGHT_MONOREPO_PATH = originalMonorepo;
    }
  });

  it("tier 1: SHIPWRIGHT_PROFILES_DIR wins when set", () => {
    process.env.SHIPWRIGHT_PROFILES_DIR = "/custom/path";
    delete process.env.SHIPWRIGHT_MONOREPO_PATH;
    expect(getProfilesDir()).toBe("/custom/path");
  });

  it("tier 1: empty SHIPWRIGHT_PROFILES_DIR is ignored (falls through)", () => {
    process.env.SHIPWRIGHT_PROFILES_DIR = "   ";
    delete process.env.SHIPWRIGHT_MONOREPO_PATH;
    const result = getProfilesDir();
    expect(result).not.toBe("   ");
    expect(result).toMatch(/profiles$/);
  });

  it("tier 2: SHIPWRIGHT_MONOREPO_PATH resolves to shared/profiles", () => {
    delete process.env.SHIPWRIGHT_PROFILES_DIR;
    process.env.SHIPWRIGHT_MONOREPO_PATH = "/repo/shipwright";
    expect(getProfilesDir()).toBe(
      resolve("/repo/shipwright", "shared", "profiles"),
    );
  });

  it("tier 1 takes precedence over tier 2", () => {
    process.env.SHIPWRIGHT_PROFILES_DIR = "/explicit";
    process.env.SHIPWRIGHT_MONOREPO_PATH = "/monorepo";
    expect(getProfilesDir()).toBe("/explicit");
  });

  it("tier 3: falls back to bundled server/profiles when no env vars set", () => {
    delete process.env.SHIPWRIGHT_PROFILES_DIR;
    delete process.env.SHIPWRIGHT_MONOREPO_PATH;
    const result = getProfilesDir();
    // Must end in `profiles` and the parent must be the server package root.
    // We assert on the suffix rather than the absolute path because CI and
    // local checkouts have different prefixes.
    expect(result).toMatch(/server[/\\]profiles$/);
  });
});

describe("findServerRoot marker walk", () => {
  let tmpRoot: string;

  beforeEach(() => {
    tmpRoot = mkdtempSync(join(tmpdir(), "sw-server-root-"));
  });

  afterEach(() => {
    rmSync(tmpRoot, { recursive: true, force: true });
  });

  it("finds the server root from a simulated dev layout (src/core/)", () => {
    // Simulate: <tmp>/server/package.json + <tmp>/server/src/core/
    const serverDir = join(tmpRoot, "server");
    const coreDir = join(serverDir, "src", "core");
    mkdirSync(coreDir, { recursive: true });
    writeFileSync(
      join(serverDir, "package.json"),
      JSON.stringify({ name: "shipwright-command-center-server" }),
    );
    expect(findServerRoot(coreDir)).toBe(serverDir);
  });

  it("finds the server root from a simulated build layout (dist/core/)", () => {
    // Simulate: <tmp>/server/package.json + <tmp>/server/dist/core/
    const serverDir = join(tmpRoot, "server");
    const coreDir = join(serverDir, "dist", "core");
    mkdirSync(coreDir, { recursive: true });
    writeFileSync(
      join(serverDir, "package.json"),
      JSON.stringify({ name: "shipwright-command-center-server" }),
    );
    expect(findServerRoot(coreDir)).toBe(serverDir);
  });

  it("skips package.json with a different name (e.g. client)", () => {
    // A client/package.json halfway up must not match.
    const serverDir = join(tmpRoot, "server");
    const coreDir = join(serverDir, "src", "core");
    mkdirSync(coreDir, { recursive: true });
    writeFileSync(
      join(serverDir, "package.json"),
      JSON.stringify({ name: "shipwright-command-center-server-v2" }),
    );
    // A sibling package.json for the client that sits _above_ server in a
    // monorepo layout must not be picked.
    writeFileSync(
      join(tmpRoot, "package.json"),
      JSON.stringify({ name: "shipwright-command-center-client" }),
    );
    expect(findServerRoot(coreDir)).toBe(serverDir);
  });

  it("returns null when no matching package.json exists in ancestry", () => {
    const isolated = mkdtempSync(join(tmpdir(), "sw-no-marker-"));
    try {
      expect(findServerRoot(isolated)).toBeNull();
    } finally {
      rmSync(isolated, { recursive: true, force: true });
    }
  });
});
