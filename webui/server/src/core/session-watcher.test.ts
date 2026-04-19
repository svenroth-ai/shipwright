import { describe, it, expect, beforeEach, afterEach } from "vitest";
import { mkdtempSync, rmSync, writeFileSync, mkdirSync } from "node:fs";
import path from "node:path";
import { tmpdir } from "node:os";

import {
  SessionWatcher,
  readWithRetry,
  computeFingerprint,
  type JsonlLocation,
} from "./session-watcher.js";

const UUID = "11111111-2222-3333-4444-555555555555";

describe("SessionWatcher.findByUuid", () => {
  let projectsDir: string;
  beforeEach(() => {
    projectsDir = mkdtempSync(path.join(tmpdir(), "sw-"));
  });
  afterEach(() => {
    try { rmSync(projectsDir, { recursive: true, force: true }); } catch { /* ignore */ }
  });

  it("finds the JSONL by filename match", async () => {
    const encoded = path.join(projectsDir, "encodedA");
    mkdirSync(encoded, { recursive: true });
    writeFileSync(path.join(encoded, `${UUID}.jsonl`), "hello\n");
    const watcher = new SessionWatcher({ projectsDir });
    const loc = await watcher.findByUuid(UUID);
    expect(loc?.path.endsWith(`${UUID}.jsonl`)).toBe(true);
    expect(loc?.encodedCwd).toBe("encodedA");
  });

  it("returns null if no file matches", async () => {
    const watcher = new SessionWatcher({ projectsDir });
    const loc = await watcher.findByUuid(UUID);
    expect(loc).toBeNull();
  });

  it("is case-insensitive on the filename match", async () => {
    // Windows filesystems are case-insensitive by default so we can't drop
    // two files that differ only in case. Verify the lookup itself uses
    // `toLowerCase()` by seeding lowercase and querying uppercase.
    const encoded = path.join(projectsDir, "enc");
    mkdirSync(encoded, { recursive: true });
    writeFileSync(path.join(encoded, `${UUID.toLowerCase()}.jsonl`), "x\n");
    const watcher = new SessionWatcher({ projectsDir });
    const loc = await watcher.findByUuid(UUID.toUpperCase());
    expect(loc).not.toBeNull();
  });
});

describe("SessionWatcher.readChunk", () => {
  let projectsDir: string;
  beforeEach(() => {
    projectsDir = mkdtempSync(path.join(tmpdir(), "sw-"));
  });
  afterEach(() => {
    try { rmSync(projectsDir, { recursive: true, force: true }); } catch { /* ignore */ }
  });

  function seed(content: string): void {
    const encoded = path.join(projectsDir, "enc");
    mkdirSync(encoded, { recursive: true });
    writeFileSync(path.join(encoded, `${UUID}.jsonl`), content);
  }

  it("returns status=missing when no JSONL yet", async () => {
    const watcher = new SessionWatcher({ projectsDir });
    const r = await watcher.readChunk({ sessionUuid: UUID, fromByte: 0, expectFingerprint: null });
    expect(r.status).toBe("missing");
  });

  it("returns chunk ending on \\n boundary", async () => {
    seed("line-a\nline-b\nline-c");
    const watcher = new SessionWatcher({ projectsDir });
    const r = await watcher.readChunk({ sessionUuid: UUID, fromByte: 0, expectFingerprint: null });
    expect(r.status).toBe("ok");
    if (r.status === "ok") {
      expect(r.chunk.content.endsWith("\n")).toBe(true);
      expect(r.chunk.content).toBe("line-a\nline-b\n");
      expect(r.chunk.toByte).toBe("line-a\nline-b\n".length);
    }
  });

  it("reads only from fromByte onwards", async () => {
    seed("line-a\nline-b\nline-c\n");
    const watcher = new SessionWatcher({ projectsDir });
    const r = await watcher.readChunk({ sessionUuid: UUID, fromByte: 7, expectFingerprint: null });
    expect(r.status).toBe("ok");
    if (r.status === "ok") {
      expect(r.chunk.content).toBe("line-b\nline-c\n");
      expect(r.chunk.fromByte).toBe(7);
    }
  });

  it("detects rotation when fingerprint mismatch + size shrank", async () => {
    seed("short\n");
    const watcher = new SessionWatcher({ projectsDir });
    const staleFp = "100:999"; // previous mtime + larger size
    const r = await watcher.readChunk({
      sessionUuid: UUID,
      fromByte: 500,
      expectFingerprint: staleFp,
    });
    expect(r.status).toBe("rotated");
  });
});

describe("readWithRetry", () => {
  it("retries on EBUSY up to the 6-attempt budget and eventually succeeds", async () => {
    let calls = 0;
    const op = async () => {
      calls++;
      if (calls < 3) throw Object.assign(new Error("busy"), { code: "EBUSY" });
      return "ok";
    };
    const value = await readWithRetry(op);
    expect(value).toBe("ok");
    expect(calls).toBe(3);
  });

  it("bails immediately on non-retryable errors", async () => {
    const op = async () => {
      throw Object.assign(new Error("bad"), { code: "NOTRETRY" });
    };
    await expect(readWithRetry(op)).rejects.toThrow("bad");
  });

  it("rethrows after exhausting retries on persistent EBUSY", async () => {
    const op = async () => {
      throw Object.assign(new Error("still busy"), { code: "EBUSY" });
    };
    await expect(readWithRetry(op)).rejects.toThrow("still busy");
  });
});

describe("computeFingerprint", () => {
  it("encodes <mtime-ms>:<size-bytes>", () => {
    const loc: JsonlLocation = {
      path: "",
      encodedCwd: "",
      mtimeMs: 1234.7,
      sizeBytes: 999,
    };
    expect(computeFingerprint(loc)).toBe("1234:999");
  });
});
