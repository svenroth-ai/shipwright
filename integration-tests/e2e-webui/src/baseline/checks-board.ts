// B35-B46: the served board in a browser, against a companion the stand-in agent has filled the way the approved mockups show it
// (synthetic run stored, reddit:1on3f8q posted, reddit:1o8zw3d skipped, clock 2026-11-03). Status counts, texts and layout come
// from the brief's fit criteria; the elements are found by role and visible text.
import type { Page } from "@playwright/test";
import { filterLabel, filterOptions, findItem, itemsOf, leafCount, mainText, openBoard, openThread, pickPlatform, readTabs, rowTitle, setFilter } from "./board-ui.js";
import { K_HN, K_POSTED, K_SKIPPED } from "./checks-runs.js";
import { arr, get, obj, post, str, type Api, type Obj } from "./http.js";
import type { Probe } from "./probe.js";
import { compareFonts, compareTokens, parseFontTokens, parseTokens } from "../tokens.js";

export interface BoardEnv {
  page: Page;
  /** A page in a fresh browser context with the given width (clipboard permitted). */
  newPage(width?: number): Promise<Page>;
  origin: string;
  api: Api;
  items: Obj[];
  guidelines: string;
  fixtureDir: string;
}

const KEY_1OQ = "reddit:1oq7k2m";
const wait = (ms: number) => new Promise((r) => setTimeout(r, ms));
const sameCounts = (got: { name: string; count: number }[], want: [string, number][]) => JSON.stringify(got.map((c) => [c.name, c.count])) === JSON.stringify(want);

export async function refresh(api: Api): Promise<Obj[]> {
  return itemsOf((await get(api, "/api/threads?status=all")).json);
}

/** B35: master-detail shape and the counts of the mockup state. */
export async function masterDetail(b: BoardEnv, p: Probe): Promise<void> {
  await openBoard(b.page, b.origin);
  p.expect("the platform switch shows LinkedIn 2, Reddit 1, Hacker News 2, X 1 in that order", sameCounts(await readTabs(b.page), [["LinkedIn", 2], ["Reddit", 1], ["Hacker News", 2], ["X", 1]]), JSON.stringify(await readTabs(b.page)));
  const label = await filterLabel(b.page);
  p.expect("the board opens on the filter Open 6", label?.name === "Open" && label.count === 6, JSON.stringify(label));
  p.expect("the filter offers Open 6, Posted 1, Skipped 1, Expired 3 and All 11", sameCounts(await filterOptions(b.page), [["Open", 6], ["Posted", 1], ["Skipped", 1], ["Expired", 3], ["All", 11]]), JSON.stringify(await filterOptions(b.page)));
  await setFilter(b.page, "Posted");
  p.expect("Posted shows only Reddit with one thread", sameCounts(await readTabs(b.page), [["Reddit", 1]]), JSON.stringify(await readTabs(b.page)));
  await setFilter(b.page, "Skipped");
  p.expect("Skipped shows one thread", (await readTabs(b.page)).reduce((n, t) => n + t.count, 0) === 1);
  await setFilter(b.page, "Open");
  const chat = await b.page.evaluate(() => [...document.querySelectorAll("input, textarea")].filter((e) => (e as HTMLInputElement).type !== "hidden" && /chat|composer|send a message|type a (message|command)/i.test([(e as HTMLInputElement).placeholder, e.getAttribute("aria-label"), e.id].join(" "))).length);
  p.expect("there is no chat input on the board", chat === 0, `${chat} chat-like input(s)`);
}

/** B36: keyboard j/k and the address hash. */
export async function keyboardAndHash(b: BoardEnv, p: Probe): Promise<void> {
  await openBoard(b.page, b.origin);
  await pickPlatform(b.page, "hn");
  const hashOf = () => b.page.evaluate(() => decodeURIComponent(location.hash));
  await b.page.getByText(rowTitle(findItem(b.items, "hn:46120001")), { exact: false }).first().click();
  await b.page.locator("h1").first().click({ trial: false }).catch(() => undefined);
  await b.page.keyboard.press("j");
  await b.page.waitForTimeout(350);
  const first = await hashOf();
  await b.page.keyboard.press("k");
  await b.page.waitForTimeout(350);
  const back = await hashOf();
  await b.page.keyboard.press("j");
  await b.page.waitForTimeout(350);
  const next = await hashOf();
  p.expect("the selected thread's key is in the address hash", /hn:46\d+/.test(first), first);
  p.expect("j selects the next thread and k the previous one", next === first && back !== first && /hn:/.test(back), `j ${first}, k ${back}, j ${next}`);
  await setFilter(b.page, "Posted");
  await b.page.getByText(rowTitle(findItem(b.items, K_POSTED)), { exact: false }).first().click();
  const posted = await hashOf();
  const other = await b.newPage();
  try {
    await openBoard(other, b.origin, await b.page.evaluate(() => location.hash));
    const label = await filterLabel(other);
    p.expect("opening a posted thread's address switches the filter to All", /1on3f8q/.test(posted) && label?.name === "All", `${posted}; filter ${JSON.stringify(label)}`);
    p.expect("and shows that thread", (await mainText(other)).includes(rowTitle(findItem(b.items, K_POSTED)).slice(0, 30)));
  } finally {
    await other.context().close();
  }
}

function commentById(tree: unknown, id: string): Obj | null {
  for (const c of arr(tree).map(obj)) {
    if (c.id === id) return c;
    const hit = commentById(c.children, id);
    if (hit) return hit;
  }
  return null;
}

/** B37: summary, draft card placement, why/review/posted link, platform look. */
export async function threadView(b: BoardEnv, p: Probe): Promise<void> {
  const t = findItem(b.items, KEY_1OQ);
  await openBoard(b.page, b.origin);
  await openThread(b.page, t);
  const text = await mainText(b.page);
  p.expect("the summary shows Question, Others say and Our angle", ["Question", "Others say", "Our angle"].every((s) => text.includes(s)));
  const angle = str(obj(t.summary).angle).slice(0, 30);
  const bold = await b.page.evaluate((a) => { const el = [...document.querySelectorAll("main *")].find((e) => e.children.length === 0 && (e.textContent ?? "").includes(a)); return el ? Number(getComputedStyle(el).fontWeight) >= 600 || !!el.closest("b, strong") : null; }, angle);
  p.expect("the angle text is bold", bold === true, bold === null ? "angle text not found" : String(bold));
  p.expect("it offers the link 'Jump to the draft (reply to u/maple_orbit)'", /Jump to the draft \(reply to u\/maple_orbit\)/.test(text));
  p.expect("the feedback field sits in the summary", (await b.page.locator("main textarea").count()) > 0);
  const target = commentById(t.comments, "mq1a009");
  const prefix = str(target?.text).slice(0, 30);
  const inside = await b.page.evaluate(({ prefix: pre, title }) => {
    const main = document.querySelector("main") ?? document.body;
    const leaf = (re: RegExp) => [...main.querySelectorAll("*")].find((e) => e.children.length === 0 && re.test((e.textContent ?? "").trim()));
    const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const draft = leaf(/^Draft reply\b/i);
    const comment = leaf(new RegExp(`^${esc(pre)}`));
    const head = leaf(new RegExp(esc(title.slice(0, 40))));
    if (!draft || !comment) return `not found: ${draft ? "" : "draft card "}${comment ? "" : "comment"}`;
    let a: Element | null = comment;
    while (a && !a.contains(draft)) a = a.parentElement;
    return a && !(head && a.contains(head)) && a !== main ? "inside" : "outside";
  }, { prefix, title: str(obj(t.post).title) });
  p.expect("the draft card sits inside the comment mq1a009", inside === "inside", inside);
  p.expect("the why line shows under the thread", text.includes(str(t.why).slice(0, 40)));
  const postLevel = findItem(b.items, "reddit:1o4kq7e");
  await openThread(b.page, postLevel);
  const order = await b.page.evaluate(({ title, first }) => {
    const main = document.querySelector("main") ?? document.body;
    const leaf = (s: string) => [...main.querySelectorAll("*")].find((e) => e.children.length === 0 && (e.textContent ?? "").trim().startsWith(s));
    const head = leaf(title), draft = [...main.querySelectorAll("*")].find((e) => e.children.length === 0 && /^Draft reply\b/i.test((e.textContent ?? "").trim())), c = leaf(first);
    if (!head || !draft) return "not found";
    const F = Node.DOCUMENT_POSITION_FOLLOWING;
    return (head.compareDocumentPosition(draft) & F) && (!c || (draft.compareDocumentPosition(c) & F)) ? "under the post" : "elsewhere";
  }, { title: str(obj(postLevel.post).title).slice(0, 40), first: str(obj(arr(postLevel.comments)[0]).text).slice(0, 30) });
  p.expect("a reply to the post sits under the post, before the comments", order === "under the post", order);
  const posted = findItem(b.items, K_POSTED);
  await openThread(b.page, posted, "Posted");
  p.expect("a posted thread shows the link to the person's comment", (await b.page.locator("main a[href^='https://']").evaluateAll((as) => as.map((a) => (a as HTMLAnchorElement).href))).some((h) => h.includes("mq2bZZ1")) || (await mainText(b.page)).includes("mq2bZZ1"));
  const noSummary = b.items.find((i) => !i.summary);
  if (noSummary) {
    await openThread(b.page, noSummary);
    p.expect("a thread without a summary says 'No summary for this thread.'", (await mainText(b.page)).includes("No summary for this thread."));
  }
  const hnItem = findItem(b.items, "hn:46120001");
  await openThread(b.page, hnItem);
  const hn = await b.page.evaluate(() => { const els = [...(document.querySelector("main") ?? document.body).querySelectorAll("*")]; return { verdana: els.some((e) => /verdana/i.test(getComputedStyle(e).fontFamily)), orange: els.some((e) => { const s = getComputedStyle(e); return [s.backgroundColor, s.borderTopColor, s.borderLeftColor, s.borderBottomColor].some((c) => c === "rgb(255, 102, 0)"); }) }; });
  p.expect("Hacker News threads have the orange bar and Verdana", hn.verdana && hn.orange, JSON.stringify(hn));
  await openThread(b.page, b.items.find((i) => i.platform === "linkedin" && arr(i.comments).length > 0) ?? {});
  const bubble = await b.page.evaluate(() => [...(document.querySelector("main") ?? document.body).querySelectorAll("*")].some((e) => getComputedStyle(e).backgroundColor === "rgb(243, 242, 239)"));
  p.expect("LinkedIn comments sit in grey bubbles", bubble);
  const avatar = await b.page.evaluate(() => [...(document.querySelector("main") ?? document.body).querySelectorAll("img, span, div")].some((e) => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e); return r.width >= 20 && r.width <= 72 && Math.abs(r.width - r.height) < 2 && (e.tagName === "IMG" || parseFloat(s.borderTopLeftRadius) >= r.width / 2 - 1 || s.borderTopLeftRadius.includes("%")); }));
  p.expect("LinkedIn threads show round avatars", avatar);
}

/** B38: one comment count, the stored tree's. */
export async function commentCount(b: BoardEnv, p: Probe): Promise<void> {
  const api = obj((await get(b.api, `/api/threads/${encodeURIComponent(KEY_1OQ)}`)).json);
  p.expect("GET /api/threads/reddit:1oq7k2m answers comment_count 12", api.comment_count === 12, String(api.comment_count));
  await openBoard(b.page, b.origin);
  for (const key of [KEY_1OQ, "hn:46120001", "linkedin:7390112233445566771"]) {
    const item = findItem(b.items, key);
    const n = Number(item.comment_count);
    await openThread(b.page, item);
    const re = n === 1 ? "\\b1 comment\\b" : `\\b${n} comments\\b`;
    p.expect(`${key}: the list row and the post header both read ${n === 1 ? "1 comment" : `${n} comments`}`, (await leafCount(b.page, re)) >= 2 || (await b.page.getByText(new RegExp(re)).count()) >= 2, `${await leafCount(b.page, re)} places`);
  }
  await openThread(b.page, findItem(b.items, KEY_1OQ));
  p.expect("the platform's own total (13) is not shown", (await b.page.getByText(/\b13 comments\b/).count()) === 0);
}

/** B39: Copy reply, Open thread, the X character count. */
export async function copyAndOpen(b: BoardEnv, p: Probe): Promise<void> {
  const t = findItem(b.items, KEY_1OQ);
  await openBoard(b.page, b.origin);
  await openThread(b.page, t);
  const copy = b.page.getByRole("button", { name: /Copy reply/i }).first();
  p.expect("a Copy reply button is shown", (await copy.count()) > 0);
  await copy.click();
  const clip = await b.page.evaluate(() => navigator.clipboard.readText()).catch((e: Error) => `clipboard unreadable: ${e.message}`);
  p.expect("Copy reply puts exactly the reply text on the clipboard", clip === str(obj(t.reply).text), clip.slice(0, 80));
  await wait(150);
  p.expect("the button then reads Copied", /Copied/i.test(await copy.innerText().catch(() => "")));
  const sent: string[] = [];
  await b.page.route("**/api/open", async (route) => { sent.push(route.request().postData() ?? ""); await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ opened: str(obj(JSON.parse(route.request().postData() ?? "{}")).url) }) }); });
  const button = b.page.getByRole("button", { name: /Open thread/i }).first();
  const link = b.page.getByRole("link", { name: /Open thread/i }).first();
  if ((await button.count()) > 0) {
    await button.click();
    await wait(400);
    p.expect("Open thread posts /api/open with the thread's address (the request is answered by the harness, no browser starts)", sent.length === 1 && str(obj(JSON.parse(sent[0] || "{}")).url) === str(t.url), sent.join(" | ") || "no request");
  } else {
    const href = (await link.count()) > 0 ? await link.getAttribute("href") : null;
    p.expect("Open thread is offered with the thread's address", href === str(t.url), String(href));
  }
  await b.page.unroute("**/api/open");
  const x = b.items.find((i) => i.platform === "x") ?? {};
  await openThread(b.page, x);
  const len = str(obj(x.reply).text).length;
  p.expect(`the X draft card shows ${len}/280`, new RegExp(`\\b${len}\\s*/\\s*280\\b`).test(await mainText(b.page)), String(len));
}

/** B40: the feedback field. */
export async function feedbackOnBoard(b: BoardEnv, p: Probe): Promise<void> {
  const t = findItem(b.items, K_HN);
  b.page.on("dialog", (d) => void d.accept());
  await openBoard(b.page, b.origin);
  await openThread(b.page, t, "Open");
  const field = b.page.locator("main textarea").first();
  const entries = async () => arr(obj((await get(b.api, "/api/feedback?status=all")).json).entries).map(obj);
  const before = (await entries()).length;
  await field.fill("Board feedback one.");
  await b.page.getByRole("button", { name: /Save feedback/i }).first().click();
  await wait(700);
  p.expect("Save feedback stores the entry (it shows in the queue)", (await entries()).length === before + 1 && (await entries()).some((e) => e.text === "Board feedback one." && e.key === K_HN), `${before} -> ${(await entries()).length}`);
  const chip = await b.page.evaluate(() => { const el = [...document.querySelectorAll("main *")].find((e) => e.children.length === 0 && /Board feedback one\./.test(e.textContent ?? "")); let n: Element | null = el ?? null; for (let i = 0; n && i < 4; i++, n = n.parentElement) if ([...n.querySelectorAll("*")].some((c) => c.children.length === 0 && (c.textContent ?? "").trim().toLowerCase() === "open")) return true; return false; });
  p.expect("the entry shows under the summary with the chip open", chip);
  await field.fill("Board feedback two.");
  await field.press("Control+Enter");
  await wait(700);
  p.expect("Ctrl+Enter saves too", (await entries()).some((e) => e.text === "Board feedback two."));
  const keep = "Text that must survive a failed save.";
  await b.page.route("**/api/feedback", (route) => (route.request().method() === "POST" ? route.fulfill({ status: 500, contentType: "application/json", body: JSON.stringify({ error: "disk full" }) }) : route.continue()));
  await field.fill(keep);
  await b.page.getByRole("button", { name: /Save feedback/i }).first().click();
  await wait(700);
  await b.page.unroute("**/api/feedback");
  p.expect("a failed save shows \"Not saved\" with the error and says the text is still there", /Not saved:.*Your text is still here/s.test(await mainText(b.page)), (await mainText(b.page)).slice(0, 80));
  p.expect("the typed text is still in the field after a failed save", (await field.inputValue()) === keep);
  await field.fill("");
}

/** B41: status actions on the board. */
export async function statusOnBoard(b: BoardEnv, p: Probe): Promise<void> {
  const t = b.items.find((i) => i.platform === "linkedin" && i.status === "drafted") ?? {};
  const status = async () => str(obj((await get(b.api, `/api/threads/${encodeURIComponent(str(t.key))}`)).json).status);
  await openBoard(b.page, b.origin);
  await openThread(b.page, t, "Open");
  await b.page.getByRole("button", { name: "Skip", exact: true }).first().click();
  await wait(600);
  p.expect("Skip sets the status skipped", (await status()) === "skipped", await status());
  await openThread(b.page, t, "Skipped");
  await b.page.getByRole("button", { name: /^Reopen$/ }).first().click();
  await wait(600);
  p.expect("Reopen sets it back to drafted", (await status()) === "drafted", await status());
  await openThread(b.page, t, "Open");
  await b.page.getByRole("button", { name: /Mark posted/i }).first().click();
  const link = "https://www.linkedin.com/feed/update/urn:li:activity:7390000000000000001/";
  await b.page.locator("input[type=url], input[placeholder*='https']").first().fill(link);
  await b.page.getByRole("button", { name: /^Save$/ }).first().click();
  await wait(700);
  const th = obj((await get(b.api, `/api/threads/${encodeURIComponent(str(t.key))}`)).json);
  p.expect("Mark posted with a link stores posted and the link", th.status === "posted" && th.posted_url === link, `${str(th.status)} ${str(th.posted_url)}`);
  await post(b.api, "/api/status", { key: str(t.key), status: "drafted" });
}

/** B42: 390 pixels width. */
export async function phone(b: BoardEnv, p: Probe): Promise<void> {
  const page = await b.newPage(390);
  try {
    await openBoard(page, b.origin);
    const open = b.items.filter((i) => i.status === "drafted");
    const info = await page.evaluate(() => {
      const sel = [...document.querySelectorAll("select")].find((s) => s.getClientRects().length > 0);
      const tabs = [...document.querySelectorAll('[role="tab"]')].map((t) => t.getBoundingClientRect());
      return { scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth, width: window.innerWidth, hasSelect: !!sel, options: sel ? [...sel.options].map((o) => o.text) : [], tabsRight: Math.max(0, ...tabs.map((r) => r.right)), rows: new Set(tabs.map((r) => Math.round(r.top))).size };
    });
    p.expect("there is no horizontal scroll (the page is not wider than its 390 px viewport)", info.scrollWidth <= info.clientWidth && info.width === 390, `scrollWidth ${info.scrollWidth}, viewport ${info.width}`);
    p.expect("the platform switch wraps onto a second row and stays inside the screen", info.tabsRight <= 390 && info.rows >= 2, `right edge ${info.tabsRight}, ${info.rows} row(s)`);
    p.expect("a picker (select) with the thread titles is shown", info.hasSelect && info.options.length >= 1 && info.options.length <= open.length, `${info.options.length} options, ${open.length} open threads (the picker lists the active platform's threads)`);
    const prev = page.getByRole("button", { name: "Previous thread" });
    const next = page.getByRole("button", { name: "Next thread" });
    p.expect("Previous thread and Next thread are shown, Previous disabled on the first", (await prev.count()) > 0 && (await next.count()) > 0 && (await prev.first().isDisabled()), "");
    const title = rowTitle(open[0] ?? {});
    p.expect("the thread list column is not displayed (the title is visible once, in the thread)", (await leafCount(page, `^${title.slice(0, 30).replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}`)) <= 1);
    await page.locator("select").first().selectOption({ index: info.options.length - 1 });
    await page.waitForTimeout(400);
    p.expect("choosing the last title selects it and disables Next", await next.first().isDisabled());
  } finally {
    await page.context().close();
  }
}

/** B43: the colour, font-size and font tokens of visual-guidelines.md on the served board. */
export async function tokens(b: BoardEnv, p: Probe): Promise<void> {
  await openBoard(b.page, b.origin);
  const declared = parseTokens(b.guidelines);
  const fonts = parseFontTokens(b.guidelines);
  const names = [...Object.keys(declared), ...Object.keys(fonts)];
  const served = await b.page.evaluate((ns) => { const cs = getComputedStyle(document.documentElement); return Object.fromEntries(ns.map((n) => [n, cs.getPropertyValue(n).trim()])); }, names);
  const r = compareTokens(declared, served);
  const f = compareFonts(fonts, served);
  p.expect("the package declares tokens", r.declared > 0);
  p.expect(`every colour and font-size token has its value on the board (${r.matching}/${r.declared})`, r.mismatches.length === 0, r.mismatches.slice(0, 4).join("; "));
  p.expect("the font tokens name Inter and Geist Mono", f.mismatches.length === 0 && f.declared === 2, f.mismatches.join("; ") || `${f.declared} font tokens`);
}

/** B44: the board notices a write it did not make itself (version poll every 3 seconds) and offers Reload. */
export async function versionBanner(b: BoardEnv, p: Probe): Promise<void> {
  const v = async () => JSON.stringify((await get(b.api, "/api/version")).json);
  await openBoard(b.page, b.origin);
  const before = await v();
  p.expect("GET /api/version answers a JSON object", Object.keys(obj((await get(b.api, "/api/version")).json)).length > 0, before);
  p.expect("no update banner is shown before an outside write", (await b.page.getByText(/Claude updated the board/i).count()) === 0);
  const t = b.items.find((i) => i.status === "drafted") ?? {};
  await post(b.api, "/api/feedback", { key: str(t.key), text: "Outside write for the version poll." });
  await wait(4500);
  p.expect("the version changes after the write", (await v()) !== before);
  p.expect("the board shows \"Claude updated the board\" with a Reload button", (await b.page.getByText(/Claude updated the board/i).count()) > 0 && (await b.page.getByRole("button", { name: /Reload/i }).count()) > 0);
}
