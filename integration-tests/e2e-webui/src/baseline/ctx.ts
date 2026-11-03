// Shared context of the baseline checks: where the built project and the package are, the synthetic tokens, the fake
// services, and `scenario()`, which runs a block against a fresh companion and a fresh data folder.
import crypto from "node:crypto";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { startCompanion, type Companion } from "./companion.js";
import type { Fake } from "./fake-services.js";
import { arr, obj, type Api, type Obj } from "./http.js";

export const TODAY = "2026-11-03";

export interface Ctx {
  project: string;
  fixtureDir: string;
  python: string;
  tmpRoot: string;
  fake: Fake;
  /** Dummy token values made up for this run; they exist nowhere else. */
  tokens: { syften: string; apify: string };
  /** Everything the companion said or wrote that the secrecy check must read: answers, logs, data files. */
  leaks: { where: string; text: string }[];
  /** The 11 items the stand-in agent stores (seed/agent/run-synthetic.json). */
  synthetic: Obj[];
}

export function loadSynthetic(fixtureDir: string): Obj[] {
  const file = JSON.parse(fs.readFileSync(path.join(fixtureDir, "seed", "agent", "run-synthetic.json"), "utf8")) as unknown;
  return arr(obj(file).items).map(obj);
}

export const dummyTokens = () => ({ syften: `E2E-DUMMY-SYFTEN-${crypto.randomBytes(8).toString("hex")}`, apify: `E2E-DUMMY-APIFY-${crypto.randomBytes(8).toString("hex")}` });

export interface ScenarioOpts {
  /** Extra environment of the companion; `fakeUrls` adds the three base-URL variables, `tokens` the two token variables. */
  env?: Record<string, string>;
  fakeUrls?: boolean;
  tokens?: "both" | "none";
  today?: boolean;
  /** Write `.env.local` into the data folder before the start (token source test). */
  envLocal?: string;
}

export interface Scenario {
  c: Companion;
  api: Api;
  dataDir: string;
  home: string;
  /** Stops the companion and starts it again on the same data folder and port. */
  restart(): Promise<void>;
}

/** Fresh data folder + companion for `fn`; always stopped afterwards, its log and data files are handed to the secrecy check. */
export async function scenario<T>(ctx: Ctx, name: string, opts: ScenarioOpts, fn: (s: Scenario) => Promise<T>): Promise<T> {
  const base = fs.mkdtempSync(path.join(ctx.tmpRoot, `${name}-`));
  const dataDir = path.join(base, "data");
  const home = path.join(base, "home");
  fs.mkdirSync(home, { recursive: true });
  if (opts.envLocal !== undefined) {
    fs.mkdirSync(dataDir, { recursive: true });
    fs.writeFileSync(path.join(dataDir, ".env.local"), opts.envLocal);
  }
  const env: Record<string, string> = { ...(opts.env ?? {}) };
  if (opts.fakeUrls) Object.assign(env, ctx.fake.env);
  if (opts.tokens === "both") Object.assign(env, { SYFTEN_TOKEN: ctx.tokens.syften, APIFY_TOKEN: ctx.tokens.apify });
  if (opts.today) env.SOCIAL_ENGAGEMENT_TODAY = TODAY;
  const start = (port?: number) => startCompanion({ project: ctx.project, dataDir, home, env, port, sink: (req, a) => ctx.leaks.push({ where: `${name}: answer to ${req.method ?? "GET"} ${req.path}`, text: a.text }) }, ctx.python);
  let c = await start();
  const s: Scenario = {
    get c() { return c; },
    get api() { return c.api; },
    dataDir, home,
    async restart() { const port = c.port; await c.stop(); c = await start(port); },
  };
  try {
    return await fn(s);
  } finally {
    await c.stop();
    ctx.leaks.push({ where: `${name}: companion output`, text: c.logs() });
    collectFiles(dataDir, (rel, text) => ctx.leaks.push({ where: `${name}: data file ${rel}`, text }));
    cleanDir(base);
  }
}

/** Calls `visit` with the relative path and text of every file under `dir` (recursive, size-capped). */
export function collectFiles(dir: string, visit: (rel: string, text: string) => void, rel = ""): void {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(path.join(dir, rel), { withFileTypes: true });
  } catch {
    return;
  }
  for (const e of entries) {
    const r = rel ? `${rel}/${e.name}` : e.name;
    if (e.isDirectory()) collectFiles(dir, visit, r);
    else if (e.isFile()) visit(r, fs.readFileSync(path.join(dir, r), "utf8").slice(0, 2_000_000));
  }
}

export const tmpRootFor = (): string => fs.mkdtempSync(path.join(os.tmpdir(), "e2e-baseline-"));

/** Removes a temp folder; on Windows a just-killed process may still hold it, so retry and never let cleanup decide a verdict. */
export function cleanDir(dir: string): void {
  try {
    fs.rmSync(dir, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
  } catch {
    // a leftover temp folder is harmless; the OS temp cleaner removes it
  }
}
