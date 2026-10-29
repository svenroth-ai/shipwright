// S05 for the source-adapter variant: external services may be named in exactly one place, the adapter package
// `backend/sources/`. Everywhere else in the project the loopback-only rule of project-checks.ts holds. The recorded
// Syften and Apify answers (`seed/recorded/`) must hold at least nine items, three per platform. Read-only, no browser.
import fs from "node:fs";
import path from "node:path";
import type { Checklist } from "./checklist.js";
import { findExternalUse, readJson, walk } from "./project-checks.js";

export const ADAPTER_DIR = "backend/sources";
export const RECORDED_SYFTEN = "seed/recorded/syften.json";
export const RECORDED_APIFY = "seed/recorded/apify_linkedin.json";

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

export function checkSelfContainedWithAdapter(projectPath: string, checklist: Checklist): void {
  const code = walk(projectPath, (r) => /\.(py|js|mjs|cjs|ts|html|css|sh)$/.test(r) && !/^(tests|brief|seed|docs|\.shipwright|\.claude|playwright-report|test-results|coverage|htmlcov)\//.test(r));
  const inAdapter = (r: string) => r.startsWith(`${ADAPTER_DIR}/`);
  const adapter = code.filter(inAdapter);
  const outside = findExternalUse(projectPath, code.filter((r) => !inAdapter(r)));
  const hasFetchItems = adapter.some((r) => /\bdef\s+fetch_items\s*\(/.test(fs.readFileSync(path.join(projectPath, r), "utf8")));
  const rec = findRecorded(projectPath);
  const recOk = rec.missing.length === 0 && rec.total >= 9 && Object.values(rec.perPlatform).every((n) => n >= 3) && rec.old >= 2;
  const evidence = [
    outside.length === 0 ? `no external use outside ${ADAPTER_DIR}/ in ${code.length - adapter.length} project code files` : `external use outside the adapter: ${outside.slice(0, 4).join("; ")}`,
    hasFetchItems ? `fetch_items found in ${adapter.length} adapter file(s)` : `no \`def fetch_items(\` in ${ADAPTER_DIR}/`,
    rec.missing.length ? `recorded answers missing: ${rec.missing.join(", ")}` : `recorded answers: ${rec.total} valid items (${Object.entries(rec.perPlatform).map(([p, n]) => `${p} ${n}`).join(", ")}), ${rec.old} more than 14 days older than the newest`,
  ];
  checklist.record("S05", code.length > adapter.length && outside.length === 0 && hasFetchItems && recOk ? "pass" : "fail", evidence.join("; "));
}
