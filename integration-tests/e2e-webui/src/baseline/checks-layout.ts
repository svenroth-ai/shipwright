// B22 (events stream), B26 (data folder files and layout), B28 (a corrupt data file is reported and never overwritten).
import fs from "node:fs";
import path from "node:path";
import { scenario, type Ctx, type Scenario } from "./ctx.js";
import { K_HN, K_POSTED } from "./checks-runs.js";
import { arr, errOf, get, obj, post, put, str, type Obj } from "./http.js";
import type { Probe } from "./probe.js";

const readJson = (file: string): unknown => { try { return JSON.parse(fs.readFileSync(file, "utf8")); } catch { return undefined; } };
const names = (dir: string): string[] => { try { return fs.readdirSync(dir); } catch { return []; } };
const allFiles = (dir: string, rel = ""): string[] => names(path.join(dir, rel)).flatMap((n) => {
  const r = rel ? `${rel}/${n}` : n;
  return fs.statSync(path.join(dir, r)).isDirectory() ? allFiles(dir, r) : [r];
});

/** One short story on a fresh folder (config, synthetic run, one feedback, one status change, one lesson); B22 and B26 read it. */
export async function eventsAndLayout(ctx: Ctx, s: Scenario, events: Probe, layout: Probe): Promise<void> {
  await put(s.api, "/api/config", { mode: "expertise" });
  const run = await post(s.api, "/api/runs", { items: ctx.synthetic });
  const fb = await post(s.api, "/api/feedback", { key: K_HN, text: "Too clever for a Show HN. Drop the hash idea." });
  const link = "https://www.reddit.com/r/ExperiencedDevs/comments/1on3f8q/comment/mq2bZZ1/";
  await post(s.api, "/api/status", { key: K_POSTED, status: "posted", posted_url: link });
  await post(s.api, "/api/lessons", { rule: "No rhetorical question at the end of a reply.", feedback_id: str(obj(fb.json).id) });
  p0(events, run.status === 200 && fb.status === 200, "the story could not be set up");

  const e0 = obj((await get(s.api, "/api/events?after=0")).json);
  const list = arr(e0.events).map(obj);
  events.expect("after=0 answers two events and next 2", list.length === 2 && e0.next === 2, `${list.length} events, next ${String(e0.next)}`);
  events.expect("event 1 is the feedback with its key and text", list[0]?.seq === 1 && list[0]?.kind === "feedback" && list[0]?.key === K_HN && list[0]?.text === "Too clever for a Show HN. Drop the hash idea.", JSON.stringify(list[0]));
  events.expect("event 2 is the status change with status and posted_url", list[1]?.seq === 2 && list[1]?.kind === "status" && list[1]?.key === K_POSTED && list[1]?.status === "posted" && list[1]?.posted_url === link, JSON.stringify(list[1]));
  events.expect("every event has an at time", list.every((e) => str(e.at) !== ""));
  const e2 = obj((await get(s.api, "/api/events?after=2")).json);
  events.expect("after=2 answers no events", arr(e2.events).length === 0 && e2.next === 2, JSON.stringify(e2));
  events.expect("after=1 answers only event 2", arr(obj((await get(s.api, "/api/events?after=1")).json).events).length === 1);
  const lines = (() => { try { return fs.readFileSync(path.join(s.dataDir, "events.jsonl"), "utf8").split(/\r?\n/).filter(Boolean); } catch { return []; } })();
  events.expect("events.jsonl holds the two events", lines.length === 2 && lines.every((l) => { try { JSON.parse(l); return true; } catch { return false; } }), `${lines.length} lines`);

  const d = s.dataDir;
  const data = obj(readJson(path.join(d, "data.json")));
  layout.expect("data.json is {title, items} with 11 items", "title" in data && arr(data.items).length === 11, `keys ${Object.keys(data).join(",")}, ${arr(data.items).length} items`);
  const state = obj(readJson(path.join(d, "state.json")));
  const entries = Object.entries(state).map(([k, v]) => [k, obj(v)] as [string, Obj]);
  layout.expect("state.json is keyed by thread key, 11 entries with status, url, date, platform and aliases", entries.length === 11 && entries.every(([, v]) => ["status", "url", "date", "platform", "aliases"].every((f) => f in v)), `${entries.length} entries`);
  layout.expect("the posted entry carries posted_at and posted_url", obj(state[K_POSTED]).posted_at !== undefined && obj(state[K_POSTED]).posted_url === link, JSON.stringify(state[K_POSTED]));
  layout.expect("feedback.json is {entries}", arr(obj(readJson(path.join(d, "feedback.json"))).entries).length === 1);
  layout.expect("config.json is an object holding the mode", obj(readJson(path.join(d, "config.json"))).mode === "expertise");
  layout.expect("lessons.md holds the lesson line", /No rhetorical question at the end of a reply\. \(fb_[0-9a-f]{8}\)/.test((() => { try { return fs.readFileSync(path.join(d, "lessons.md"), "utf8"); } catch { return ""; } })()));
  const runs = names(path.join(d, "runs"));
  layout.expect("runs/ holds one <YYYYMMDD-HHMMSS>.json", runs.length === 1 && /^\d{8}-\d{6}\.json$/.test(runs[0]) && runs[0] === `${str(obj(run.json).run_id)}.json`, runs.join(","));
  const tmp = allFiles(d).filter((f) => /\.tmp$|\.tmp\.|^tmp/i.test(path.basename(f)));
  layout.expect("no .tmp file is left behind", tmp.length === 0, tmp.join(","));
}

function p0(p: Probe, ok: boolean, why: string): void {
  p.expect("the story ran (config, run, feedback, status, lesson)", ok, why);
}

/** B28: a data file that is not valid JSON gives a 500 naming it, and is not overwritten by the next write. */
export async function corruptFile(ctx: Ctx, p: Probe): Promise<void> {
  await scenario(ctx, "corrupt", { today: true }, async (s) => {
    await post(s.api, "/api/runs", { items: [ctx.synthetic[0]] });
    const file = path.join(s.dataDir, "data.json");
    const junk = "{ this is not json";
    fs.writeFileSync(file, junk);
    const r = await get(s.api, "/api/board");
    p.expect("reading answers 500 data file data.json is not valid JSON", r.status === 500 && errOf(r) === "data file data.json is not valid JSON", `${r.status} ${errOf(r)}`);
    const w = await post(s.api, "/api/runs", { items: [ctx.synthetic[1]] });
    p.expect("a write does not succeed on top of it", w.status === 500, String(w.status));
    p.expect("the corrupt file is left exactly as it was", fs.readFileSync(file, "utf8") === junk);
  });
}
