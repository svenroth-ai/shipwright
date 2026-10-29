// The hard API checks of the real-skill variant (H06-H11, H14, S07) against the built companion's documented JSON API
// (the fixture's brief.md "Companion API" glossary entry). Same shape as board-api.ts; the routes differ: threads carry
// a summary and comments, there is feedback, a skipped status and sources instead of keywords.
import { errorText, obj, type ApiAnswer, type Call, type Exchange, type Obj, type ThreadState } from "./board-api.js";
import type { Checklist } from "./checklist.js";

export const SOURCES = [
  { kind: "syften", query: "shipwright", status: "active" },
  { kind: "linkedin", query: "ai coding agent", status: "active" },
];

export interface RealThreadState extends ThreadState {
  /** Platform key (`reddit`, ...) per thread id: the board shows a thread only under its platform. */
  platformOf: Record<number, string>;
}

export async function runRealApiChecks(call: Call, checklist: Checklist): Promise<{ log: Exchange[]; state: RealThreadState }> {
  const log: Exchange[] = [];
  const ask = async (label: string, method: string, path: string, body?: unknown): Promise<ApiAnswer | null> => {
    try {
      const answer = await call(method, path, body);
      log.push({ label, method, path, answer, error: null });
      return answer;
    } catch (error) {
      log.push({ label, method, path, answer: null, error: (error as Error).message });
      return null;
    }
  };
  const set = (id: string, ok: boolean, evidence: string) => checklist.record(id, ok ? "pass" : "fail", evidence);
  const listOf = (a: ApiAnswer | null): Obj[] => (Array.isArray(obj(a?.json).threads) ? (obj(a?.json).threads as Obj[]) : []);

  const before = await ask("list before", "GET", "/api/threads");
  const beforeReadable = before?.status === 200 && Array.isArray(obj(before.json).threads);
  const existing = listOf(before).length;
  const fetch1 = await ask("fetch", "POST", "/api/fetch", {});
  const fetch2 = await ask("fetch again", "POST", "/api/fetch", {});
  const added1 = Number(obj(fetch1?.json).added);
  const added2 = Number(obj(fetch2?.json).added);
  set("H06", beforeReadable && fetch1?.status === 200 && fetch2?.status === 200 && existing === 0 && added1 > 0 && added2 === 0,
    `first: added ${added1} (${existing} threads existed before); second: added ${added2}${beforeReadable ? "" : "; the list before the fetch could not be read, freshness is unproven"}${existing > 0 ? "; the data folder was NOT fresh" : ""}`);

  const threads = listOf(await ask("list", "GET", "/api/threads")).sort((a, b) => Number(a.id) - Number(b.id));
  const titles = Object.fromEntries(threads.map((t) => [Number(t.id), String(t.title)]));
  const platformOf = Object.fromEntries(threads.map((t) => [Number(t.id), String(t.platform)]));
  // Only "new" threads can be drafted; expired ones show the derived status and are not usable. Four are needed (draft+post, skip, drafted-only, untouched).
  const fresh = threads.filter((t) => t.status === "new").map((t) => Number(t.id));
  const [first, second, third] = [fresh[0] ?? 1, fresh[1] ?? 2, fresh[2] ?? 3];

  const show1 = await ask("show", "GET", `/api/threads/${first}`);
  const show99 = await ask("show unknown", "GET", "/api/threads/99");
  const summary = obj(obj(show1?.json).summary);
  const hasSummary = ["question", "others", "angle"].every((k) => typeof summary[k] === "string" && String(summary[k]).length > 0);
  const comments = obj(show1?.json).comments;
  set("H07", fresh.length >= 4 && show1?.status === 200 && Number(obj(show1.json).id) === first && hasSummary && Array.isArray(comments) &&
    show99?.status === 404 && /There is no thread 99/.test(errorText(show99)),
    `${fresh.length} new threads; thread ${first}: ${show1?.status}, summary ${hasSummary}, comments ${Array.isArray(comments) ? (comments as unknown[]).length : "missing"}; thread 99: ${show99?.status} "${errorText(show99)}"`);

  const draftA = await ask("draft", "POST", `/api/threads/${first}/draft`, {});
  const draftB = await ask("draft again", "POST", `/api/threads/${first}/draft`, {});
  const stored = await ask("show drafted", "GET", `/api/threads/${first}`);
  const textA = String(obj(draftA?.json).draft ?? "");
  set("H08", draftA?.status === 200 && obj(draftA.json).status === "drafted" && textA.length > 0 && textA === String(obj(draftB?.json).draft ?? "") &&
    obj(stored?.json).status === "drafted" && String(obj(stored?.json).draft ?? "") === textA,
    `draft stored: ${textA.length > 0}; same text twice: ${textA === String(obj(draftB?.json).draft ?? "")}`);

  const note = "shorter, no greeting";
  const fbOk = await ask("feedback", "PUT", `/api/threads/${first}/feedback`, { feedback: note });
  const fbStored = await ask("show feedback", "GET", `/api/threads/${first}`);
  const fbRefused = await ask("feedback on a thread that is not drafted", "PUT", `/api/threads/${second}/feedback`, { feedback: note });
  set("H14", fbOk?.status === 200 && String(obj(fbStored?.json).feedback ?? "") === note && fbRefused?.status === 409 && errorText(fbRefused).length > 0,
    `stored: ${String(obj(fbStored?.json).feedback ?? "")}; on a new thread -> ${fbRefused?.status} "${errorText(fbRefused)}"`);

  const markNew = await ask("mark not drafted", "POST", `/api/threads/${second}/posted`, {});
  const stillNew = await ask("show not drafted", "GET", `/api/threads/${second}`);
  const markDrafted = await ask("mark drafted", "POST", `/api/threads/${first}/posted`, {});
  const posted = await ask("show posted", "GET", `/api/threads/${first}`);
  const skip = await ask("skip", "POST", `/api/threads/${second}/skipped`, {});
  const skippedList = await ask("list skipped", "GET", "/api/threads?status=skipped");
  const refused = !!markNew && markNew.status === 409 && errorText(markNew).length > 0;
  set("H09", markDrafted?.status === 200 && obj(markDrafted.json).status === "posted" && obj(posted?.json).status === "posted" && refused && obj(stillNew?.json).status === "new" &&
    skip?.status === 200 && obj(skip.json).status === "skipped" && listOf(skippedList).some((t) => Number(t.id) === second),
    `drafted -> ${markDrafted?.status}; not drafted -> ${markNew?.status} "${errorText(markNew)}", status after: ${String(obj(stillNew?.json).status)}; skip -> ${skip?.status}; skipped list has it: ${listOf(skippedList).some((t) => Number(t.id) === second)}`);

  await ask("draft for the tour", "POST", `/api/threads/${third}/draft`, {}); // setup for the screens, not a check

  const put = await ask("set sources", "PUT", "/api/sources", { sources: SOURCES });
  const got = await ask("get sources", "GET", "/api/sources");
  const bad = await ask("bad source kind", "PUT", "/api/sources", { sources: [{ kind: "carrier-pigeon", query: "x", status: "active" }] });
  const same = (a: ApiAnswer | null) => JSON.stringify(((obj(a?.json).sources as Obj[] | undefined) ?? []).map((s) => [s.kind, s.query, s.status])) === JSON.stringify(SOURCES.map((s) => [s.kind, s.query, s.status]));
  set("H10", put?.status === 200 && same(put) && same(got) && bad?.status === 400 && errorText(bad).length > 0,
    `put -> ${put?.status}; get matches: ${same(got)}; bad kind -> ${bad?.status} "${errorText(bad)}"`);

  const unknown = await ask("unknown route", "GET", "/api/no-such-route");
  set("S07", unknown?.status === 404 && /json/i.test(unknown.contentType) && errorText(unknown).length > 0,
    `GET /api/no-such-route -> ${unknown?.status} (${unknown?.contentType}) "${errorText(unknown)}"`);

  const answered = log.filter((e) => e.answer);
  const broken = answered.filter((e) => e.answer!.json === undefined || (e.answer!.status >= 400 && errorText(e.answer).length === 0));
  set("H11", answered.length === log.length && broken.length === 0,
    `${answered.length}/${log.length} answers; not JSON or error without text: ${broken.map((e) => `${e.method} ${e.path}`).join(", ") || "none"}`);

  const perPlatform: Record<string, number> = {};
  for (const t of threads) perPlatform[String(t.platform)] = (perPlatform[String(t.platform)] ?? 0) + 1;
  return { log, state: { posted: first, drafted: third, fresh: fresh[3] ?? second, titles, perPlatform, platformOf } };
}
