// B10-B15: fetching through the service adapter against the harness's local fake servers (they replay seed/recorded/):
// Syften hits, LinkedIn posts, thread loading, service failures, missing tokens, dropping known threads.
// The fake servers are the only "services" there are: no real network and no real key is involved.
import fs from "node:fs";
import path from "node:path";
import type { Ctx, Scenario } from "./ctx.js";
import { arr, errOf, get, obj, post, str } from "./http.js";
import type { Probe } from "./probe.js";

export const HN_COMMENT = "https://news.ycombinator.com/item?id=46120103";
export const HN_STORY = "https://news.ycombinator.com/item?id=46120001";
export const HN_OTHER = "https://news.ycombinator.com/item?id=46080002";
const REDDIT_1OQ = "https://www.reddit.com/r/ProductManagement/comments/1oq7k2m/";

/** The package does not define the format of linkedin-queries.json; this list (with the query under the usual names) is the harness's reading of "queries with status active". */
export function writeQueries(dataDir: string, shape = 0): void {
  fs.mkdirSync(dataDir, { recursive: true });
  const q = "verification evidence ai coding";
  const list = [{ query: q, search: q, text: q, status: "active" }];
  fs.writeFileSync(path.join(dataDir, "linkedin-queries.json"), JSON.stringify(shape === 0 ? list : { queries: list }));
}

/** Writes the queries file and calls the LinkedIn fetch; an answer that says "no active queries" is tried again with the next file shape. */
export async function linkedinFetch(s: Scenario, body: Record<string, unknown>): Promise<Awaited<ReturnType<typeof post>>> {
  let r = await post(s.api, "/api/fetch/linkedin", body);
  for (const shape of [0, 1]) {
    writeQueries(s.dataDir, shape);
    r = await post(s.api, "/api/fetch/linkedin", body);
    if (!(r.status === 400 && /quer/i.test(r.text))) break;
  }
  return r;
}

/** Where a Scenario for the fetch checks comes from: Syften token from the environment, Apify token from .env.local only. */
export const fetchScenarioOpts = (ctx: Ctx) => ({
  fakeUrls: true, today: true, env: { SYFTEN_TOKEN: ctx.tokens.syften }, envLocal: `APIFY_TOKEN=${ctx.tokens.apify}\n`,
});

const count = (tree: unknown): number => arr(tree).reduce<number>((n, c) => n + 1 + count(obj(c).children), 0);
const ids = (tree: unknown): string[] => arr(tree).flatMap((c) => [str(obj(c).id), ...ids(obj(c).children)]);
const json = (s: string): unknown => { try { return JSON.parse(s); } catch { return {}; } };

/** B10: the Syften fetch. */
export async function fetchSyften(ctx: Ctx, s: Scenario, p: Probe): Promise<void> {
  const a = await post(s.api, "/api/fetch/syften", {});
  const hits = arr(obj(a.json).hits).map(obj);
  const plat = (name: string) => hits.filter((h) => str(h.platform) === name).length;
  p.expect("POST /api/fetch/syften answers 200", a.status === 200, `${a.status} ${a.text.slice(0, 120)}`);
  p.expect("8 hits: 4 Reddit and 4 Hacker News", hits.length === 8 && plat("reddit") === 4 && plat("hn") === 4, `${hits.length} hits; platforms ${hits.map((h) => str(h.platform)).join(",")}`);
  p.expect("the Hacker News comment hit is one of them", hits.some((h) => `${str(h.url)} ${str(h.matched_url)}`.includes(HN_COMMENT)));
  p.expect("every hit has url, key, platform, title, text, author, timestamp, matched_url and known", hits.every((h) => ["url", "key", "platform", "title", "text", "author", "timestamp", "matched_url", "known"].every((k) => k in h)));
  p.expect("dropped_other is 1 (the Bluesky item)", obj(a.json).dropped_other === 1, String(obj(a.json).dropped_other));
  p.expect("the config keeps last_run 2026-11-02T18:00:00Z (the dropped item counts)", obj(obj((await get(s.api, "/api/config")).json)).last_run === "2026-11-02T18:00:00Z");
  const call = ctx.fake.seen.filter((r) => r.service === "syften" && r.url.endsWith("/items/get"))[0];
  const body = obj(json(call?.body ?? "{}"));
  p.expect("Syften got POST items/get with limit 100 and show ai_accepted", !!call && body.limit === 100 && body.show === "ai_accepted", call?.body ?? "no Syften request reached the fake server: SYFTEN_BASE_URL is not honoured, the adapter may call the real host");
  p.expect("Syften got Authorization: Bearer <the token>", call?.headers.authorization === `Bearer ${ctx.tokens.syften}`);
  await post(s.api, "/api/fetch/syften", {});
  const again = ctx.fake.seen.filter((r) => r.service === "syften").at(-1);
  p.expect("the next fetch asks only for what is newer (after = last_run)", obj(json(again?.body ?? "{}")).after === "2026-11-02T18:00:00Z", again?.body);
}

/** B11: the LinkedIn fetch. */
export async function fetchLinkedin(ctx: Ctx, s: Scenario, p: Probe): Promise<void> {
  const a = await linkedinFetch(s, { posted: "week" });
  p.note("linkedin-queries.json is written by the harness as a list of {query, status: active} (the package does not define its format)");
  p.expect("POST /api/fetch/linkedin answers 200", a.status === 200, `${a.status} ${a.text.slice(0, 160)}`);
  const posts = arr(obj(a.json).posts).map(obj);
  p.expect("4 posts", posts.length === 4, String(posts.length));
  p.expect("the company page has flags.company true", posts.some((x) => obj(x.flags).company === true));
  p.expect("every post has known false and an item skeleton", posts.every((x) => x.known === false && typeof x.item === "object" && x.item !== null));
  p.expect("every post has key, url, author, posted_at, text and flags", posts.every((x) => ["key", "url", "author", "posted_at", "text", "flags"].every((k) => k in x)));
  p.expect("the answer names the run (id, status, usd)", ["id", "status", "usd"].every((k) => k in obj(obj(a.json).run)), JSON.stringify(obj(a.json).run));
  const start = ctx.fake.seen.find((r) => r.service === "apify" && r.url.includes("harvestapi~linkedin-post-search/runs"));
  const body = obj(json(start?.body ?? "{}"));
  p.expect("Apify got the actor start with postedLimit week, maxPosts 20, sortBy date, nested comments", !!start && body.postedLimit === "week" && body.maxPosts === 20 && body.sortBy === "date" && body.postNestedComments === true, start?.body?.slice(0, 160));
  p.expect("the run is started with a cost cap (maxTotalChargeUsd)", !!start && /maxTotalChargeUsd=/.test(start.url), start?.url);
  p.expect("Apify got Authorization: Bearer <the token from .env.local>", start?.headers.authorization === `Bearer ${ctx.tokens.apify}`);
  p.expect("the config keeps last_linkedin_run", str(obj((await get(s.api, "/api/config")).json).last_linkedin_run) !== "");
}

/** B12: loading a thread with its comment tree. */
export async function fetchThread(ctx: Ctx, s: Scenario, p: Probe): Promise<void> {
  const hn = await post(s.api, "/api/fetch/thread", { url: HN_COMMENT });
  const hnj = obj(hn.json);
  p.expect("a Hacker News comment url loads", hn.status === 200, `${hn.status} ${hn.text.slice(0, 120)}`);
  p.expect("it resolves to the story", str(hnj.url) === HN_STORY, str(hnj.url));
  p.expect("3 comments in total (the deleted one is dropped)", count(hnj.comments) === 3, String(count(hnj.comments)));
  p.expect("the HTML is plain text", !/<[a-z][^>]*>|&#?\w+;/i.test(JSON.stringify(hnj.comments) + JSON.stringify(hnj.post)), "markup left in the text");
  const rd = await post(s.api, "/api/fetch/thread", { url: REDDIT_1OQ, max_comments: 5, keep: ["mq1a009"] });
  const rj = obj(rd.json);
  const all = ids(rj.comments);
  p.expect("a Reddit url loads", rd.status === 200, `${rd.status} ${rd.text.slice(0, 120)}`);
  p.expect("the tree keeps mq1a009 and its parent mq1a008", all.includes("mq1a009") && all.includes("mq1a008"), all.join(","));
  p.expect("authors read u/<name>", arr(rj.comments).every((c) => /^u\//.test(str(obj(c).author))));
  const scores = arr(rj.comments).map((c) => Number(/\d+/.exec(str(obj(c).stats))?.[0] ?? 0));
  p.expect("top-level comments are ordered by score", scores.every((v, i) => i === 0 || scores[i - 1] >= v), scores.join(","));
  p.expect("rules carry the subreddit rules link", JSON.stringify(rj.rules).includes("https://www.reddit.com/r/ProductManagement/about/rules"), JSON.stringify(rj.rules));
  const req = ctx.fake.seen.find((r) => r.service === "apify" && r.url.includes("reddit-comments-scraper/run-sync-get-dataset-items"));
  const body = obj(json(req?.body ?? "{}"));
  p.expect("Apify got the actor input (postUrls, maxCommentsPerPost 200, no NSFW, no AI analysis) at timeout 240", !!req && body.includeNSFW === false && body.aiAnalysis === false && body.maxCommentsPerPost === 200 && /timeout=240/.test(req.url), req?.body?.slice(0, 160));
  const li = await post(s.api, "/api/fetch/thread", { url: "https://www.linkedin.com/posts/wren-halvorsen_synthetic-activity-7390112233445566771-aB3x" });
  p.equal("a LinkedIn url answers 400 with the plain text", [li.status, errOf(li)], [400, "Only Reddit and Hacker News threads can be loaded by script."]);
  const none = await post(s.api, "/api/fetch/thread", { url: "https://www.reddit.com/r/x/comments/zzz9999/" });
  p.expect("a thread Apify has no post for answers 502 Apify returned no post for <url>", none.status === 502 && errOf(none).startsWith("Apify returned no post for https://www.reddit.com/r/x/comments/zzz9999/"), `${none.status} ${errOf(none)}`);
}

/** B13: a failing service gives 502 with service, status and hint, and stores nothing. */
export async function serviceFailures(ctx: Ctx, s: Scenario, p: Probe): Promise<void> {
  const cfg = (await get(s.api, "/api/config")).text;
  ctx.fake.fail.syften = 401;
  const sy = await post(s.api, "/api/fetch/syften", {}).finally(() => { ctx.fake.fail.syften = undefined; });
  p.expect("Syften 401 answers 502", sy.status === 502, `${sy.status} ${sy.text.slice(0, 120)}`);
  p.expect("the text names the service, the status and the hint (token invalid, regenerate it)", /Syften/.test(errOf(sy)) && /401/.test(errOf(sy)) && /token invalid/i.test(errOf(sy)), errOf(sy));
  p.expect("last_run stays and nothing is stored", (await get(s.api, "/api/config")).text === cfg && arr(obj((await get(s.api, "/api/board")).json).items).length === 0);
  ctx.fake.fail.apify = 402;
  let li: Awaited<ReturnType<typeof post>>, th: Awaited<ReturnType<typeof post>>;
  try {
    li = await linkedinFetch(s, { posted: "week" });
    th = await post(s.api, "/api/fetch/thread", { url: REDDIT_1OQ });
  } finally {
    ctx.fake.fail.apify = undefined;
  }
  p.expect("Apify 402 answers 502 naming Apify, 402 and the credit hint", li.status === 502 && /Apify/.test(errOf(li)) && /402/.test(errOf(li)) && /credit/i.test(errOf(li)), `${li.status} ${errOf(li)}`);
  p.expect("a Reddit thread load fails the same way", th.status === 502 && /Apify/.test(errOf(th)) && /402/.test(errOf(th)), `${th.status} ${errOf(th)}`);
}

/** B13b: a missing token answers 503 with the fix and calls nothing. */
export async function missingTokens(ctx: Ctx, s: Scenario, p: Probe): Promise<void> {
  writeQueries(s.dataDir);
  const before = ctx.fake.seen.length;
  const th = await post(s.api, "/api/fetch/thread", { url: REDDIT_1OQ });
  p.equal("a Reddit thread without APIFY_TOKEN answers 503 with the fix", [th.status, errOf(th)], [503, "APIFY_TOKEN missing: put it into .env.local in the data folder"]);
  const li = await linkedinFetch(s, { posted: "week" });
  p.expect("LinkedIn without APIFY_TOKEN answers 503", li.status === 503 && /APIFY_TOKEN missing/.test(errOf(li)), `${li.status} ${errOf(li)}`);
  const sy = await post(s.api, "/api/fetch/syften", {});
  p.expect("Syften without SYFTEN_TOKEN answers 503", sy.status === 503 && /SYFTEN_TOKEN missing/.test(errOf(sy)), `${sy.status} ${errOf(sy)}`);
  p.expect("the fake servers saw no request", ctx.fake.seen.length === before, `${ctx.fake.seen.length - before} request(s)`);
  const hn = await post(s.api, "/api/fetch/thread", { url: HN_COMMENT });
  p.expect("a Hacker News thread needs no token and loads", hn.status === 200, `${hn.status} ${errOf(hn)}`);
}

/** B15: threads the backend already holds are not offered again. */
export async function dedupe(ctx: Ctx, s: Scenario, p: Probe): Promise<void> {
  const story = ctx.synthetic.find((i) => i.url === HN_STORY);
  if (!story) return void p.expect("the synthetic run holds the story 46120001", false);
  const stored = await post(s.api, "/api/runs", { items: [story] });
  p.expect("the story with its syften_urls is stored", stored.status === 200, `${stored.status} ${errOf(stored)}`);
  const un = await post(s.api, "/api/threads/unseen", { urls: [HN_COMMENT, HN_OTHER, HN_OTHER] });
  p.equal("the alias hit is dropped, the other is answered once", obj(un.json), { unseen: [HN_OTHER] });
  const items = await post(s.api, "/api/threads/unseen", { items: [{ url: HN_COMMENT }, { url: HN_OTHER }] });
  p.equal("the items form answers the same", obj(items.json), { unseen: [HN_OTHER] });
  const hits = arr(obj((await post(s.api, "/api/fetch/syften", {})).json).hits).map(obj);
  const known = (frag: string) => hits.find((h) => `${str(h.url)} ${str(h.matched_url)}`.includes(frag))?.known;
  p.expect("the comment hit on the stored story carries known true", known("id=46120103") === true, String(known("id=46120103")));
  p.expect("the hit on the stored story carries known true", known("id=46120001") === true, String(known("id=46120001")));
  p.expect("a hit on a thread not held carries known false", known("id=46080002") === false, String(known("id=46080002")));
}
