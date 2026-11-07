// S05 for the source-adapter variant: external services may be named in exactly one place, the adapter package
// `backend/sources/`. Everywhere else in the project the loopback-only rule of project-checks.ts holds. The recorded
// Syften and Apify answers (`seed/recorded/`) must hold at least nine items, three per platform, and must be the files the
// package ships, byte for byte, with nothing added next to them. Read-only, no browser.
import fs from "node:fs";
import path from "node:path";
import type { Checklist } from "./checklist.js";
import { REAL_FIXTURE_NAME } from "./fixture.js";
import { findExternalUse, readJson, walk } from "./project-checks.js";

export const ADAPTER_DIR = "backend/sources";
export const RECORDED_SYFTEN = "seed/recorded/syften.json";
export const RECORDED_APIFY = "seed/recorded/apify_linkedin.json";
/** The recorded answers the package ships: the reference the built project's `seed/recorded/` must equal (read from the repo, never from the build). */
export const SHIPPED_RECORDED_DIR = path.resolve(import.meta.dirname, "..", "..", "fixtures", REAL_FIXTURE_NAME, "seed", "recorded");

const DAY_MS = 86_400_000;
type Obj = Record<string, unknown>;
const text = (v: unknown): boolean => typeof v === "string" && v.trim().length > 0;
const asObj = (v: unknown): Obj => (v && typeof v === "object" ? (v as Obj) : {});
const when = (v: unknown): number => (text(v) ? Date.parse(String(v)) : NaN);

/**
 * Per-platform counts of the VALID recorded items, and how many are more than 14 days older than the newest one.
 * Syften item: `item.item_url`, `item.backend` (reddit | hackernews), a parseable `item.timestamp`, `item.title` or `item.text`.
 * Apify post: `linkedinUrl`, `content`, a parseable `postedAt.date`. An entry missing a documented field is not counted.
 */
export function findRecorded(projectPath: string): { perPlatform: Record<string, number>; total: number; old: number; missing: string[] } {
  const perPlatform: Record<string, number> = { reddit: 0, hackernews: 0, linkedin: 0 };
  const stamps: number[] = [];
  const missing: string[] = [];
  const syften = readJson(path.join(projectPath, RECORDED_SYFTEN));
  if (Array.isArray(syften) && syften.length > 0) {
    for (const x of syften) {
      const item = asObj(asObj(x).item);
      const b = String(item.backend ?? "").toLowerCase().replace(/\s+/g, "");
      const t = when(item.timestamp);
      if ((b === "reddit" || b === "hackernews") && text(item.item_url) && (text(item.title) || text(item.text)) && !Number.isNaN(t)) {
        perPlatform[b] += 1;
        stamps.push(t);
      }
    }
  } else missing.push(RECORDED_SYFTEN);
  const apify = readJson(path.join(projectPath, RECORDED_APIFY));
  if (Array.isArray(apify) && apify.length > 0) {
    for (const x of apify) {
      const o = asObj(x);
      const t = when(asObj(o.postedAt).date);
      if (text(o.linkedinUrl) && text(o.content) && !Number.isNaN(t)) {
        perPlatform.linkedin += 1;
        stamps.push(t);
      }
    }
  } else missing.push(RECORDED_APIFY);
  const newest = Math.max(...stamps, 0);
  return { perPlatform, total: stamps.length, old: stamps.filter((t) => newest - t > 14 * DAY_MS).length, missing };
}

/** Relative POSIX paths of every file under `dir` (recursive, sorted). Empty when `dir` is absent. */
function listFiles(dir: string, rel = ""): string[] {
  let entries: fs.Dirent[];
  try {
    entries = fs.readdirSync(path.join(dir, rel), { withFileTypes: true });
  } catch {
    return [];
  }
  return entries.flatMap((e) => {
    const r = rel ? `${rel}/${e.name}` : e.name;
    return e.isDirectory() ? listFiles(dir, r) : [r];
  }).sort();
}

const itemCount = (buf: Buffer): number | null => {
  try {
    const v: unknown = JSON.parse(buf.toString("utf8"));
    return Array.isArray(v) ? v.length : null;
  } catch {
    return null;
  }
};

/**
 * How the built project's `seed/recorded/` differs from the files the package ships: one entry per file, named, as
 * `missing`, `changed` (with the item counts when both are JSON lists) or `extra`. Empty = identical and nothing added.
 */
export function compareShippedRecorded(projectPath: string, shippedDir: string = SHIPPED_RECORDED_DIR): string[] {
  const built = path.join(projectPath, "seed", "recorded");
  const shipped = listFiles(shippedDir);
  if (shipped.length === 0) return [`the package ships no recorded answers at ${shippedDir}`];
  const diffs: string[] = [];
  for (const f of shipped) {
    const name = `seed/recorded/${f}`;
    const target = path.join(built, f);
    let b: Buffer;
    try {
      b = fs.readFileSync(target); // read directly: no check-then-read gap; a missing file and a folder both throw
    } catch {
      diffs.push(`${name} missing`);
      continue;
    }
    const a = fs.readFileSync(path.join(shippedDir, f));
    if (a.equals(b)) continue;
    const [na, nb] = [itemCount(a), itemCount(b)];
    const lf = (x: Buffer) => x.toString("latin1").replace(/\r\n/g, "\n");
    const lineEndingsOnly = lf(a) === lf(b);
    const how = lineEndingsOnly ? "line endings only (CRLF vs LF)" : na !== null && nb !== null && na !== nb ? `${nb} items, the package ships ${na}` : `${b.length} bytes, the package ships ${a.length}`;
    diffs.push(`${name} changed (${how})`);
  }
  for (const f of listFiles(built)) if (!shipped.includes(f)) diffs.push(`seed/recorded/${f} extra file`);
  return diffs;
}

export function checkSelfContainedWithAdapter(projectPath: string, checklist: Checklist, shippedDir: string = SHIPPED_RECORDED_DIR): void {
  // `e2e/` is the app's own Playwright suite (not shipped code): it points the browser at made-up reserved-domain URLs such as
  // www.reddit.example. Its tests and screenshots are judged by S06, not here.
  const code = walk(projectPath, (r) => /\.(py|js|mjs|cjs|ts|html|css|sh)$/.test(r) && !/^(tests|e2e|brief|seed|docs|\.shipwright|\.claude|playwright-report|test-results|coverage|htmlcov)\//.test(r));
  const inAdapter = (r: string) => r.startsWith(`${ADAPTER_DIR}/`);
  const adapter = code.filter(inAdapter);
  const outside = findExternalUse(projectPath, code.filter((r) => !inAdapter(r)), { reservedTestDomains: true });
  const hasFetchItems = adapter.some((r) => /\bdef\s+fetch_items\s*\(/.test(fs.readFileSync(path.join(projectPath, r), "utf8")));
  const rec = findRecorded(projectPath);
  const recOk = rec.missing.length === 0 && rec.total >= 9 && Object.values(rec.perPlatform).every((n) => n >= 3) && rec.old >= 2;
  const drift = compareShippedRecorded(projectPath, shippedDir);
  const evidence = [
    outside.length === 0 ? `no external use outside ${ADAPTER_DIR}/ in ${code.length - adapter.length} project code files` : `external use outside the adapter: ${outside.slice(0, 4).join("; ")}`,
    hasFetchItems ? `fetch_items found in ${adapter.length} adapter file(s)` : `no \`def fetch_items(\` in ${ADAPTER_DIR}/`,
    rec.missing.length ? `recorded answers missing: ${rec.missing.join(", ")}` : `recorded answers: ${rec.total} valid items (${Object.entries(rec.perPlatform).map(([p, n]) => `${p} ${n}`).join(", ")}), ${rec.old} more than 14 days older than the newest`,
    drift.length ? `shipped recorded answers not kept as shipped: ${drift.slice(0, 6).join(", ")}${drift.length > 6 ? `, and ${drift.length - 6} more` : ""}` : "seed/recorded/ is byte-identical to the shipped recorded answers, nothing added",
  ];
  checklist.record("S05", code.length > adapter.length && outside.length === 0 && hasFetchItems && recOk && drift.length === 0 ? "pass" : "fail", evidence.join("; "));
}
