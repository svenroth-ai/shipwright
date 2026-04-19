/*
 * Session JSONL discovery + stateless byte-range reader.
 *
 * Variant-a narrow: NO chokidar, NO recursive watchers. Discovery is
 * filename-first per PoC finding 1 — claude writes each session at
 * `~/.claude/projects/<encoded-cwd>/<uuid>.jsonl`, and the filename is
 * the authoritative primitive (first-line sessionId verification is a
 * sanity check only; fork-session files begin with `file-history-snapshot`
 * lines that carry no sessionId).
 *
 * The transcript endpoint reads byte-ranges stateless: the client supplies
 * `fromByte` + `expectFingerprint`; the server returns the delta. No
 * server-side offset cache → multi-tab works by construction.
 *
 * Torn-read retry: 50 → 1600 ms × 6 attempts, catching EBUSY / EPERM /
 * EACCES / ENOENT in addition to JSON-parse errors. Plan D'' round-1
 * BLOCKER fix + Gemini BLOCKER. PoC finding 4 showed torn-reads don't fire
 * on NTFS at the write rates claude emits, but the wider retry envelope
 * remains as insurance against AV scanners / OneDrive sync / Defender.
 */

import { readFile, readdir, stat } from "node:fs/promises";
import { homedir } from "node:os";
import path from "node:path";

export const PROJECTS_DIR = path.join(homedir(), ".claude", "projects");

export interface JsonlLocation {
  path: string;
  encodedCwd: string;
  mtimeMs: number;
  sizeBytes: number;
}

export interface SessionWatcherDeps {
  readdir?: (p: string) => Promise<string[]>;
  stat?: (p: string) => Promise<{ mtimeMs: number; size: number; isDirectory: () => boolean }>;
  readFile?: (p: string) => Promise<Buffer>;
  /** Override for tests; defaults to `~/.claude/projects`. */
  projectsDir?: string;
}

const DEFAULT_DEPS: Required<SessionWatcherDeps> = {
  readdir: (p) => readdir(p),
  stat: (p) =>
    stat(p).then((s) => ({
      mtimeMs: s.mtimeMs,
      size: s.size,
      isDirectory: () => s.isDirectory(),
    })),
  readFile: (p) => readFile(p),
  projectsDir: PROJECTS_DIR,
};

export class SessionWatcher {
  private readonly deps: Required<SessionWatcherDeps>;

  constructor(deps: SessionWatcherDeps = {}) {
    this.deps = { ...DEFAULT_DEPS, ...deps };
  }

  /**
   * Resolve the on-disk JSONL for a given pre-bound session UUID.
   * Returns null if no file matches yet (common during
   * `awaiting_external_start` before the user pastes).
   */
  async findByUuid(sessionUuid: string): Promise<JsonlLocation | null> {
    const wanted = `${sessionUuid.toLowerCase()}.jsonl`;
    let subs: string[];
    try {
      subs = await this.deps.readdir(this.deps.projectsDir);
    } catch {
      return null;
    }
    for (const sub of subs) {
      const subPath = path.join(this.deps.projectsDir, sub);
      try {
        const s = await this.deps.stat(subPath);
        if (!s.isDirectory()) continue;
      } catch {
        continue;
      }
      let files: string[];
      try {
        files = await this.deps.readdir(subPath);
      } catch {
        continue;
      }
      for (const f of files) {
        if (f.toLowerCase() !== wanted) continue;
        const fp = path.join(subPath, f);
        try {
          const fs = await this.deps.stat(fp);
          return { path: fp, encodedCwd: sub, mtimeMs: fs.mtimeMs, sizeBytes: fs.size };
        } catch {
          return null;
        }
      }
    }
    return null;
  }

  /**
   * Read a byte-range from the JSONL with torn-read retry + UTF-8 safe
   * chunk trimming. Always returns content ending on `\n` so the client
   * never sees a partial line (and `\n` is safe to split on even in the
   * middle of a multi-byte UTF-8 sequence).
   */
  async readChunk(args: {
    sessionUuid: string;
    fromByte: number;
    expectFingerprint: string | null;
  }): Promise<TranscriptReadResult> {
    const loc = await this.findByUuid(args.sessionUuid);
    if (!loc) return { status: "missing" };
    const fingerprint = computeFingerprint(loc);

    if (args.expectFingerprint && args.expectFingerprint !== fingerprint) {
      const [, prevSizeStr] = args.expectFingerprint.split(":");
      const prevSize = Number.parseInt(prevSizeStr ?? "0", 10);
      if (loc.sizeBytes < args.fromByte || loc.sizeBytes < prevSize) {
        return { status: "rotated", currentFingerprint: fingerprint };
      }
    }

    const bytes = await readWithRetry(() => this.deps.readFile(loc.path));
    const from = Math.min(Math.max(args.fromByte, 0), bytes.length);
    let slice = bytes.subarray(from);
    let endExclusive = from + slice.length;
    const lastNl = lastIndexOf(slice, 0x0a);
    if (lastNl === -1) {
      slice = Buffer.alloc(0);
      endExclusive = from;
    } else {
      slice = slice.subarray(0, lastNl + 1);
      endExclusive = from + lastNl + 1;
    }

    return {
      status: "ok",
      chunk: {
        fingerprint,
        size: loc.sizeBytes,
        fromByte: from,
        toByte: endExclusive,
        content: slice.toString("utf-8"),
      },
    };
  }
}

// ---------- helpers ----------

export interface TranscriptChunk {
  fingerprint: string;
  size: number;
  fromByte: number;
  toByte: number;
  content: string;
}

export type TranscriptReadResult =
  | { status: "missing" }
  | { status: "rotated"; currentFingerprint: string }
  | { status: "ok"; chunk: TranscriptChunk };

export function computeFingerprint(loc: JsonlLocation): string {
  return `${Math.trunc(loc.mtimeMs)}:${loc.sizeBytes}`;
}

const RETRY_DELAYS_MS = [50, 100, 200, 400, 800, 1600];
const RETRY_ERROR_CODES = new Set(["EBUSY", "EPERM", "EACCES", "ENOENT"]);

/** 6-attempt exponential backoff covering Windows filesystem errors. */
export async function readWithRetry<T>(op: () => Promise<T>): Promise<T> {
  let lastErr: unknown;
  for (let i = 0; i < RETRY_DELAYS_MS.length; i++) {
    try {
      return await op();
    } catch (err) {
      lastErr = err;
      const code = (err as NodeJS.ErrnoException)?.code;
      if (!code || !RETRY_ERROR_CODES.has(code)) {
        // Non-retryable error (permissions, syntax, etc.) — bail immediately.
        throw err;
      }
      if (i === RETRY_DELAYS_MS.length - 1) break;
      await new Promise((r) => setTimeout(r, RETRY_DELAYS_MS[i]));
    }
  }
  throw lastErr;
}

function lastIndexOf(buf: Buffer, byte: number): number {
  for (let i = buf.length - 1; i >= 0; i--) {
    if (buf[i] === byte) return i;
  }
  return -1;
}
