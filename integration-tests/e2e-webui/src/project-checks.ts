// Checks over the built project's files: H12 (plugin shape), H13 (no screen left as the mockup copy), S05 (no
// external service, seed size) and S06 (the Test phase ran pytest and Playwright). Read-only, no browser.
// The project is data produced by a model: it is only read, never executed, and file contents never enter the report.
import fs from "node:fs";
import path from "node:path";
import type { Checklist } from "./checklist.js";
import { PLATFORMS } from "./fixture.js";

const SKIP = new Set([".git", "node_modules", ".venv", "__pycache__", ".pytest_cache", ".dev-data"]);

function walk(root: string, accept: (rel: string) => boolean, limit = 4000): string[] {
  const out: string[] = [];
  const stack = [""];
  while (stack.length > 0 && out.length < limit) {
    const rel = stack.pop()!;
    let entries: fs.Dirent[];
    try {
      entries = fs.readdirSync(path.join(root, rel), { withFileTypes: true });
    } catch {
      continue;
    }
    for (const e of entries) {
      if (SKIP.has(e.name) || e.isSymbolicLink()) continue;
      const child = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) stack.push(child);
      else if (accept(child)) out.push(child);
    }
  }
  return out.sort();
}

const readJson = (file: string): unknown => {
  try {
    return JSON.parse(fs.readFileSync(file, "utf8"));
  } catch {
    return undefined;
  }
};

/** H12: the project is a plugin with a skill, a backend, a board and tests. */
export function checkPluginShape(projectPath: string, checklist: Checklist): void {
  const has = (rel: string) => fs.existsSync(path.join(projectPath, rel));
  const manifest = readJson(path.join(projectPath, ".claude-plugin", "plugin.json"));
  const skills = walk(path.join(projectPath, "skills"), (r) => r.endsWith("/SKILL.md"));
  const board = walk(path.join(projectPath, "board"), (r) => r.endsWith(".html"));
  const tests = walk(path.join(projectPath, "tests"), (r) => /(^|\/)test_.*\.py$/.test(r));
  const missing = [
    manifest && typeof manifest === "object" ? "" : ".claude-plugin/plugin.json (valid JSON)",
    skills.length > 0 ? "" : "skills/<name>/SKILL.md",
    has("backend/server.py") ? "" : "backend/server.py",
    board.length > 0 ? "" : "board/*.html",
    tests.length > 0 ? "" : "tests/test_*.py",
  ].filter(Boolean);
  checklist.record("H12", missing.length === 0 ? "pass" : "fail",
    missing.length === 0 ? `plugin.json, ${skills.length} skill(s), backend, ${board.length} board page(s), ${tests.length} test file(s)` : `missing: ${missing.join(", ")}`);
}

export interface ScreenVerdict {
  mockup: string;
  state: "composed" | "mockup-copy" | "missing";
}

const KIT_SIGNATURE = /Untitled UI kit|===\s*Base\s*===/;
const KIT_CLASS = /\b(btn-primary|btn-secondary|badge-(?:success|warning|error|info|neutral)|app-topnav|app-layout)\b/g;

/**
 * H13 mirrors brief-compose.md ("a screen carries the kit"): kit.css pasted inline (its header comment) or at least two
 * distinct kit component classes the plain mockups do not use, plus a token block in :root. A screen without that is
 * still the mockup copy, however it differs from the upload. A mockup that already carries the kit is itself composed.
 */
export function carriesKit(html: string): boolean {
  const classes = new Set(html.match(KIT_CLASS) ?? []);
  return /:root\s*\{/.test(html) && (KIT_SIGNATURE.test(html) || classes.size >= 2);
}

export function compareScreens(projectPath: string, mockups: string[]): ScreenVerdict[] {
  const designs = path.join(projectPath, ".shipwright", "designs");
  return mockups.map((mockup) => {
    const screen = path.join(designs, "screens", mockup);
    const upload = path.join(designs, "uploads", mockup);
    if (!fs.existsSync(screen) || !fs.existsSync(upload)) return { mockup, state: "missing" };
    return { mockup, state: carriesKit(fs.readFileSync(screen, "utf8")) ? "composed" : "mockup-copy" };
  });
}

export function checkScreensComposed(projectPath: string, mockups: string[], checklist: Checklist): void {
  const verdicts = compareScreens(projectPath, mockups);
  const bad = verdicts.filter((v) => v.state !== "composed");
  checklist.record("H13", mockups.length > 0 && bad.length === 0 ? "pass" : "fail",
    bad.length === 0 ? `${verdicts.length} screens differ from their mockups (composed)` : bad.map((v) => `${v.mockup}: ${v.state}`).join("; "));
}

const LOOPBACK = /^(127\.0\.0\.1|localhost|0\.0\.0\.0|\[::1\])$/i;
const HARMLESS_HOSTS = /^(www\.w3\.org|example\.(com|org|net)|json-schema\.org)$/i;
const KEY_READ = /(os\.environ|os\.getenv|process\.env)[^\n]{0,80}(API_?KEY|SECRET|PASSWORD|(API|ACCESS|AUTH)_?TOKEN)/i;

function hostOf(raw: string): string {
  try {
    const url = new URL(raw.replace(/^(?:href|src)=["']/i, "http:").replace(/^wss?:/i, "http:"));
    return url.hostname.includes(":") && !url.hostname.startsWith("[") ? `[${url.hostname}]` : url.hostname;
  } catch {
    return raw;
  }
}

/** External URLs and key reads in code lines (comment lines are skipped) of the given files. */
export function findExternalUse(projectPath: string, files: string[]): string[] {
  const hits: string[] = [];
  for (const rel of files) {
    const lines = fs.readFileSync(path.join(projectPath, rel), "utf8").split(/\r?\n/);
    lines.forEach((line, i) => {
      if (/^\s*(#|\/\/|\*|\/\*)/.test(line)) return;
      for (const m of line.matchAll(/(?:https?|wss?):\/\/[^\s"'`<>)]+|(?:href|src)=["']\/\/[^\s"'`<>)]+/gi)) {
        const host = hostOf(m[0]);
        if (!LOOPBACK.test(host) && !HARMLESS_HOSTS.test(host)) hits.push(`${rel}:${i + 1} reaches ${host}`);
      }
      if (KEY_READ.test(line)) hits.push(`${rel}:${i + 1} reads a key or token from the environment`);
    });
  }
  return hits;
}

/** The seed the package names (brief.md glossary): seed/matches.json, a list (or {matches: list}) of objects with a platform. No fallback to other files. */
export function findSeed(projectPath: string): { file: string; perPlatform: Record<string, number>; total: number } | null {
  const rel = "seed/matches.json";
  const data = readJson(path.join(projectPath, rel));
  const list = Array.isArray(data) ? data : Array.isArray((data as { matches?: unknown })?.matches) ? (data as { matches: unknown[] }).matches : null;
  if (!list || !list.every((x) => x && typeof x === "object" && "platform" in x)) return null;
  const perPlatform: Record<string, number> = {};
  for (const x of list as { platform: unknown }[]) perPlatform[String(x.platform)] = (perPlatform[String(x.platform)] ?? 0) + 1;
  return { file: rel, perPlatform, total: list.length };
}

const platformKey = (p: string) => p.toLowerCase().replace(/\s+/g, "");

/** S05: no external service or key in the backend and the board, and a seed of at least nine matches, three per platform. */
export function checkSelfContained(projectPath: string, checklist: Checklist): void {
  const code = walk(projectPath, (r) => /^(backend|board|skills)\/.*\.(py|js|mjs|html|css)$/.test(r));
  const external = findExternalUse(projectPath, code);
  const seed = findSeed(projectPath);
  const counts = seed ? PLATFORMS.map((p) => seed.perPlatform[platformKey(p)] ?? 0) : [];
  const seedOk = !!seed && seed.total >= 9 && counts.every((n) => n >= 3);
  const evidence = [
    external.length === 0 ? `no external use in ${code.length} backend/board/skills files` : `external use: ${external.slice(0, 4).join("; ")}`,
    seed ? `seed ${seed.file}: ${seed.total} matches (${PLATFORMS.map((p, i) => `${p} ${counts[i]}`).join(", ")})` : "no seed file found",
  ];
  checklist.record("S05", code.length > 0 && external.length === 0 && seedOk ? "pass" : "fail", evidence.join("; "));
}

/** S06: shipwright_test_results.json records both a unit (pytest) run and an e2e (Playwright) run with at least one test. */
export function checkTestsRan(projectPath: string, checklist: Checklist): void {
  const data = readJson(path.join(projectPath, "shipwright_test_results.json")) as Record<string, { passed?: number; total?: number; failed?: number; skipped?: number } | undefined> | undefined;
  const count = (k: string) => ({ passed: Number(data?.[k]?.passed ?? 0), total: Number(data?.[k]?.total ?? 0), failed: Number(data?.[k]?.failed ?? 0), skipped: Number(data?.[k]?.skipped ?? 0) });
  const unit = count("unit");
  const e2e = count("e2e");
  const ran = (c: { total: number }) => c.total > 0;
  checklist.record("S06", ran(unit) && ran(e2e) && unit.passed + unit.skipped === unit.total && e2e.passed + e2e.skipped === e2e.total && unit.failed === 0 && e2e.failed === 0 ? "pass" : "fail",
    data ? `unit (pytest) ${unit.passed}/${unit.total}; e2e (Playwright) ${e2e.passed}/${e2e.total}` : "shipwright_test_results.json is missing or unreadable");
}
