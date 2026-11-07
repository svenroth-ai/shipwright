// B06-B09, B24, B25: the companion API contract of brief.md "Serve the companion API": headers, local-only access, error
// answers, the read routes, the config and the link opener. Each function gets a fresh companion (see ctx.scenario).
import type { Scenario } from "./ctx.js";
import { arr, errOf, get, obj, post, put, str, type Answer } from "./http.js";
import type { Probe } from "./probe.js";

const JSON_TYPE = "application/json; charset=utf-8";
const READ_ROUTES = ["/api/health", "/api/version", "/api/board", "/api/threads", "/api/runs", "/api/feedback", "/api/lessons", "/api/config", "/api/events?after=0", "/api/nope"];

/** B06: JSON everywhere, no caching, nosniff, no CORS headers; the page itself is HTML. */
export async function headers(s: Scenario, p: Probe): Promise<void> {
  const bad: string[] = [];
  const answers: [string, Answer][] = [];
  for (const path of READ_ROUTES) answers.push([path, await get(s.api, path)]);
  answers.push(["POST /api/open", await post(s.api, "/api/open", { url: "x" })]);
  for (const [path, a] of answers) {
    if (a.headers["content-type"] !== JSON_TYPE) bad.push(`${path} content-type ${String(a.headers["content-type"])}`);
    if (!String(a.headers["cache-control"] ?? "").includes("no-store")) bad.push(`${path} cache-control`);
    if (a.headers["x-content-type-options"] !== "nosniff") bad.push(`${path} nosniff`);
    if (Object.keys(a.headers).some((h) => h.startsWith("access-control-"))) bad.push(`${path} CORS header`);
    if (a.json === undefined) bad.push(`${path} not JSON`);
  }
  p.expect(`all ${answers.length} API answers are JSON (utf-8), no-store, nosniff and carry no CORS header`, bad.length === 0, bad.slice(0, 4).join("; "));
  const page = await get(s.api, "/");
  p.expect("GET / serves the board page as text/html", page.status === 200 && String(page.headers["content-type"]).startsWith("text/html") && /<html/i.test(page.text), `${page.status} ${String(page.headers["content-type"])}`);
  p.expect("the page also carries no-store and nosniff", String(page.headers["cache-control"]).includes("no-store") && page.headers["x-content-type-options"] === "nosniff");
  for (const f of ["/board.css", "/board.js"]) p.expect(`${f} is served`, (await get(s.api, f)).status === 200);
  p.expect("an unknown static file answers 404", (await get(s.api, "/board.nope")).status === 404);
  const pre = await s.api({ method: "OPTIONS", path: "/api/status", headers: { Origin: "http://evil.example", "Access-Control-Request-Method": "POST" } });
  p.expect("a cross-site preflight is not granted", !pre.headers["access-control-allow-origin"], `status ${pre.status}`);
}

/** B07: only the local machine and the board's own header may read or write. */
export async function localAccess(s: Scenario, p: Probe): Promise<void> {
  const evil = await get(s.api, "/api/version", { Host: "evil.example" });
  p.equal("a foreign Host is refused with 403 local access only", [evil.status, obj(evil.json)], [403, { error: "local access only" }]);
  const page = await get(s.api, "/", { Host: "evil.example" });
  p.expect("the page is refused for a foreign Host too", page.status === 403, String(page.status));
  const local = await get(s.api, "/api/version", { Host: `localhost:${s.c.port}` });
  p.expect("the Host localhost is accepted", local.status === 200, String(local.status));
  const noHeader = await s.api({ method: "POST", path: "/api/status", body: { key: "x", status: "drafted" }, xBoard: false });
  p.equal("a POST without X-Board: 1 is refused with 403 local board only", [noHeader.status, obj(noHeader.json)], [403, { error: "local board only" }]);
  const noPut = await s.api({ method: "PUT", path: "/api/config", body: { mode: "light" }, xBoard: false });
  p.expect("a PUT without X-Board: 1 is refused too", noPut.status === 403, String(noPut.status));
  const foreign = await s.api({ method: "POST", path: "/api/status", body: { key: "x", status: "drafted" }, headers: { Origin: "http://evil.example" } });
  p.expect("a foreign Origin is refused", foreign.status === 403, String(foreign.status));
  const own = await s.api({ method: "POST", path: "/api/status", body: { key: "reddit:nope", status: "drafted" }, headers: { Origin: `http://127.0.0.1:${s.c.port}` } });
  p.expect("the board's own Origin passes the gate (the unknown thread is a 404)", own.status === 404, String(own.status));
}

/** B08: unknown route, unreadable body, too large a body. */
export async function badRequests(s: Scenario, p: Probe): Promise<void> {
  const nope = await get(s.api, "/api/nope");
  p.equal("an unknown route answers 404 {error: not found}", [nope.status, obj(nope.json)], [404, { error: "not found" }]);
  const bad = await s.api({ method: "POST", path: "/api/feedback", raw: "{not json" });
  p.expect("a body that is not JSON answers 400 with an error text", bad.status === 400 && errOf(bad) !== "", `${bad.status} ${bad.text.slice(0, 80)}`);
  const big = await post(s.api, "/api/feedback", { key: "x", text: "a".repeat(20_100) });
  p.equal("a body over 20000 bytes answers 413 too large", [big.status, obj(big.json)], [413, { error: "too large" }]);
  const run = await post(s.api, "/api/runs/check", { items: [], pad: "a".repeat(30_000) });
  p.expect("POST /api/runs/check accepts a body over 20000 bytes (limit 2 MB)", run.status !== 413, String(run.status));
}

/** B09: the read routes on a fresh data folder and their error texts. */
export async function readRoutes(s: Scenario, p: Probe): Promise<void> {
  const v1 = obj((await get(s.api, "/api/version")).json).v;
  p.expect("/api/version answers a string", typeof v1 === "string" && v1 !== "");
  const board = obj((await get(s.api, "/api/board")).json);
  p.expect("/api/board has title, sub, mode, posted_today, daily_cap 5 and items", ["title", "sub", "mode", "posted_today", "daily_cap", "items"].every((k) => k in board) && board.daily_cap === 5 && arr(board.items).length === 0, Object.keys(board).join(","));
  p.equal("/api/threads answers an empty list", obj((await get(s.api, "/api/threads")).json), { threads: [] });
  const st = await get(s.api, "/api/threads?status=x");
  p.equal("an unknown status answers 400 unknown status x", [st.status, errOf(st)], [400, "unknown status x"]);
  const pl = await get(s.api, "/api/threads?platform=bluesky");
  p.equal("an unknown platform answers 400 unknown platform bluesky", [pl.status, errOf(pl)], [400, "unknown platform bluesky"]);
  const t = await get(s.api, `/api/threads/${encodeURIComponent("reddit:nope")}`);
  p.equal("an unknown thread answers 404 unknown thread reddit:nope", [t.status, errOf(t)], [404, "unknown thread reddit:nope"]);
  p.equal("/api/runs answers an empty list", obj((await get(s.api, "/api/runs")).json), { runs: [] });
  const les = obj((await get(s.api, "/api/lessons")).json);
  p.expect("/api/lessons answers text and lines", "text" in les && Array.isArray(les.lines));
  p.equal("/api/feedback answers an empty queue", obj((await get(s.api, "/api/feedback")).json), { entries: [] });
  const fb = await get(s.api, "/api/feedback?status=x");
  p.expect("an unknown feedback status answers 400", fb.status === 400 && errOf(fb) !== "", String(fb.status));
  const ev = await get(s.api, "/api/events?after=x");
  p.equal("a bad after answers 400 after must be a number", [ev.status, errOf(ev)], [400, "after must be a number"]);
  const unseen = await post(s.api, "/api/threads/unseen", {});
  p.equal("unseen without urls or items answers 400 give urls or items", [unseen.status, errOf(unseen)], [400, "give urls or items"]);
  await put(s.api, "/api/config", { mode: "light" });
  p.expect("/api/version changes after a write", obj((await get(s.api, "/api/version")).json).v !== v1);
}

/** B24: the posting mode and handles; strict keys; nothing written on a refusal. */
export async function config(s: Scenario, p: Probe): Promise<void> {
  p.equal("a fresh data folder answers configured false", obj((await get(s.api, "/api/config")).json), { configured: false });
  const ok = await put(s.api, "/api/config", { mode: "light", reddit: "synthetic_handle" });
  p.expect("PUT answers the merged config with configured true", ok.status === 200 && obj(ok.json).mode === "light" && obj(ok.json).reddit === "synthetic_handle" && obj(ok.json).configured === true, ok.text.slice(0, 120));
  const before = (await get(s.api, "/api/config")).text;
  const loud = await put(s.api, "/api/config", { mode: "loud" });
  p.equal("mode loud answers 400 mode must be one of expertise, light, open", [loud.status, errOf(loud)], [400, "mode must be one of expertise, light, open"]);
  const colour = await put(s.api, "/api/config", { colour: "red" });
  p.equal("an unknown key answers 400 unknown setting colour", [colour.status, errOf(colour)], [400, "unknown setting colour"]);
  const mixed = await put(s.api, "/api/config", { hn: "should_not_stick", colour: "red" });
  p.expect("a refused change writes nothing", (await get(s.api, "/api/config")).text === before && mixed.status === 400);
  const merged = await put(s.api, "/api/config", { hn: "hn_handle" });
  p.expect("a later change keeps the earlier keys", obj(merged.json).mode === "light" && obj(merged.json).hn === "hn_handle");
}

/** B25: the link opener refuses everything but https links to the five platforms. Opening a good link would start the OS browser, so it is not tried. */
export async function openRefusals(s: Scenario, p: Probe): Promise<void> {
  const text = "only https links to Reddit, Hacker News, LinkedIn (also lnkd.in) or X";
  for (const url of ["http://www.reddit.com/r/a/comments/b/", "https://evil.example/x", "https://www.reddit.com/a\"b", "https://www.reddit.com/a b", "javascript:alert(1)", "https://news.ycombinator.com/<x>"]) {
    const a = await post(s.api, "/api/open", { url });
    p.equal(`${url} is refused`, [a.status, errOf(a)], [400, text]);
  }
  p.expect("the error texts are plain strings", str(errOf(await post(s.api, "/api/open", {}))) !== "");
}
