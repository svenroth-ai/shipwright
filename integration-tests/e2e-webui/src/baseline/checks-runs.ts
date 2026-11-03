// B16-B21, B23: what the stand-in agent stores and what the backend guarantees about it: runs all or nothing, the draft lint,
// status rules, the derived expired status (clock fixed by SOCIAL_ENGAGEMENT_TODAY), feedback, the feedback queue, lessons.
// The functions run in this order on ONE companion: later ones use the threads the earlier ones stored.
import fs from "node:fs";
import path from "node:path";
import { TODAY, type Ctx, type Scenario } from "./ctx.js";
import { arr, errOf, get, obj, post, put, str, type Api, type Obj } from "./http.js";
import type { Probe } from "./probe.js";

export const K_POSTED = "reddit:1on3f8q";
export const K_SKIPPED = "reddit:1o8zw3d";
export const K_HN = "hn:46080002";
const enc = encodeURIComponent;
const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v)) as T;
const threadOf = async (api: Api, key: string): Promise<Obj> => obj((await get(api, `/api/threads/${enc(key)}`)).json);
const listOf = async (api: Api, q: string): Promise<Obj[]> => arr(obj((await get(api, `/api/threads?status=${q}`)).json).threads).map(obj);
const plain = (e: unknown): string => JSON.stringify(e);
const day = (offset: number): string => new Date(Date.parse(`${TODAY}T00:00:00Z`) + offset * 86_400_000).toISOString().slice(0, 10);

/** The stand-in agent's item for url `url` taken from the synthetic run, with changes. */
function variant(ctx: Ctx, url: string, over: Obj): Obj {
  const base = ctx.synthetic.find((i) => i.url === url);
  return { ...clone(base ?? {}), ...over };
}

/** B16: a run is stored all or nothing, kept threads stay, runs are archived newest first. */
export async function runStorage(ctx: Ctx, s: Scenario, p: Probe): Promise<void> {
  const check = await post(s.api, "/api/runs/check", { items: ctx.synthetic });
  p.expect("the synthetic run passes /api/runs/check", check.status === 200 && obj(check.json).ok === true, `${check.status} ${plain(obj(check.json).errors).slice(0, 160)}`);
  const first = await post(s.api, "/api/runs", { items: ctx.synthetic });
  const fj = obj(first.json);
  p.expect("POST /api/runs with the 11 items answers stored 11, kept []", first.status === 200 && fj.stored === 11 && arr(fj.kept).length === 0, `${first.status} ${first.text.slice(0, 160)}`);
  p.expect("the run id is YYYYMMDD-HHMMSS", /^\d{8}-\d{6}$/.test(str(fj.run_id)), str(fj.run_id));
  p.expect("GET /api/board lists 11 items", arr(obj((await get(s.api, "/api/board")).json).items).length === 11);
  p.expect("a platform the app does not handle is skipped and listed", await (async () => {
    const odd = variant(ctx, str(ctx.synthetic[0].url), { platform: "bluesky", url: "https://bsky.app/profile/e2e/post/1" });
    const a = await post(s.api, "/api/runs/check", { items: [odd] });
    return a.status === 200 && plain(obj(a.json).skipped).includes("bsky.app");
  })());
  await post(s.api, "/api/status", { key: K_POSTED, status: "posted" });
  await new Promise((r) => setTimeout(r, 1100)); // run ids have one-second resolution
  const old = str(obj(obj(await threadOf(s.api, K_POSTED)).reply).text);
  const changed = variant(ctx, "https://www.reddit.com/r/ExperiencedDevs/comments/1on3f8q/", { reply: { ...obj(ctx.synthetic[1].reply), text: `${str(obj(ctx.synthetic[1].reply).text)} Thanks for reading.` } });
  const second = await post(s.api, "/api/runs", { items: [changed] });
  p.expect("a changed draft for a posted thread is answered in kept", plain(obj(second.json).kept).includes(K_POSTED), second.text.slice(0, 160));
  p.expect("the stored draft of the posted thread is unchanged", str(obj((await threadOf(s.api, K_POSTED)).reply).text) === old);
  const before = (await get(s.api, "/api/board")).text;
  const runsBefore = arr(obj((await get(s.api, "/api/runs")).json).runs).length;
  const bad = await post(s.api, "/api/runs", { items: [variant(ctx, str(ctx.synthetic[2].url), { url: "http://not-https.example/x" }), clone(ctx.synthetic[3])] });
  p.expect("a run with one bad item answers 422 and says nothing was written", bad.status === 422 && /nothing written/.test(errOf(bad)), `${bad.status} ${errOf(bad)}`);
  p.expect("the board is unchanged", (await get(s.api, "/api/board")).text === before);
  p.expect("no run is archived for it", arr(obj((await get(s.api, "/api/runs")).json).runs).length === runsBefore);
  p.expect("a body without items answers 400", (await post(s.api, "/api/runs", { foo: 1 })).status === 400);
  const runs = arr(obj((await get(s.api, "/api/runs")).json).runs).map(obj);
  p.expect("GET /api/runs lists both runs, newest first", runs.length === 2 && str(runs[0].run_id) > str(runs[1].run_id) && runs[1].items === 11, plain(runs).slice(0, 200));
}

const ERRORS_EXPERTISE = ["em/en dash in why", "reply.to not found in comments: c9", 'never write "beta"', 'never write "v1.0"', '"Command Center" must follow "Shipwright"', "mode expertise allows no product mention and no link"];

/** B17: the lint rules are backend validation, with the documented texts. */
export async function lint(ctx: Ctx, s: Scenario, p: Probe): Promise<void> {
  const url = "https://news.ycombinator.com/item?id=45900003";
  const bad = variant(ctx, url, { why: "A real question — worth answering.", reply: { to: "c9", text: "We delve into Shipwright beta v1.0 and the Command Center, see https://svenroth.ai/x" } });
  await put(s.api, "/api/config", { mode: "expertise" });
  const a = await post(s.api, "/api/runs/check", { items: [bad] });
  p.expect("mode expertise: 422", a.status === 422, String(a.status));
  const errs = plain(obj(a.json).errors);
  for (const e of ERRORS_EXPERTISE) p.expect(`error: ${e}`, errs.includes(e), errs.slice(0, 120));
  p.expect("warning: tone words ['delve']", plain(obj(a.json).warnings).includes("tone words ['delve']"), plain(obj(a.json).warnings));
  p.expect("the error list names the item's url", errs.includes("45900003"));
  await put(s.api, "/api/config", { mode: "open" });
  const open = await post(s.api, "/api/runs/check", { items: [bad] });
  p.expect("mode open: the link error becomes the UTM rule", plain(obj(open.json).errors).includes("svenroth.ai link needs UTM tags: https://svenroth.ai/x"), plain(obj(open.json).errors).slice(0, 160));
  await put(s.api, "/api/config", { mode: "expertise" });
  const comments = Array.from({ length: 11 }, (_, i) => ({ id: `c${i + 1}`, author: "u/e2e", age: "1h", text: "x", stats: "1 point", children: [] }));
  const shape = variant(ctx, url, { date: "03.11.2026", url: "http://news.ycombinator.com/item?id=45900003", comments, summary: undefined, reply: { to: "post", text: "Plain answer." } });
  const b = plain(obj((await post(s.api, "/api/runs/check", { items: [shape] })).json).errors);
  for (const e of ["date must be YYYY-MM-DD, got '03.11.2026'", "url must be https", "11 comments, needs summary {question, others, angle}"]) p.expect(`error: ${e}`, b.includes(e), b.slice(0, 120));
  const empty = await post(s.api, "/api/runs/check", { items: [{}] });
  p.expect("an item with no fields is a 422 with errors", empty.status === 422 && arr(obj(empty.json).errors).length > 0, String(empty.status));
  const unreadable = await post(s.api, "/api/runs/check", { items: [42] });
  p.expect("an item the lint cannot read is an error, not a pass", unreadable.status === 422 || unreadable.status === 400, String(unreadable.status));
  const clean = await post(s.api, "/api/runs/check", { items: [ctx.synthetic.find((i) => i.url === url)] });
  p.expect("a clean item passes with ok true", clean.status === 200 && obj(clean.json).ok === true && arr(obj(clean.json).errors).length === 0, `${clean.status} ${plain(obj(clean.json).errors)}`);
  const text = str(obj(ctx.synthetic.find((i) => i.url === url)?.reply).text);
  const tone = variant(ctx, url, { reply: { to: "post", text: `${text} We leverage this.` } });
  const warn = await post(s.api, "/api/runs/check", { items: [tone] });
  p.expect("warnings do not refuse and do not change the text", warn.status === 200 && plain(obj(warn.json).warnings).includes("leverage"), plain(obj(warn.json).warnings));
}

/** B18: status rules. */
export async function statusRules(_ctx: Ctx, s: Scenario, p: Probe): Promise<void> {
  const link = "www.reddit.com/r/ExperiencedDevs/comments/1on3f8q/comment/mq2bZZ1/";
  const ok = await post(s.api, "/api/status", { key: K_POSTED, status: "posted", posted_url: link });
  p.equal("posted with a link answers the https link", [ok.status, obj(ok.json)], [200, { status: "posted", posted_url: `https://${link}` }]);
  p.expect("posted_today is 1", obj((await get(s.api, "/api/board")).json).posted_today === 1);
  const st = await post(s.api, "/api/status", { key: K_POSTED, status: "expired" });
  p.equal("expired cannot be set", [st.status, errOf(st)], [400, "STATUS must be one of drafted, posted, skipped"]);
  const http = await post(s.api, "/api/status", { key: K_POSTED, status: "posted", posted_url: "http://x.com/a" });
  p.equal("an http link is refused", [http.status, errOf(http)], [400, "the link must be one https:// address"]);
  const space = await post(s.api, "/api/status", { key: K_POSTED, status: "posted", posted_url: "https://x.com/a b" });
  p.expect("a link with whitespace is refused", space.status === 400, String(space.status));
  const unknown = await post(s.api, "/api/status", { key: "reddit:nope", status: "posted" });
  p.expect("an unknown key answers 404 and says unknown thread", unknown.status === 404 && /unknown thread/.test(errOf(unknown)), `${unknown.status} ${errOf(unknown)}`);
  p.expect("a refused change leaves the link as it was", str((await threadOf(s.api, K_POSTED)).posted_url) === `https://${link}`);
  await post(s.api, "/api/status", { key: K_POSTED, status: "drafted" });
  const re = await threadOf(s.api, K_POSTED);
  p.expect("Reopen clears posted_at and posted_url", !re.posted_at && !re.posted_url && re.status === "drafted", plain({ s: re.status, a: re.posted_at, u: re.posted_url }));
  const skip = await post(s.api, "/api/status", { key: K_SKIPPED, status: "skipped" });
  p.expect("Skip answers skipped and the thread is listed under skipped", skip.status === 200 && (await listOf(s.api, "skipped")).some((t) => t.key === K_SKIPPED));
  p.expect("posted_today counts only posted threads", obj((await get(s.api, "/api/board")).json).posted_today === 0);
}

/** B19: expired is derived (date before today minus 14 days), never stored; the clock is fixed to 2026-11-03. */
export async function expiry(ctx: Ctx, s: Scenario, p: Probe): Promise<void> {
  const edge = day(-14);
  const mk = (id: string, date: string) => variant(ctx, "https://www.reddit.com/r/agile/comments/1o8zw3d/", { url: `https://www.reddit.com/r/agile/comments/${id}/`, date, syften_urls: undefined });
  const a = await post(s.api, "/api/runs", { items: [mk("e2eb001", edge), mk("e2eb002", day(-15))] });
  p.expect("two threads dated 14 and 15 days ago are stored", a.status === 200, `${a.status} ${errOf(a)}`);
  const expired = (await listOf(s.api, "expired")).map((t) => str(t.key));
  const open = (await listOf(s.api, "open")).map((t) => str(t.key));
  p.expect("the thread of 15 days ago is expired and not open", expired.includes("reddit:e2eb002") && !open.includes("reddit:e2eb002"), expired.join(","));
  p.expect("the thread of exactly 14 days ago is still open", open.includes("reddit:e2eb001") && !expired.includes("reddit:e2eb001"));
  const old = ctx.synthetic.filter((i) => str(i.date) < day(-14) && i.url !== "https://www.reddit.com/r/agile/comments/1o8zw3d/").map((i) => str(i.url));
  const expUrls = (await listOf(s.api, "expired")).map((t) => str(t.url));
  p.expect(`the ${old.length} old drafted threads of the synthetic run are expired`, old.every((u) => expUrls.includes(u)), expUrls.length + " expired listed");
  const st = JSON.parse(fs.readFileSync(path.join(s.dataDir, "state.json"), "utf8")) as Obj;
  p.expect("expired is never stored (state.json keeps drafted)", obj(st["reddit:e2eb002"]).status === "drafted", str(obj(st["reddit:e2eb002"]).status));
  const key = "reddit:1o4kq7e";
  await post(s.api, "/api/status", { key, status: "posted" });
  p.expect("a posted old thread is posted, not expired", (await threadOf(s.api, key)).status === "posted");
  await post(s.api, "/api/status", { key, status: "drafted" });
  p.expect("Reopen of an old thread shows it as expired again", (await threadOf(s.api, key)).status === "expired");
}

/** B20: feedback is saved with a snapshot of the draft at that moment. */
export async function feedbackSaved(_ctx: Ctx, s: Scenario, p: Probe): Promise<void> {
  const text = "Too clever for a Show HN. Drop the hash idea.";
  const a = await post(s.api, "/api/feedback", { key: K_HN, text });
  const e = obj(a.json);
  p.expect("POST /api/feedback answers an open entry with an fb_ id", a.status === 200 && /^fb_[0-9a-f]{8}$/.test(str(e.id)) && e.text === text && e.status === "open" && e.resolution === "", `${a.status} ${a.text.slice(0, 160)}`);
  p.expect("created is an ISO time with an offset", /^\d{4}-\d{2}-\d{2}T[\d:.]+(Z|[+-]\d{2}:\d{2})$/.test(str(e.created)), str(e.created));
  const th = await threadOf(s.api, K_HN);
  const entry = arr(obj((await get(s.api, "/api/feedback")).json).entries).map(obj).find((x) => x.id === e.id);
  const snap = obj(entry?.snapshot);
  p.equal("the snapshot equals the stored thread (angle, draft, reply_to, mode, date)", snap, { angle: obj(th.summary).angle ?? "", draft: obj(th.reply).text, reply_to: obj(th.reply).to, mode: th.mode, date: th.date });
  const blank = await post(s.api, "/api/feedback", { key: K_HN, text: "   " });
  p.equal("blank text answers 400 empty feedback", [blank.status, errOf(blank)], [400, "empty feedback"]);
  const unknown = await post(s.api, "/api/feedback", { key: "hn:nope", text: "x" });
  p.expect("an unknown thread answers 404", unknown.status === 404, String(unknown.status));
  const padded = obj((await post(s.api, "/api/feedback", { key: K_HN, text: "  kept as written  " })).json);
  p.expect("the text is trimmed and otherwise kept as written", padded.text === "kept as written");
  p.expect("any number of entries per thread", arr(obj((await get(s.api, "/api/feedback")).json).entries).length === 2);
}

/** B21: the queue: open entries oldest first, resolve with a note. */
export async function feedbackQueue(_ctx: Ctx, s: Scenario, p: Probe): Promise<void> {
  const open = arr(obj((await get(s.api, "/api/feedback")).json).entries).map(obj);
  p.expect("GET /api/feedback lists only open entries, oldest first", open.length === 2 && open.every((x) => x.status === "open") && str(open[0].created) <= str(open[1].created), plain(open.map((x) => x.created)));
  const id = str(open[0].id);
  const r = await post(s.api, `/api/feedback/${id}/resolve`, { status: "applied", note: "Cut the last sentence." });
  const rj = obj(r.json);
  p.expect("resolve answers the entry applied with the note and resolved_at", r.status === 200 && rj.status === "applied" && rj.resolution === "Cut the last sentence." && str(rj.resolved_at) !== "", `${r.status} ${r.text.slice(0, 160)}`);
  p.expect("it leaves the default list and stays under status=all", !plain(obj((await get(s.api, "/api/feedback")).json)).includes(id) && plain(obj((await get(s.api, "/api/feedback?status=all")).json)).includes(id));
  const done = await post(s.api, `/api/feedback/${id}/resolve`, { status: "done", note: "x" });
  p.equal("status done answers 400", [done.status, errOf(done)], [400, "status must be applied or declined"]);
  const nope = await post(s.api, "/api/feedback/fb_nope/resolve", { status: "applied", note: "x" });
  p.equal("an unknown id answers 404", [nope.status, errOf(nope)], [404, "unknown feedback id fb_nope"]);
  const none = await post(s.api, `/api/feedback/${str(open[1].id)}/resolve`, { status: "applied" });
  p.equal("a resolve without a note answers 400", [none.status, errOf(none)], [400, "a note is required"]);
  const blank = await post(s.api, `/api/feedback/${str(open[1].id)}/resolve`, { status: "declined", note: "  " });
  p.expect("a blank note is refused too", blank.status === 400);
  const again = await post(s.api, `/api/feedback/${id}/resolve`, { status: "declined", note: "Changed my mind." });
  p.expect("a resolved entry can be resolved again (the note is replaced)", again.status === 200 && obj(again.json).resolution === "Changed my mind." && obj(again.json).status === "declined");
}

/** B23: lessons: one line per rule, no duplicates. */
export async function lessons(_ctx: Ctx, s: Scenario, p: Probe): Promise<void> {
  const id = str(obj(arr(obj((await get(s.api, "/api/feedback?status=all")).json).entries)[0]).id);
  const rule = "No rhetorical question at the end of a reply.";
  const a = await post(s.api, "/api/lessons", { rule, feedback_id: id });
  p.equal("a rule answers its line", [a.status, obj(a.json)], [200, { line: `- ${rule} (${id})` }]);
  p.expect("GET /api/lessons holds the line", arr(obj((await get(s.api, "/api/lessons")).json).lines).includes(`- ${rule} (${id})`));
  const dup = await post(s.api, "/api/lessons", { rule: "no rhetorical question at the end of a reply", feedback_id: id });
  p.equal("the same rule (case and final dot ignored) answers 409", [dup.status, errOf(dup)], [409, "this lesson is already in lessons.md"]);
  const unknown = await post(s.api, "/api/lessons", { rule: "Another rule.", feedback_id: "fb_nope" });
  p.expect("an unknown feedback id answers 404", unknown.status === 404, String(unknown.status));
  const empty = await post(s.api, "/api/lessons", { rule: "  ", feedback_id: id });
  p.equal("an empty rule answers 400 empty rule", [empty.status, errOf(empty)], [400, "empty rule"]);
}
