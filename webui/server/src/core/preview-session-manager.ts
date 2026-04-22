/*
 * Preview dev-server spawn manager (iterate 3 section 03 / plan.md § 4.2).
 *
 * Contract:
 *   - spawn(projectId, profile, opts?) → {url, sessionId}
 *   - get(projectId) → cached entry if alive, else undefined
 *   - killAll() → SIGTERM every tracked PID and clear the map
 *
 * Security model:
 *   - `profile.dev_server.command` is tokenized via `shell-quote.parse`. If
 *     the parse yields any OPERATOR token (`&&`, `|`, `;`, `>`, etc.) we
 *     refuse to spawn — those are shell features and we are NOT running
 *     through a shell (`shell: false`).
 *   - child_process.spawn is invoked with `shell: false` + the pre-tokenized
 *     argv. The first token is argv0, the rest are args.
 *   - Environment is sanitized to drop any keys that start with `CLAUDE_` or
 *     `SHIPWRIGHT_` — those are webui internals and the user's dev server
 *     has no business inheriting them.
 *
 * Error codes (returned to route layer as structured class instances):
 *   - PreviewProfileInvalidError   — command field empty or contains shell operators
 *   - PreviewSpawnFailedError      — spawn threw (ENOENT, EACCES, ...)
 *   - PreviewPortInUseError        — TCP probe pre-spawn returned EADDRINUSE
 *   - PreviewExitedEarlyError      — child emitted `exit` before the ready signal
 *   - PreviewTimeoutError          — no ready signal within `ready_timeout_seconds`
 *
 * Dedup: a repeat spawn() call for a projectId with a live entry returns
 * the cached {url, sessionId} without spawning. The cache is keyed by
 * projectId + a `profileHash` — if the profile changes (new command /
 * port / ready timeout), the next spawn() re-spawns from scratch.
 *
 * Shutdown: `process.on("exit" | "SIGINT" | "SIGTERM", ...)` is wired by
 * the server entry (index.ts) calling `killAll()` in the graceful-shutdown
 * path. The manager itself does NOT install signal handlers — that's the
 * caller's job so shutdown ordering stays coherent with other subsystems.
 */

import {
  spawn as realSpawn,
  type ChildProcessWithoutNullStreams,
} from "node:child_process";
import { randomUUID, createHash } from "node:crypto";
import { createServer } from "node:net";
import { parse as shellParse } from "shell-quote";

export interface PreviewProfile {
  dev_server?: {
    command?: string;
    port?: number;
    ready_path?: string;
    ready_timeout_seconds?: number;
  };
}

export interface PreviewSpawnOptions {
  cwd: string;
  /** Injected for tests — omit to use node's real child_process.spawn. */
  spawn?: typeof realSpawn;
  /** Injected for tests — override port probe. Returns true when free. */
  probePort?: (port: number) => Promise<boolean>;
  /** Injected for tests — readiness probe. Returns true when ready. */
  probeReady?: (args: {
    port: number;
    readyPath: string;
    signal: AbortSignal;
  }) => Promise<boolean>;
  /** Injected for tests — ms clock. */
  now?: () => number;
  /** Sanitized env. Defaults to process.env minus SHIPWRIGHT_* / CLAUDE_*. */
  env?: NodeJS.ProcessEnv;
}

export interface PreviewEntry {
  projectId: string;
  pid: number;
  url: string;
  sessionId: string;
  startedAt: number;
  profileHash: string;
  /** Internal — retained so killAll() can terminate. */
  child: ChildProcessWithoutNullStreams;
}

export class PreviewProfileInvalidError extends Error {
  readonly detail: string;
  constructor(detail: string) {
    super(`Preview profile invalid: ${detail}`);
    this.name = "PreviewProfileInvalidError";
    this.detail = detail;
  }
}

export class PreviewSpawnFailedError extends Error {
  readonly detail: string;
  constructor(detail: string) {
    super(`Preview spawn failed: ${detail}`);
    this.name = "PreviewSpawnFailedError";
    this.detail = detail;
  }
}

export class PreviewPortInUseError extends Error {
  readonly port: number;
  constructor(port: number) {
    super(`Preview port ${port} is already in use`);
    this.name = "PreviewPortInUseError";
    this.port = port;
  }
}

export class PreviewExitedEarlyError extends Error {
  readonly code: number | null;
  constructor(code: number | null) {
    super(`Preview process exited early (code=${code})`);
    this.name = "PreviewExitedEarlyError";
    this.code = code;
  }
}

export class PreviewTimeoutError extends Error {
  readonly seconds: number;
  constructor(seconds: number) {
    super(`Preview ready timeout after ${seconds}s`);
    this.name = "PreviewTimeoutError";
    this.seconds = seconds;
  }
}

function hashProfile(p: PreviewProfile): string {
  const payload = JSON.stringify({
    cmd: p.dev_server?.command ?? "",
    port: p.dev_server?.port ?? 0,
    ready: p.dev_server?.ready_path ?? "/",
    timeout: p.dev_server?.ready_timeout_seconds ?? 60,
  });
  return createHash("sha1").update(payload).digest("hex").slice(0, 12);
}

function sanitizeEnv(base: NodeJS.ProcessEnv): NodeJS.ProcessEnv {
  const out: NodeJS.ProcessEnv = {};
  for (const [k, v] of Object.entries(base)) {
    if (k.startsWith("SHIPWRIGHT_")) continue;
    if (k.startsWith("CLAUDE_")) continue;
    out[k] = v;
  }
  return out;
}

async function defaultProbePort(port: number): Promise<boolean> {
  // `free` = we could create + bind a server on that port right now.
  return await new Promise((resolve) => {
    const server = createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => {
      server.close(() => resolve(true));
    });
    try {
      server.listen(port, "127.0.0.1");
    } catch {
      resolve(false);
    }
  });
}

/**
 * Defense: a malicious profile file could set ready_path to something
 * like `@evil.com/` which, when concatenated into the URL string, would
 * redirect the readiness probe off-host. We build the URL via the URL
 * constructor and assert the resolved host is 127.0.0.1 before fetching.
 */
function buildReadyUrl(port: number, readyPath: string): URL | null {
  try {
    const base = new URL(`http://127.0.0.1:${port}/`);
    // Treat readyPath as a pathname+search segment. Strip any leading
    // authority / scheme characters so a malicious string can't smuggle
    // another host through the URL constructor.
    const clean = readyPath.replace(/^[/@]+/, "/").trim() || "/";
    const url = new URL(clean, base);
    if (url.hostname !== "127.0.0.1") return null;
    if (url.port !== String(port)) return null;
    return url;
  } catch {
    return null;
  }
}

async function defaultProbeReady(args: {
  port: number;
  readyPath: string;
  signal: AbortSignal;
}): Promise<boolean> {
  const url = buildReadyUrl(args.port, args.readyPath);
  if (!url) return false;
  try {
    const res = await fetch(url.toString(), { signal: args.signal });
    // Any HTTP response at all (even 404) proves the server bound the port
    // and is routable. Vite's default index sometimes 404s on `/`.
    return res.status >= 0;
  } catch {
    return false;
  }
}

export class PreviewSessionManager {
  private entries = new Map<string, PreviewEntry>();

  /**
   * Validate + tokenize a dev command. Exposed for tests and for the
   * routes layer, which can dry-validate without mutating state.
   * Returns argv on success; throws PreviewProfileInvalidError otherwise.
   */
  static tokenizeCommand(command: string | undefined): string[] {
    if (!command || !command.trim()) {
      throw new PreviewProfileInvalidError(
        "dev_server.command is empty or missing",
      );
    }
    const parsed = shellParse(command);
    const argv: string[] = [];
    for (const tok of parsed) {
      if (typeof tok === "string") {
        argv.push(tok);
      } else {
        // Any non-string token = shell operator (`op`) or pattern glob — both
        // require a shell to interpret, which we refuse to run.
        throw new PreviewProfileInvalidError(
          "dev_server.command must be a single executable plus args, not a shell pipeline",
        );
      }
    }
    if (argv.length === 0) {
      throw new PreviewProfileInvalidError(
        "dev_server.command tokenized to zero tokens",
      );
    }
    return argv;
  }

  get(projectId: string): PreviewEntry | undefined {
    const entry = this.entries.get(projectId);
    if (!entry) return undefined;
    // Purge dead entries on lookup — killAll() normally does this, but an
    // unexpected exit outside our control should not return a stale URL.
    if (entry.child.exitCode !== null || entry.child.killed) {
      this.entries.delete(projectId);
      return undefined;
    }
    return entry;
  }

  async spawn(
    projectId: string,
    profile: PreviewProfile,
    opts: PreviewSpawnOptions,
  ): Promise<PreviewEntry> {
    const spawnFn = opts.spawn ?? realSpawn;
    const probePort = opts.probePort ?? defaultProbePort;
    const probeReady = opts.probeReady ?? defaultProbeReady;
    const now = opts.now ?? (() => Date.now());

    const profileHash = hashProfile(profile);

    // Dedup: live entry with matching profile hash → return cached.
    const cached = this.get(projectId);
    if (cached && cached.profileHash === profileHash) {
      return cached;
    }
    // Profile changed under us — kill the old child so we can respawn.
    if (cached) {
      try {
        cached.child.kill("SIGTERM");
      } catch {
        // ignore
      }
      this.entries.delete(projectId);
    }

    const argv = PreviewSessionManager.tokenizeCommand(
      profile.dev_server?.command,
    );
    const port = profile.dev_server?.port ?? 0;
    const readyPath = profile.dev_server?.ready_path ?? "/";
    const readyTimeoutSec = profile.dev_server?.ready_timeout_seconds ?? 60;

    // Port probe before spawn — a server we can't reach because another
    // process owns the port is worse than a clear error.
    if (port > 0) {
      const free = await probePort(port);
      if (!free) throw new PreviewPortInUseError(port);
    }

    let child: ChildProcessWithoutNullStreams;
    try {
      child = spawnFn(argv[0], argv.slice(1), {
        cwd: opts.cwd,
        env: opts.env ?? sanitizeEnv(process.env),
        shell: false,
        detached: false,
        stdio: "pipe",
      }) as ChildProcessWithoutNullStreams;
    } catch (err) {
      const detail =
        (err as NodeJS.ErrnoException)?.code === "ENOENT"
          ? `command not found: ${argv[0]}`
          : String(err).slice(0, 200);
      throw new PreviewSpawnFailedError(detail);
    }

    // Spawn-time error event can still fire after the constructor returned
    // (e.g. Windows sometimes reports ENOENT asynchronously). Race it
    // against the readiness / exit probes below.
    const earlyExit = new Promise<never>((_resolve, reject) => {
      child.once("error", (err) => {
        const detail =
          (err as NodeJS.ErrnoException)?.code === "ENOENT"
            ? `command not found: ${argv[0]}`
            : String(err).slice(0, 200);
        reject(new PreviewSpawnFailedError(detail));
      });
      child.once("exit", (code) => {
        reject(new PreviewExitedEarlyError(code));
      });
    });

    const readyAbort = new AbortController();
    const readinessPoll = (async (): Promise<void> => {
      const deadline = now() + readyTimeoutSec * 1000;
      while (now() < deadline) {
        if (readyAbort.signal.aborted) return;
        try {
          const ok = await probeReady({
            port,
            readyPath,
            signal: readyAbort.signal,
          });
          if (ok) return;
        } catch {
          // fall through and retry
        }
        await new Promise((r) => setTimeout(r, 500));
      }
      throw new PreviewTimeoutError(readyTimeoutSec);
    })();

    try {
      await Promise.race([readinessPoll, earlyExit]);
    } catch (err) {
      // Whatever happened, we don't want the child sitting around.
      readyAbort.abort();
      try {
        child.kill("SIGTERM");
      } catch {
        // ignore
      }
      throw err;
    }

    readyAbort.abort();

    const entry: PreviewEntry = {
      projectId,
      pid: child.pid ?? -1,
      url: `http://localhost:${port}${readyPath === "/" ? "" : readyPath}`,
      sessionId: randomUUID(),
      startedAt: now(),
      profileHash,
      child,
    };
    // Auto-purge the entry if the child exits after we've cached it.
    child.once("exit", () => {
      const current = this.entries.get(projectId);
      if (current === entry) this.entries.delete(projectId);
    });
    this.entries.set(projectId, entry);
    return entry;
  }

  killAll(): void {
    for (const entry of this.entries.values()) {
      try {
        entry.child.kill("SIGTERM");
      } catch {
        // ignore
      }
    }
    this.entries.clear();
  }

  /** Test helper — exposes the internal map size without leaking entries. */
  size(): number {
    return this.entries.size;
  }
}
