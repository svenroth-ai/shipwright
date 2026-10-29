// The board checks S01 and S02 for the master-detail variant (a platform switcher, a status filter, a thread list and one
// thread beside it), over a snapshot of the served page. The browser part is one evaluate call plus two row clicks; the
// verdicts are pure functions over the snapshot, so unit tests need no browser. S04 reuses board-dom.ts (tokens + fonts).
import type { Page } from "@playwright/test";
import type { Checklist } from "./checklist.js";
import { PLATFORMS, REAL_STATUSES } from "./fixture.js";
import type { BoardSnapshot } from "./board-dom.js";
import type { RealThreadState } from "./board-api-real.js";

export interface MasterDetailSnapshot extends BoardSnapshot {
  /** Visible switcher entries (role=tab, else buttons named like a platform), each with its text. */
  switcher: string[];
  /** Option texts (lower case) of every status filter: select options, or buttons/items inside an element named status or filter. */
  filterOptions: string[];
  /** After opening a row: its title is visible more than once (list row + thread), i.e. the list stayed beside the thread. */
  listBesideThread: boolean;
  /** A "Copy reply" button is visible with a drafted thread open. */
  copyReply: boolean;
  /** An entry called Keywords in the switcher or as a tab: the keywords belong to the sources, not to a board tab. */
  keywordsTab: boolean;
}

function script(tokenNames: string[]): string {
  return `(async () => {
  const text = (e) => (e.textContent || '').trim().replace(/\\s+/g, ' ');
  const visible = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const platforms = ${JSON.stringify(PLATFORMS)};
  const isPlat = (e) => platforms.some((p) => text(e).toLowerCase().startsWith(p.toLowerCase()));
  const switcherEls = () => { const r = [...document.querySelectorAll('[role="tab"]')].filter(isPlat); return r.length > 0 ? r : [...document.querySelectorAll('button, a, [role="button"]')].filter((e) => visible(e) && isPlat(e)); };
  const names = switcherEls().map(text);
  const badgesByTab = {};
  for (let i = 0; i < names.length; i += 1) { const t = switcherEls()[i]; if (t) t.click(); await new Promise((r) => setTimeout(r, 500)); badgesByTab[names[i]] = [...document.querySelectorAll('[class*="badge"]')].filter(visible).map((e) => text(e).toLowerCase()); }
  const optionRe = /^(all( statuses)?|new|drafted|posted|skipped|expired)(\\s*\\(?\\d+\\)?)?$/;
  const opts = [];
  for (const s of document.querySelectorAll('select')) for (const o of s.options) opts.push(text(o).toLowerCase());
  const inPlatform = (e) => isPlat(e) || !!e.closest('[role="tablist"]');
  for (const g of document.querySelectorAll('[class*="filter"], [id*="filter"], [class*="status"], [id*="status"], [aria-label*="tatus" i], [aria-label*="ilter" i]')) for (const o of g.querySelectorAll('button, li, [role="option"], [role="menuitem"], option, label')) { const t = text(o).toLowerCase(); if (optionRe.test(t) && !inPlatform(o)) opts.push(t); }
  const everyTab = [...document.querySelectorAll('[role="tab"], nav a, nav button')].map(text);
  const keywordsTab = [...everyTab, ...names].some((n) => /^keywords?\\b/i.test(n));
  const inputRe = /chat|composer|type a (message|command)|send a message/i;
  const panelRe = /chat|composer|message-log|msg-log/i;
  const chatInputs = [...document.querySelectorAll('input, textarea')].filter((e) => e.type !== 'hidden' && inputRe.test([e.placeholder, e.getAttribute('aria-label'), e.name, e.id].join(' '))).map((e) => e.outerHTML.slice(0, 120));
  const chatPanels = [...document.querySelectorAll('[class], [id], [aria-label]')].filter((e) => panelRe.test([e.className && e.className.baseVal === undefined ? e.className : '', e.id, e.getAttribute('aria-label')].join(' ')) && !['INPUT','TEXTAREA','SCRIPT','STYLE'].includes(e.tagName) && visible(e)).map((e) => e.tagName.toLowerCase() + ' ' + String(e.className || e.id || e.getAttribute('aria-label')).slice(0, 60));
  const cs = getComputedStyle(document.documentElement);
  const tokens = {};
  for (const n of ${JSON.stringify(tokenNames)}) tokens[n] = cs.getPropertyValue(n).trim();
  return { tabs: names, switcher: names, badgesByTab, filterOptions: opts, chatInputs, chatPanels, tokens, keywordsTab };
})()`;
}

/** Switches to the thread's platform and opens its row; returns whether the title is then visible more than once (list + thread). */
async function openRow(page: Page, platformLabel: string, title: string): Promise<boolean> {
  const name = new RegExp(`^${platformLabel}`, "i");
  const roled = page.getByRole("tab", { name }).first();
  const entry = (await roled.count()) ? roled : page.locator("button, a, [role=button]").filter({ hasText: name }).first();
  if (await entry.count()) await entry.click({ timeout: 5000 }).catch(() => undefined);
  await page.waitForTimeout(400);
  // A list may cut a long title: match on its first words.
  const head = title.slice(0, 30);
  await page.getByText(head, { exact: false }).first().click({ timeout: 8000 });
  await page.waitForTimeout(600);
  return (await page.getByText(head, { exact: false }).filter({ visible: true }).count()) > 1;
}

const LABEL: Record<string, string> = { reddit: "Reddit", hackernews: "Hacker News", linkedin: "LinkedIn" };

export async function snapshotMasterDetail(page: Page, tokenNames: string[], state: RealThreadState): Promise<MasterDetailSnapshot> {
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => undefined);
  await page.waitForSelector('[role="tab"], button', { timeout: 10_000 }).catch(() => undefined);
  const snap = (await page.evaluate(script(tokenNames))) as MasterDetailSnapshot;
  const open = async (id: number | null) => (id === null ? false : openRow(page, LABEL[state.platformOf[id]] ?? "Reddit", state.titles[id] ?? "").catch(() => false));
  snap.listBesideThread = await open(state.fresh);
  await open(state.drafted);
  snap.copyReply = (await page.getByRole("button", { name: /copy reply/i }).filter({ visible: true }).count()) > 0;
  return snap;
}

const key = (name: string) => name.toLowerCase().replace(/\s*\(?\d+\)?$/, "").replace(/\s+/g, "");

/** S01: the board is the whole page. S02 (variant): switcher with counts, status filter, badge per list row, thread beside the list, Copy reply, no Keywords tab. */
export function checkMasterDetailShape(snap: MasterDetailSnapshot, checklist: Checklist, perPlatform: Record<string, number> = {}): void {
  const chat = [...snap.chatInputs, ...snap.chatPanels];
  checklist.record("S01", chat.length === 0 && snap.switcher.length > 0 ? "pass" : "fail",
    chat.length === 0 ? `no chat input or panel found; ${snap.switcher.length} switcher entries` : `chat-like elements: ${chat.slice(0, 3).join(" | ")}`);

  const entriesOk = snap.switcher.length === PLATFORMS.length && PLATFORMS.every((p) => snap.switcher.some((t) => t.toLowerCase().startsWith(p.toLowerCase())));
  // A count per entry (digits in the label); it may not exceed the threads the API lists for that platform (a filter may hide some).
  const counts = snap.switcher.map((t) => [key(t), /(\d+)\s*$/.exec(t.trim())?.[1]] as const);
  const uncounted = counts.filter(([, n]) => n === undefined).map(([k]) => k);
  // The filter starts at "all" (brief.md), so a count may not exceed the API's and may not read 0 where the API lists threads.
  const overcounted = counts.filter(([k, n]) => n !== undefined && k in perPlatform && (Number(n) > perPlatform[k] || (Number(n) === 0 && perPlatform[k] > 0))).map(([k]) => k);
  const filterMissing = REAL_STATUSES.filter((s) => !snap.filterOptions.some((o) => o.includes(s)));
  const perTab = Object.entries(snap.badgesByTab).map(([n, b]) => [n, b.filter((x) => (REAL_STATUSES as readonly string[]).includes(x))] as [string, string[]]);
  const empty = perTab.filter(([, b]) => b.length === 0).map(([n]) => n);
  const short = perTab.filter(([n, b]) => b.length < (perPlatform[key(n)] ?? 0)).map(([n]) => n);
  const seen = REAL_STATUSES.filter((s) => perTab.some(([, b]) => b.includes(s)));
  // With the API's data known (a real run), the derived and the skipped status must really be rendered: the run's setup skipped a thread and the recordings hold expired ones.
  const mustShow = Object.keys(perPlatform).length > 0 ? (["skipped", "expired"] as const).filter((s) => !seen.includes(s)) : [];
  checklist.record("S02", entriesOk && uncounted.length === 0 && overcounted.length === 0 && filterMissing.length === 0 && empty.length === 0 && short.length === 0 &&
    seen.length >= 3 && mustShow.length === 0 && snap.listBesideThread && snap.copyReply && !snap.keywordsTab ? "pass" : "fail",
    `switcher: ${snap.switcher.join(", ") || "none"}; without count: ${uncounted.join(", ") || "none"}; count above API: ${overcounted.join(", ") || "none"}; status filter lacks: ${filterMissing.join(", ") || "none"}; ` +
    `empty lists: ${empty.join(", ") || "none"}; lists with fewer badges than threads: ${short.join(", ") || "none"}; statuses seen: ${seen.join(", ") || "none"}; never rendered although the data has them: ${mustShow.join(", ") || "none"}; ` +
    `list beside thread: ${snap.listBesideThread}; Copy reply: ${snap.copyReply}; Keywords tab: ${snap.keywordsTab}`);
}
