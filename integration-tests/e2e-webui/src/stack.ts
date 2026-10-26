// Own stack starter, modelled on the WebUI's client/e2e/isolated-stack.mjs: build the server and client,
// then start the server (which also serves the built client) with HOME/USERPROFILE pointing at the temp
// HOME. Every child process uses a fixed argv array (no shell string, no env-built command line).
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";

export interface Stack {
  baseUrl: string;
  home: string;
  /** How long the three build steps took (reported on their own, apart from the agent run). */
  buildMs: number;
  stop(): Promise<void>;
  /** Synchronous kill, for the shutdown path that runs from signal and exit handlers. */
  killSync(): void;
}

/** Each build step gets its own limit so a hung build is reported as a build problem, not as an idle agent. */
export const BUILD_STEP_TIMEOUT_MS = 20 * 60_000;

/** Kills the child AND its whole process tree (fixed argv, no shell). Never throws; the tree may already be gone. */
export function killTree(child: ChildProcess): void {
  const pid = child.pid;
  if (pid === undefined || child.exitCode !== null) return;
  try {
    if (process.platform === "win32") execFileSync("taskkill", ["/PID", String(pid), "/T", "/F"], { stdio: "ignore", timeout: 30_000 });
    else process.kill(-pid, "SIGKILL");
  } catch {
    try {
      child.kill("SIGKILL");
    } catch {
      // already gone
    }
  }
}

/** Build steps count against the overall deadline: a step may use at most the time that is left. */
function runNode(args: string[], cwd: string, label: string, deadline: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const limit = Math.min(BUILD_STEP_TIMEOUT_MS, deadline - Date.now());
    if (limit <= 0) return reject(new Error(`${label} not started: the overall time budget is used up`));
    const child = spawn(process.execPath, args, { cwd, stdio: "inherit", detached: process.platform !== "win32" });
    const timer = setTimeout(() => {
      killTree(child);
      reject(new Error(`${label} timed out after ${Math.round(limit / 60_000)} minutes (step limit or overall budget)`));
    }, limit);
    child.once("error", (e) => { clearTimeout(timer); reject(e); });
    child.once("exit", (code) => {
      clearTimeout(timer);
      if (code === 0) resolve();
      else reject(new Error(`${label} failed (exit ${code})`));
    });
  });
}

const ENV_ALLOW = new Set([
  "PATH", "Path", "PATHEXT", "SystemRoot", "SYSTEMROOT", "SystemDrive", "windir", "ComSpec", "ProgramData", "ProgramFiles",
  "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL", "TERM", "PLAYWRIGHT_BROWSERS_PATH", "USERNAME",
  "NODE_OPTIONS", "NODE_EXTRA_CA_CERTS", "NODE_PATH", "NODE_ENV", "SSL_CERT_FILE", "CLAUDE_CODE_GIT_BASH_PATH",
  "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "http_proxy", "https_proxy", "no_proxy",
]);

/**
 * Environment for the WebUI server (and so the agent). An allowlist, not the operator's whole environment:
 * the basics a process needs (an explicit NODE_* subset, never NODE_AUTH_TOKEN), proxy/CA settings, the values the starter itself exports in `extra` (which carries only the
 * chosen auth variable and the SHIPWRIGHT_* settings), and every home-like location pointed at the temp HOME.
 */
export function childEnv(base: NodeJS.ProcessEnv, home: string, extra: Record<string, string>): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {};
  for (const [key, value] of Object.entries(base)) {
    if (value !== undefined && ENV_ALLOW.has(key)) env[key] = value;
  }
  Object.assign(env, extra, { HOME: home, USERPROFILE: home });
  env.APPDATA = path.join(home, "AppData", "Roaming");
  env.LOCALAPPDATA = path.join(home, "AppData", "Local");
  return env;
}

async function freePort(): Promise<number> {
  return await new Promise((resolve, reject) => {
    const probe = net.createServer();
    probe.once("error", reject);
    probe.listen(0, "127.0.0.1", () => {
      const address = probe.address() as net.AddressInfo;
      probe.close((error) => (error ? reject(error) : resolve(address.port)));
    });
  });
}

async function waitFor(url: string, child: ChildProcess, deadline: number, seconds = 60): Promise<void> {
  for (let i = 0; i < seconds * 2 && Date.now() < deadline; i += 1) {
    if (child.exitCode !== null) throw new Error(`WebUI server exited before it was ready (exit ${child.exitCode})`);
    try {
      if ((await fetch(url, { signal: AbortSignal.timeout(5000) })).ok) return;
    } catch {
      // not listening yet
    }
    await new Promise((r) => setTimeout(r, 500));
  }
  throw new Error(`Timed out waiting for the WebUI at ${url}`);
}

export function checkWebuiDir(webuiDir: string): string[] {
  const needs = [
    "server/node_modules/typescript/bin/tsc",
    "server/scripts/copy-assets.mjs",
    "client/node_modules/vite/bin/vite.js",
  ];
  return needs.filter((n) => !fs.existsSync(path.join(webuiDir, n)));
}

export interface StartInput {
  webuiDir: string;
  repoRoot: string;
  home: string;
  /** Extra env for the server (and so the agent): the fixture acceptance flag. */
  extraEnv: Record<string, string>;
  /** Epoch ms of the overall deadline; build steps and the readiness wait count against it. */
  deadline: number;
}

export async function startStack(input: StartInput): Promise<Stack> {
  const { webuiDir, repoRoot, home } = input;
  const missing = checkWebuiDir(webuiDir);
  if (missing.length > 0) {
    throw new Error(`The WebUI checkout is not ready (run npm ci in its server/ and client/): missing ${missing.join(", ")}`);
  }
  const serverDir = path.join(webuiDir, "server");
  const clientDir = path.join(webuiDir, "client");
  // Build under the operator's normal environment; only the running server gets the temp HOME.
  const buildStarted = Date.now();
  await runNode(["node_modules/typescript/bin/tsc", "-p", "tsconfig.json"], serverDir, "WebUI server build", input.deadline);
  await runNode(["scripts/copy-assets.mjs"], serverDir, "WebUI asset copy", input.deadline);
  await runNode(["node_modules/vite/bin/vite.js", "build"], clientDir, "WebUI client build", input.deadline);

  const buildMs = Date.now() - buildStarted;
  fs.mkdirSync(path.join(home, "AppData", "Roaming"), { recursive: true });
  fs.mkdirSync(path.join(home, "AppData", "Local"), { recursive: true });
  const port = await freePort();
  const server = spawn(process.execPath, ["dist/index.js"], {
    cwd: serverDir,
    stdio: "ignore",
    detached: process.platform !== "win32", // own process group, so the whole tree can be killed
    env: childEnv(process.env, home, {
      ...input.extraEnv,
      PORT: String(port),
      SHIPWRIGHT_MONOREPO_PATH: repoRoot,
      SHIPWRIGHT_NETWORK_PROFILE: "local",
    }),
  });
  const killSync = () => killTree(server);
  const baseUrl = `http://127.0.0.1:${port}`;
  const stop = async () => {
    const done = new Promise<void>((r) => (server.exitCode !== null ? r() : server.once("exit", () => r())));
    killTree(server);
    await Promise.race([done, new Promise((r) => setTimeout(r, 15_000))]);
  };
  try {
    await waitFor(`${baseUrl}/api/projects`, server, input.deadline);
  } catch (error) {
    await stop();
    throw error;
  }
  return { baseUrl, home, buildMs, stop, killSync };
}
