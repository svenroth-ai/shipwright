// Starts the BUILT companion (`backend/server.py`) as a child process with a clean environment, a throw-away data folder and
// a free loopback port. The project is model-written code: it is run only with the harness's own env (no inherited keys, a
// temp HOME), fixed argv and no shell. Its output is kept so the token-secrecy check can read it.
import { execFileSync, spawn, type ChildProcess } from "node:child_process";
import net from "node:net";
import path from "node:path";
import { apiFor, get, obj, str, type Answer, type Api, type Req } from "./http.js";
import { killTree } from "../stack.js";

export async function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const s = net.createServer();
    s.once("error", reject);
    s.listen(0, "127.0.0.1", () => {
      const port = (s.address() as net.AddressInfo).port;
      s.close(() => resolve(port));
    });
  });
}

let pythonPath: string | null = null;
/** The Python the companion runs under: SHIPWRIGHT_E2E_PYTHON, else the interpreter `uv run --no-project python` resolves. */
export function resolvePython(env: NodeJS.ProcessEnv = process.env): string {
  const set = (env.SHIPWRIGHT_E2E_PYTHON ?? "").trim();
  if (set) return set;
  pythonPath ??= execFileSync("uv", ["run", "--no-project", "python", "-c", "import sys;print(sys.executable)"], { encoding: "utf8", timeout: 120_000 }).trim();
  return pythonPath;
}

const KEEP = ["PATH", "Path", "PATHEXT", "SystemRoot", "SYSTEMROOT", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL"];

/** Environment for a child of the built project: only the system basics, a temp HOME, nothing the operator exported. */
export function cleanEnv(home: string, extra: Record<string, string> = {}): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = {};
  for (const k of KEEP) if (process.env[k] !== undefined) env[k] = process.env[k];
  // Outbound traffic that is not loopback goes to a dead proxy port (fails closed), and a browser opener that does nothing is named,
  // so a lax link check in the app cannot reach the real internet or start the operator's own browser.
  const dead = "http://127.0.0.1:9";
  Object.assign(env, { HOME: home, USERPROFILE: home, PYTHONUTF8: "1", PYTHONDONTWRITEBYTECODE: "1", HTTP_PROXY: dead, HTTPS_PROXY: dead, http_proxy: dead, https_proxy: dead, ALL_PROXY: dead, NO_PROXY: "127.0.0.1,localhost", no_proxy: "127.0.0.1,localhost", BROWSER: `${process.execPath} -e 0 %s` }, extra);
  return env;
}

export interface CompanionOpts {
  project: string;
  /** Passed as `--data-dir`; null leaves the flag out (data-location checks). */
  dataDir: string | null;
  home: string;
  env?: Record<string, string>;
  port?: number;
  /** Sees every request and answer (the token-secrecy check reads them). */
  sink?: (req: Req, answer: Answer) => void;
}

export interface Companion {
  origin: string;
  port: number;
  api: Api;
  logs(): string;
  stop(): Promise<void>;
}

export async function startCompanion(o: CompanionOpts, python: string = resolvePython()): Promise<Companion> {
  const port = o.port ?? (await freePort());
  const args = [path.join(o.project, "backend", "server.py"), "--host", "127.0.0.1", "--port", String(port), ...(o.dataDir ? ["--data-dir", o.dataDir] : [])];
  const child: ChildProcess = spawn(python, args, { cwd: o.project, env: cleanEnv(o.home, o.env), stdio: ["ignore", "pipe", "pipe"], detached: process.platform !== "win32" });
  let log = "";
  const take = (c: Buffer) => { log = (log + c.toString("utf8")).slice(-1_000_000); };
  child.stdout?.on("data", take);
  child.stderr?.on("data", take);
  let exited: number | null | undefined;
  child.once("exit", (code) => { exited = code; });
  child.once("error", (e) => { exited = -1; log += `spawn failed: ${e.message}
`; });
  const origin = `http://127.0.0.1:${port}`;
  const api = apiFor(origin, o.sink);
  const stop = async () => {
    if (exited === undefined) killTree(child);
    for (let i = 0; i < 50 && exited === undefined; i += 1) await new Promise((r) => setTimeout(r, 100));
  };
  const deadline = Date.now() + 15_000;
  while (Date.now() < deadline) {
    if (exited !== undefined) throw new Error(`the companion exited with ${exited} before it answered: ${log.slice(-400)}`);
    const ok = await get(api, "/api/health").then((a) => a.status === 200 && obj(a.json).ok === true, () => false);
    if (ok) return { origin, port, api, logs: () => log, stop };
    await new Promise((r) => setTimeout(r, 200));
  }
  await stop();
  throw new Error(`the companion did not answer /api/health within 15 s: ${log.slice(-400)}`);
}

export const healthDataDir = async (api: Api): Promise<string> => str(obj((await get(api, "/api/health")).json).data_dir);
