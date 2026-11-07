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
  /** How the two rows were opened (see OpenTrace); evidence for a failed listBesideThread / copyReply. */
  diagnostics?: string;
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

/** What one openRow call did, so a failed S02 says WHY (the check or the app) instead of only that it failed. */
export interface OpenTrace {
  /** Thread id asked for (null = the setup produced none) and the title head searched for. */
  id: number | null;
  head: string;
  /** Elements whose text contains the title head, all and visible ones, before the click. */
  matches: number;
  visibleBefore: number;
  /** What the click landed on (tag#id.class), "none" when nothing visible matched, or the error that stopped it. */
  clicked: string;
  /** Visible elements with the title head after the click; more than one = list row + thread. */
  visibleAfter: number;
}

export const traceText = (t: OpenTrace): string =>
  `thread ${t.id ?? "none"} "${t.head}": ${t.matches} matches (${t.visibleBefore} visible), clicked ${t.clicked}, ${t.visibleAfter} visible afterwards`;

const elementLabel = (el: Element): string => {
  const cls = typeof el.className === "string" && el.className ? "." + el.className.trim().split(/\s+/).join(".") : "";
  return el.tagName.toLowerCase() + (el.id ? "#" + el.id : "") + cls;
};

/**
 * Switches to the thread's platform and opens its row; the verdict is whether the click worked AND the title is then visible
 * more than once (list row + thread). The title also sits in the thread picker (`<option>`; the select is hidden on a wide
 * screen) which comes BEFORE the list in the DOM, so the click goes to the first VISIBLE match that is not an option: the first
 * match overall was that hidden option and waiting for it timed out (run 14: S02 false although the app was right). A visible
 * dropdown is not a list beside the thread, so options never count. Any failure becomes evidence, never an exception.
 */
async function openRow(page: Page, platformLabel: string, id: number | null, title: string): Promise<{ opened: boolean; trace: OpenTrace }> {
  const head = title.slice(0, 30); // A list may cut a long title: match on its first words.
  const trace: OpenTrace = { id, head, matches: 0, visibleBefore: 0, clicked: "none", visibleAfter: 0 };
  if (id === null) return { opened: false, trace: { ...trace, clicked: "nothing to open (no such thread in the setup)" } };
  if (head === "") return { opened: false, trace: { ...trace, clicked: "nothing to open (the setup has no title for this thread)" } };
  const shown = () => page.getByText(head, { exact: false }).and(page.locator(":not(option)")).filter({ visible: true });
  let clickFailed = false;
  try {
    const name = new RegExp(`^${platformLabel}`, "i");
    const roled = page.getByRole("tab", { name }).first();
    const entry = (await roled.count()) ? roled : page.locator("button, a, [role=button]").filter({ hasText: name }).first();
    if (await entry.count()) await entry.click({ timeout: 5000 }).catch(() => undefined);
    await page.waitForTimeout(400);
    trace.matches = await page.getByText(head, { exact: false }).count();
    trace.visibleBefore = await shown().count();
    const target = shown().first();
    await target.waitFor({ state: "visible", timeout: 8000 });
    trace.clicked = await target.evaluate(elementLabel);
    await target.click({ timeout: 8000 });
  } catch (error) {
    clickFailed = true;
    const was = trace.clicked === "none" ? "" : `${trace.clicked} then `;
    trace.clicked = `${was}failed: ${String((error as Error).message).slice(0, 120)}`;
  }
  try {
    await page.waitForTimeout(600);
    trace.visibleAfter = await shown().count();
  } catch (error) {
    clickFailed = true;
    trace.clicked += ` (page unreadable afterwards: ${String((error as Error).message).slice(0, 80)})`;
  }
  return { opened: !clickFailed && trace.visibleAfter > 1, trace };
}

const LABEL: Record<string, string> = { reddit: "Reddit", hackernews: "Hacker News", linkedin: "LinkedIn" };

export async function snapshotMasterDetail(page: Page, tokenNames: string[], state: RealThreadState): Promise<MasterDetailSnapshot> {
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => undefined);
  await page.waitForSelector('[role="tab"], button', { timeout: 10_000 }).catch(() => undefined);
  const snap = (await page.evaluate(script(tokenNames))) as MasterDetailSnapshot;
  const open = (id: number | null) => openRow(page, LABEL[state.platformOf[id ?? -1]] ?? "Reddit", id, state.titles[id ?? -1] ?? "");
  const first = await open(state.fresh);
  snap.listBesideThread = first.opened;
  const second = await open(state.drafted);
  // getByRole skips hidden elements by default; includeHidden counts the buttons that exist in the page but are not shown.
  const inDom = await page.getByRole("button", { name: /copy reply/i, includeHidden: true }).count();
  const shown = await page.getByRole("button", { name: /copy reply/i }).filter({ visible: true }).count();
  snap.copyReply = shown > 0;
  snap.diagnostics = `open fresh: ${traceText(first.trace)}; open drafted: ${traceText(second.trace)}; Copy reply buttons: ${shown} visible of ${inDom} in the page${inDom > shown ? " (some exist but are hidden)" : ""}; state.fresh ${state.fresh ?? "null"}, state.drafted ${state.drafted ?? "null"}`;
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
    `list beside thread: ${snap.listBesideThread}; Copy reply: ${snap.copyReply}; Keywords tab: ${snap.keywordsTab}` +
    (snap.diagnostics ? `; diagnostics: ${snap.diagnostics}` : ""));
}
