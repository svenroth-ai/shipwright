// B45, B46: two board states the delivered stand-in run does not contain (an X draft above 280 characters, an item with an
// internal review). The harness stores them itself through POST /api/runs after the tour, so the mockup counts stay intact.
import { mainText, openBoard, openThread } from "./board-ui.js";
import { refresh, type BoardEnv } from "./checks-board.js";
import type { Ctx } from "./ctx.js";
import { obj, post, str, type Obj } from "./http.js";
import type { Probe } from "./probe.js";

const SENTENCE = "Fix the tests the change must pass before the agent starts, and let a human say why when a change edits them. ";
const LONG_URL = "https://x.com/synthetic_dev/status/1985000000000000091";
const REVIEW_URL = "https://x.com/synthetic_dev/status/1985000000000000092";
const REVIEW_TEXT = "revised: open with the answer, drop the second sentence";

const xItem = (ctx: Ctx): Obj => ctx.synthetic.find((i) => i.platform === "x") ?? {};
const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function store(b: BoardEnv, ctx: Ctx, extra: Obj): Promise<Obj | undefined> {
  const base = xItem(ctx);
  const res = await post(b.api, "/api/runs", { items: [{ ...base, ...extra }] });
  b.items = await refresh(b.api);
  return res.status === 200 ? b.items.find((i) => i.url === extra.url) : undefined;
}

/** B45: an X draft above 280 characters shows its count in red. */
export async function longXDraft(b: BoardEnv, p: Probe, ctx: Ctx): Promise<void> {
  const text = SENTENCE.repeat(3).trim();
  const item = await store(b, ctx, { url: LONG_URL, reply: { to: "post", text } });
  p.expect(`the harness can store an X draft of ${text.length} characters (the lint does not check X length)`, !!item, "POST /api/runs refused it");
  if (!item) return;
  await openBoard(b.page, b.origin);
  await openThread(b.page, item);
  p.expect(`the card shows ${text.length}/280`, new RegExp(`\\b${text.length}\\s*/\\s*280\\b`).test(await mainText(b.page)));
  const color = await b.page.evaluate(() => {
    const el = [...document.querySelectorAll("main *")].find((e) => e.children.length === 0 && /\/\s*280/.test(e.textContent ?? ""));
    return el ? getComputedStyle(el).color : "";
  });
  const m = /^rgba?\((\d+), ?(\d+), ?(\d+)/.exec(color);
  p.expect("the count above 280 is red (red channel clearly above green and blue)", !!m && Number(m[1]) > 150 && Number(m[1]) > Number(m[2]) + 80 && Number(m[1]) > Number(m[3]) + 80, color || "count not found");
}

/** B46: the optional internal review shows under the thread. */
export async function reviewLine(b: BoardEnv, p: Probe, ctx: Ctx): Promise<void> {
  const item = await store(b, ctx, { url: REVIEW_URL, review: { internal: REVIEW_TEXT } });
  p.expect("an item with review.internal is accepted and stored", !!item, "POST /api/runs refused it");
  if (!item) return;
  p.expect("the stored thread keeps the review", str(obj(item.review).internal) === REVIEW_TEXT, JSON.stringify(item.review ?? null));
  await openBoard(b.page, b.origin);
  await openThread(b.page, item);
  await pause(200);
  const text = await mainText(b.page);
  p.expect("the review line shows under the thread", text.includes(REVIEW_TEXT), text.slice(0, 80));
  p.expect("the why line still shows next to it", text.includes(str(item.why).slice(0, 30)));
}
