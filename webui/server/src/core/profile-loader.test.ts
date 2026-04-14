import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, writeFileSync, rmSync, utimesSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { loadProfile, clearProfileCache } from "./profile-loader.js";

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
