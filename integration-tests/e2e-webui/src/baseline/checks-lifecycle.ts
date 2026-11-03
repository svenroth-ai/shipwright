// B01-B05: the skill's lifecycle helper (`companion.py start|stop|status`): start, health, a second start reuses the running
// companion, stop, a port held by another program, a stale pidfile. B27: where the data folder is taken from.
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import net from "node:net";
import path from "node:path";
import { cleanEnv, freePort, startCompanion } from "./companion.js";
import { cleanDir, type Ctx } from "./ctx.js";
import { apiFor, get, obj, str } from "./http.js";
import type { Probe } from "./probe.js";
import { walk } from "../project-checks.js";

export const findHelper = (project: string): string | null => walk(project, (r) => /(^|\/)companion\.py$/.test(r) && !r.startsWith("tests/") && !r.startsWith("backend/"))[0] ?? null;

interface Ran { code: number | null; out: string; form: string }

/** Runs the helper with `--port` and `--data-dir`; a helper that rejects `--data-dir` is run again with SOCIAL_ENGAGEMENT_HOME instead. */
function helper(ctx: Ctx, rel: string, verb: string, port: number, dataDir: string, home: string): Ran {
  // stdout and stderr go to a file, not pipes: a server the helper leaves running would otherwise keep the pipes open until the timeout
  const run = (withFlag: boolean) => {
    const log = path.join(home, `helper-${Math.random().toString(16).slice(2)}.log`);
    const fd = fs.openSync(log, "w");
    let status: number | null;
    try {
      status = spawnSync(ctx.python, [path.join(ctx.project, rel), verb, "--port", String(port), ...(withFlag ? ["--data-dir", dataDir] : [])],
        { cwd: ctx.project, env: cleanEnv(home, { SOCIAL_ENGAGEMENT_HOME: dataDir }), stdio: ["ignore", fd, fd], timeout: 60_000 }).status;
    } finally {
      fs.closeSync(fd);
    }
    return { status, out: fs.readFileSync(log, "utf8") };
  };
  let r = run(true);
  let form = "--data-dir";
  if (r.status === 2 && /unrecognized|no such option|usage/i.test(r.out)) {
    r = run(false);
    form = "SOCIAL_ENGAGEMENT_HOME";
  }
  return { code: r.status, out: r.status === null ? `${r.out}
(the helper did not return within 60 s: it may run the companion in the foreground instead of starting it in the background)` : r.out, form };
}

const pidOf = (dataDir: string): number | null => {
  try {
    const text = fs.readFileSync(path.join(dataDir, "companion.pid"), "utf8");
    try {
      const pid = (JSON.parse(text) as { pid?: unknown }).pid;
      if (typeof pid === "number") return pid;
    } catch {
      // not JSON: fall through to the text forms
    }
    const m = /pid\D{0,3}(\d+)/i.exec(text) ?? /^\s*(\d+)\s*$/.exec(text);
    return m ? Number(m[1]) : null;
  } catch {
    return null;
  }
};
const alive = (pid: number): boolean => {
  try {
    process.kill(pid, 0);
    return true;
  } catch {
    return false;
  }
};
const refused = (port: number): Promise<boolean> => new Promise((resolve) => {
  const s = net.connect(port, "127.0.0.1");
  s.once("connect", () => { s.destroy(); resolve(false); });
  s.once("error", () => resolve(true));
});

/** B01-B03 run as one story on one data folder, so they share a single start; the first check to run does the work. */
export async function lifecycleStory(ctx: Ctx, p: { b01: Probe; b02: Probe; b03: Probe }): Promise<void> {
  const rel = findHelper(ctx.project);
  const { b01, b02, b03 } = p;
  if (!rel) {
    for (const x of [b01, b02, b03]) x.expect("the lifecycle helper companion.py exists", false, "no companion.py under the project");
    return;
  }
  const base = fs.mkdtempSync(path.join(ctx.tmpRoot, "life-"));
  const dataDir = path.join(base, "data");
  const home = path.join(base, "home");
  fs.mkdirSync(home, { recursive: true });
  const port = await freePort();
  const api = apiFor(`http://127.0.0.1:${port}`);
  let pid: number | null = null;
  try {
    const first = helper(ctx, rel, "start", port, dataDir, home);
    b01.note(`helper form: ${first.form}`);
    b01.expect("the first start succeeds", first.code === 0, `exit ${first.code}: ${first.out.slice(-200)}`);
    b01.expect("the start message names the board address", first.out.includes(`127.0.0.1:${port}`), first.out.slice(-160));
    const health = await get(api, "/api/health").catch(() => null);
    const h = obj(health?.json);
    b01.expect("/api/health answers 200 with ok, app, data_dir and version", health?.status === 200 && h.ok === true && h.app === "social-engagement" && path.isAbsolute(str(h.data_dir)) && str(h.version) !== "", JSON.stringify(h).slice(0, 160));
    pid = pidOf(dataDir);
    b01.expect("companion.pid names a live process", pid !== null && alive(pid), `pid ${pid}`);

    const second = helper(ctx, rel, "start", port, dataDir, home);
    b02.expect("a second start succeeds", second.code === 0, `exit ${second.code}: ${second.out.slice(-160)}`);
    b02.expect("the pidfile still names the same process", pidOf(dataDir) === pid, `${pid} then ${pidOf(dataDir)}`);
    b02.expect("the first process is still alive and healthy", pid !== null && alive(pid) && (await get(api, "/api/health").then((a) => a.status === 200, () => false)));

    b03.expect("the companion was running before stop (health answered and a pid was recorded)", pid !== null);
    const stop = helper(ctx, rel, "stop", port, dataDir, home);
    b03.expect("stop succeeds", stop.code === 0, `exit ${stop.code}: ${stop.out.slice(-160)}`);
    await new Promise((r) => setTimeout(r, 500));
    b03.expect("a connection to the port is refused afterwards", await refused(port));
    b03.expect("the pidfile is gone", !fs.existsSync(path.join(dataDir, "companion.pid")));
    b03.expect("the process is gone", pid === null || !alive(pid));
  } finally {
    helper(ctx, rel, "stop", port, dataDir, home);
    if (pid !== null && alive(pid)) { try { process.kill(pid); } catch { /* already gone */ } }
    cleanDir(base);
  }
}

/** B04: the port is held by something that is not the companion. */
export async function portInUse(ctx: Ctx, p: Probe): Promise<void> {
  const rel = findHelper(ctx.project);
  if (!rel) return void p.expect("the lifecycle helper companion.py exists", false);
  const base = fs.mkdtempSync(path.join(ctx.tmpRoot, "busy-"));
  const dataDir = path.join(base, "data");
  const home = path.join(base, "home");
  fs.mkdirSync(home, { recursive: true });
  const blocker = net.createServer((s) => s.destroy());
  await new Promise<void>((r) => blocker.listen(0, "127.0.0.1", r));
  const port = (blocker.address() as net.AddressInfo).port;
  try {
    const r = helper(ctx, rel, "start", port, dataDir, home);
    p.expect("the start does not report success", r.code !== 0, `exit ${r.code}`);
    p.expect("the message says the port is in use and names it", /in use|already|busy|taken/i.test(r.out) && r.out.includes(String(port)), r.out.slice(-200));
    p.expect("the message suggests another port", /--port/.test(r.out), r.out.slice(-200));
    p.expect("no pidfile is left", !fs.existsSync(path.join(dataDir, "companion.pid")));
  } finally {
    await new Promise((r) => blocker.close(r));
    cleanDir(base);
  }
}

/** B05: a pidfile with no live process behind it is removed and the start goes on. */
export async function stalePidfile(ctx: Ctx, p: Probe): Promise<void> {
  const rel = findHelper(ctx.project);
  if (!rel) return void p.expect("the lifecycle helper companion.py exists", false);
  const base = fs.mkdtempSync(path.join(ctx.tmpRoot, "stale-"));
  const dataDir = path.join(base, "data");
  const home = path.join(base, "home");
  fs.mkdirSync(dataDir, { recursive: true });
  fs.mkdirSync(home, { recursive: true });
  const dead = spawn(process.execPath, ["-e", ""], { stdio: "ignore" });
  await new Promise((r) => dead.once("exit", r));
  fs.writeFileSync(path.join(dataDir, "companion.pid"), String(dead.pid));
  const port = await freePort();
  const api = apiFor(`http://127.0.0.1:${port}`);
  try {
    const r = helper(ctx, rel, "start", port, dataDir, home);
    p.expect("the start succeeds although the pidfile was stale", r.code === 0, `exit ${r.code}: ${r.out.slice(-200)}`);
    p.expect("the companion answers", await get(api, "/api/health").then((a) => a.status === 200, () => false));
    const now = pidOf(dataDir);
    p.expect("the pidfile now names a different, live process", now !== null && now !== dead.pid && alive(now), `pid ${now}`);
  } finally {
    helper(ctx, rel, "stop", port, dataDir, home);
    const now = pidOf(dataDir);
    if (now !== null && alive(now)) { try { process.kill(now); } catch { /* already gone */ } }
    cleanDir(base);
  }
}

const same = (a: string, b: string) => path.resolve(a).toLowerCase() === path.resolve(b).toLowerCase();

/** B27: `--data-dir` wins over `$SOCIAL_ENGAGEMENT_HOME`, which wins over `~/.social-engagement` (a temp HOME; the real one is never touched). */
export async function dataLocation(ctx: Ctx, p: Probe): Promise<void> {
  const base = fs.mkdtempSync(path.join(ctx.tmpRoot, "loc-"));
  const [flag, env, home] = ["flag", "env", "home"].map((n) => path.join(base, n));
  fs.mkdirSync(home, { recursive: true });
  const dir = async (dataDir: string | null, extra: Record<string, string>) => {
    const c = await startCompanion({ project: ctx.project, dataDir, home, env: extra }, ctx.python);
    try {
      return str(obj((await get(c.api, "/api/health")).json).data_dir);
    } finally {
      await c.stop();
    }
  };
  try {
    p.expect("--data-dir is used even when SOCIAL_ENGAGEMENT_HOME is set", same(await dir(flag, { SOCIAL_ENGAGEMENT_HOME: env }), flag));
    p.expect("SOCIAL_ENGAGEMENT_HOME is used when there is no --data-dir", same(await dir(null, { SOCIAL_ENGAGEMENT_HOME: env }), env));
    p.expect("the default is ~/.social-engagement", same(await dir(null, {}), path.join(home, ".social-engagement")));
  } finally {
    cleanDir(base);
  }
}
