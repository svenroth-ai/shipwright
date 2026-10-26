// Own stack starter, modelled on the WebUI's client/e2e/isolated-stack.mjs: build the server and client,
// then start the server (which also serves the built client) with HOME/USERPROFILE pointing at the temp
// HOME. Every child process uses a fixed argv array (no shell string, no env-built command line).
import { spawn, type ChildProcess } from "node:child_process";
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

function runNode(args: string[], cwd: string, label: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn(process.execPath, args, { cwd, stdio: "inherit" });
    const timer = setTimeout(() => {
      child.kill();
      reject(new Error(`${label} timed out after ${BUILD_STEP_TIMEOUT_MS / 60_000} minutes`));
    }, BUILD_STEP_TIMEOUT_MS);
    child.once("error", (e) => { clearTimeout(timer); reject(e); });
    child.once("exit", (code) => {
      clearTimeout(timer);
      if (code === 0) resolve();
      else reject(new Error(`${label} failed (exit ${code})`));
    });
  });
}

/**
 * Environment for the WebUI server (and so the agent): the operator's environment (PATH, auth variables)
 * with every home-like location pointed at the temp HOME, so nothing resolves to the real one.
 */
export function childEnv(base: NodeJS.ProcessEnv, home: string, extra: Record<string, string>): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...base, ...extra, HOME: home, USERPROFILE: home };
  delete env.CLAUDE_CONFIG_DIR;
  delete env.XDG_CONFIG_HOME;
  delete env.XDG_DATA_HOME;
  delete env.XDG_CACHE_HOME;
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

async function waitFor(url: string, child: ChildProcess, seconds = 60): Promise<void> {
  for (let i = 0; i < seconds * 2; i += 1) {
    if (child.exitCode !== null) throw new Error(`WebUI server exited before it was ready (exit ${child.exitCode})`);
    try {
      if ((await fetch(url)).ok) return;
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
  await runNode(["node_modules/typescript/bin/tsc", "-p", "tsconfig.json"], serverDir, "WebUI server build");
  await runNode(["scripts/copy-assets.mjs"], serverDir, "WebUI asset copy");
  await runNode(["node_modules/vite/bin/vite.js", "build"], clientDir, "WebUI client build");

  const buildMs = Date.now() - buildStarted;
  fs.mkdirSync(path.join(home, "AppData", "Roaming"), { recursive: true });
  fs.mkdirSync(path.join(home, "AppData", "Local"), { recursive: true });
  const port = await freePort();
  const server = spawn(process.execPath, ["dist/index.js"], {
    cwd: serverDir,
    stdio: "ignore",
    env: childEnv(process.env, home, {
      ...input.extraEnv,
      PORT: String(port),
      SHIPWRIGHT_MONOREPO_PATH: repoRoot,
      SHIPWRIGHT_NETWORK_PROFILE: "local",
    }),
  });
  const killSync = () => {
    if (server.exitCode === null) server.kill();
  };
  const baseUrl = `http://127.0.0.1:${port}`;
  const stop = async () => {
    if (server.exitCode !== null) return;
    const done = new Promise<void>((r) => server.once("exit", () => r()));
    server.kill();
    await Promise.race([done, new Promise((r) => setTimeout(r, 5000))]);
  };
  try {
    await waitFor(`${baseUrl}/api/projects`, server);
  } catch (error) {
    await stop();
    throw error;
  }
  return { baseUrl, home, buildMs, stop, killSync };
}
