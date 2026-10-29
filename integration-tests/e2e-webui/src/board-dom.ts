// The board checks S01, S02 and S04 over a snapshot of the served page. The snapshot is taken in the browser
// (one evaluate call); the verdicts are pure functions over it, so unit tests need no browser.
import type { Page } from "@playwright/test";
import type { Checklist } from "./checklist.js";
import { PLATFORMS, STATUSES } from "./fixture.js";
import { compareTokens, type Tokens } from "./tokens.js";

export interface BoardSnapshot {
  /** Texts of the tab elements (role=tab, else buttons/links named like a platform). */
  tabs: string[];
  /** Status badge texts per tab name, collected after opening each tab. */
  badgesByTab: Record<string, string[]>;
  /** Text inputs that look like a chat box, and elements that look like a chat panel or message log. */
  chatInputs: string[];
  chatPanels: string[];
  /** The served :root value of each requested token ("" = not declared). */
  tokens: Tokens;
}

/** Runs in the page: opens every tab, reads badges, looks for a chat box, reads the requested custom properties. */
function script(tokenNames: string[]): string {
  return `(async () => {
  const text = (e) => (e.textContent || '').trim().replace(/\\s+/g, ' ');
  const platforms = ${JSON.stringify(PLATFORMS)};
  const isTab = (e) => platforms.some((p) => text(e).toLowerCase().startsWith(p.toLowerCase()));
  const findTabs = () => { const roled = [...document.querySelectorAll('[role="tab"]')]; return roled.length > 0 ? roled : [...document.querySelectorAll('button')].filter(isTab); };
  const tabEls = findTabs();
  const visible = (e) => !!(e.offsetWidth || e.offsetHeight || e.getClientRects().length);
  const badges = () => [...document.querySelectorAll('[class*="badge"]')].filter(visible).map((e) => text(e).toLowerCase());
  const badgesByTab = {};
  const names = tabEls.map(text);
  // A board may redraw its tab strip on click: find each tab again by position before clicking it.
  for (let i = 0; i < names.length; i += 1) { const t = findTabs()[i]; if (t) t.click(); await new Promise((r) => setTimeout(r, 500)); badgesByTab[names[i]] = badges(); }
  if (tabEls.length === 0) badgesByTab[''] = badges();
  const inputRe = /chat|composer|type a (message|command)|send a message/i;
  const panelRe = /chat|composer|message-log|msg-log/i;
  const chatInputs = [...document.querySelectorAll('input, textarea')].filter((e) => e.type !== 'hidden' && inputRe.test([e.placeholder, e.getAttribute('aria-label'), e.name, e.id].join(' '))).map((e) => e.outerHTML.slice(0, 120));
  const chatPanels = [...document.querySelectorAll('[class], [id], [aria-label]')].filter((e) => panelRe.test([e.className && e.className.baseVal === undefined ? e.className : '', e.id, e.getAttribute('aria-label')].join(' ')) && !['INPUT','TEXTAREA','SCRIPT','STYLE'].includes(e.tagName) && visible(e)).map((e) => e.tagName.toLowerCase() + ' ' + String(e.className || e.id || e.getAttribute('aria-label')).slice(0, 60));
  const cs = getComputedStyle(document.documentElement);
  const tokens = {};
  for (const n of ${JSON.stringify(tokenNames)}) tokens[n] = cs.getPropertyValue(n).trim();
  return { tabs: tabEls.map(text), badgesByTab, chatInputs, chatPanels, tokens };
})()`;
}

export async function snapshotBoard(page: Page, tokenNames: string[]): Promise<BoardSnapshot> {
  // The board is vanilla JS over the API: wait for it to render before reading it.
  await page.waitForLoadState("networkidle", { timeout: 15_000 }).catch(() => undefined);
  await page.waitForSelector('[role="tab"], button', { timeout: 10_000 }).catch(() => undefined);
  return (await page.evaluate(script(tokenNames))) as BoardSnapshot;
}

/** S01: the board is the whole page. S02: one tab per platform, a status badge per thread. */
/** `perPlatform`: threads per platform key from the API (reddit, hackernews, linkedin); an open tab must show a badge per thread. */
export function checkBoardShape(snap: BoardSnapshot, checklist: Checklist, perPlatform: Record<string, number> = {}): void {
  const chat = [...snap.chatInputs, ...snap.chatPanels];
  checklist.record("S01", chat.length === 0 && snap.tabs.length > 0 ? "pass" : "fail",
    chat.length === 0 ? `no chat input or panel found; ${snap.tabs.length} tabs` : `chat-like elements: ${chat.slice(0, 3).join(" | ")}`);

  // One tab per platform; the order is not part of the requirement.
  const tabsOk = snap.tabs.length === PLATFORMS.length && PLATFORMS.every((p) => snap.tabs.some((t) => t.toLowerCase().startsWith(p.toLowerCase())));
  // Only status badges count: a kit counter or label that shares the badge class is not a thread status.
  const perTab = Object.entries(snap.badgesByTab).map(([n, b]) => [n, b.filter((x) => (STATUSES as readonly string[]).includes(x))] as [string, string[]]);
  const all = perTab.flatMap(([, b]) => b);
  const empty = perTab.filter(([, b]) => b.length === 0).map(([n]) => n);
  const key = (name: string) => name.toLowerCase().replace(/\s*\(?\d+\)?$/, "").replace(/\s+/g, "");
  const short = perTab.filter(([name, b]) => b.length < (perPlatform[key(name)] ?? 0)).map(([n]) => n);
  const seen = STATUSES.filter((s) => all.includes(s));
  // Every platform the API listed threads for needs its tab, and every tab needs its count: otherwise nothing ties badges to threads.
  const tabKeys = perTab.map(([n]) => key(n));
  const wanted = Object.keys(perPlatform);
  const unmapped = wanted.filter((k) => !tabKeys.includes(k));
  const uncounted = wanted.length > 0 ? perTab.filter(([n]) => !(key(n) in perPlatform)).map(([n]) => n) : [];
  checklist.record("S02", tabsOk && empty.length === 0 && short.length === 0 && unmapped.length === 0 && uncounted.length === 0 && seen.length === STATUSES.length ? "pass" : "fail",
    `tabs: ${snap.tabs.join(", ") || "none"}; empty tabs: ${empty.join(", ") || "none"}; tabs with fewer badges than threads: ${short.join(", ") || "none"}; API platforms without a tab: ${unmapped.join(", ") || "none"}; tabs without an API count: ${uncounted.join(", ") || "none"}; statuses seen across tabs: ${seen.join(", ") || "none"}`);
}

/** S04: every colour and font-size token the package declares has that value on the served board. */
export function checkBoardTokens(snap: BoardSnapshot, declared: Tokens, checklist: Checklist): void {
  const r = compareTokens(declared, snap.tokens);
  checklist.record("S04", r.declared > 0 && r.mismatches.length === 0 ? "pass" : "fail",
    r.declared === 0 ? "the package declares no tokens" : `${r.matching}/${r.declared} declared tokens match${r.mismatches.length ? "; " + r.mismatches.slice(0, 5).join("; ") : ""}`);
}
