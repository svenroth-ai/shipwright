// The hard API checks (H06-H11, S07) against the built companion's documented JSON API (the fixture's brief.md
// "Companion API" glossary entry). Replaces the chat-command checks: the chat is the Claude app, not part of the app.
// Pure over a `call` function, so it is checkable without a browser. Callers pass loopback origins only.
import type { Checklist } from "./checklist.js";

export interface ApiAnswer {
  status: number;
  contentType: string;
  text: string;
  /** Parsed body, or undefined when the body is not JSON. */
  json: unknown;
}
export type Call = (method: string, path: string, body?: unknown) => Promise<ApiAnswer>;

export interface Exchange {
  label: string;
  method: string;
  path: string;
  answer: ApiAnswer | null;
  error: string | null;
}

/** Thread ids the later screens need: one posted, one drafted only, one untouched. */
export interface ThreadState {
  posted: number | null;
  drafted: number | null;
  fresh: number | null;
  titles: Record<number, string>;
  /** Threads per platform key as the API lists them, for the badge-per-thread check. */
  perPlatform: Record<string, number>;
}

export const KEYWORDS = ["onboarding", "pricing", "integrations"];

export type Obj = Record<string, unknown>;
export const obj = (v: unknown): Obj => (v && typeof v === "object" ? (v as Obj) : {});
export const errorText = (a: ApiAnswer | null): string => String(obj(a?.json).error ?? "");

/** Builds a `Call` over fetch for one loopback origin; the Origin header is the app's own, as a browser would send. */
export function httpCall(origin: string, doFetch: typeof fetch = fetch): Call {
  return async (method, path, body) => {
    const res = await doFetch(`${origin}${path}`, {
      method,
      headers: body === undefined ? { origin } : { origin, "content-type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
      redirect: "manual", // a model-built app must not lead the harness off loopback
      signal: AbortSignal.timeout(60_000),
    });
    const text = await res.text();
    let json: unknown;
    try {
      json = JSON.parse(text);
    } catch {
      json = undefined;
    }
    return { status: res.status, contentType: res.headers.get("content-type") ?? "", text, json };
  };
}

export async function runApiChecks(call: Call, checklist: Checklist): Promise<{ log: Exchange[]; state: ThreadState }> {
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

  // The Test phase may already have used the same dev data folder: note whether the board starts empty.
  const before = await ask("list before", "GET", "/api/threads");
  const beforeReadable = before?.status === 200 && Array.isArray(obj(before.json).threads);
  const existing = beforeReadable ? (obj(before?.json).threads as unknown[]).length : 0;
  const fetch1 = await ask("fetch", "POST", "/api/fetch", {});
  const fetch2 = await ask("fetch again", "POST", "/api/fetch", {});
  const added1 = Number(obj(fetch1?.json).added);
  const added2 = Number(obj(fetch2?.json).added);
  // The spec moves the Test phase's data folder aside first; a used folder cannot prove that fetch adds anything.
  set("H06", beforeReadable && fetch1?.status === 200 && fetch2?.status === 200 && existing === 0 && added1 > 0 && added2 === 0,
    `first: added ${added1} (${existing} threads existed before); second: added ${added2}${beforeReadable ? "" : "; the list before the fetch could not be read, freshness is unproven"}${existing > 0 ? "; the data folder was NOT fresh (a fetch on used data proves nothing)" : ""}`);

  const list = await ask("list", "GET", "/api/threads");
  const threads = (Array.isArray(obj(list?.json).threads) ? (obj(list?.json).threads as Obj[]) : []).sort((a, b) => Number(a.id) - Number(b.id));
  const ids = threads.map((t) => Number(t.id));
  const titles = Object.fromEntries(threads.map((t) => [Number(t.id), String(t.title)]));
  // Threads still "new" are the ones the draft/post sequence may use; earlier test data may have moved others on.
  const fresh = threads.filter((t) => t.status === "new").map((t) => Number(t.id));
  const [first, second, third] = [fresh[0] ?? ids[0] ?? 1, fresh[1] ?? ids[1] ?? 2, fresh[2] ?? ids[2] ?? 3];

  const show1 = await ask("show", "GET", `/api/threads/${first}`);
  const show99 = await ask("show unknown", "GET", "/api/threads/99");
  const enough = fresh.length >= 3;
  set("H07", enough && show1?.status === 200 && Number(obj(show1.json).id) === first && show99?.status === 404 && /There is no thread 99/.test(errorText(show99)),
    `${fresh.length} new threads; thread ${first}: ${show1?.status}; thread 99: ${show99?.status} "${errorText(show99)}"`);

  const draftA = await ask("draft", "POST", `/api/threads/${first}/draft`, {});
  const draftB = await ask("draft again", "POST", `/api/threads/${first}/draft`, {});
  const storedDraft = await ask("show drafted", "GET", `/api/threads/${first}`); // the change must be stored, not only echoed
  const textA = String(obj(draftA?.json).draft ?? "");
  set("H08", draftA?.status === 200 && obj(draftA.json).status === "drafted" && textA.length > 0 && textA === String(obj(draftB?.json).draft ?? "") &&
    obj(storedDraft?.json).status === "drafted" && String(obj(storedDraft?.json).draft ?? "") === textA,
    `draft stored: ${textA.length > 0}; same text twice: ${textA === String(obj(draftB?.json).draft ?? "")}`);

  const markNotDrafted = await ask("mark not drafted", "POST", `/api/threads/${second}/posted`, {});
  const stillNew = await ask("show not drafted", "GET", `/api/threads/${second}`);
  const markDrafted = await ask("mark drafted", "POST", `/api/threads/${first}/posted`, {});
  const storedPosted = await ask("show posted", "GET", `/api/threads/${first}`);
  const refused = !!markNotDrafted && markNotDrafted.status === 409 && errorText(markNotDrafted).length > 0;
  set("H09", markDrafted?.status === 200 && obj(markDrafted.json).status === "posted" && obj(storedPosted?.json).status === "posted" && refused && obj(stillNew?.json).status === "new",
    `drafted -> ${markDrafted?.status}; not drafted -> ${markNotDrafted?.status} "${errorText(markNotDrafted)}", status after: ${String(obj(stillNew?.json).status)}`);

  // Setup for the screens that follow: one drafted-only thread. Not a check of its own.
  await ask("draft for the tour", "POST", `/api/threads/${third}/draft`, {});

  const put = await ask("set keywords", "PUT", "/api/keywords", { keywords: KEYWORDS });
  const got = await ask("get keywords", "GET", "/api/keywords");
  const same = (a: ApiAnswer | null) => JSON.stringify((obj(a?.json).keywords as unknown[] | undefined)?.map((k) => String(k).toLowerCase()).sort()) === JSON.stringify([...KEYWORDS].sort());
  set("H10", put?.status === 200 && same(put) && same(got), `put: ${JSON.stringify(obj(put?.json).keywords)}; get: ${JSON.stringify(obj(got?.json).keywords)}`);

  const unknown = await ask("unknown route", "GET", "/api/no-such-route");
  set("S07", unknown?.status === 404 && /json/i.test(unknown.contentType) && errorText(unknown).length > 0,
    `GET /api/no-such-route -> ${unknown?.status} (${unknown?.contentType}) "${errorText(unknown)}"`);

  const answered = log.filter((e) => e.answer);
  const bad = answered.filter((e) => e.answer!.json === undefined || (e.answer!.status >= 400 && errorText(e.answer).length === 0));
  set("H11", answered.length === log.length && bad.length === 0,
    `${answered.length}/${log.length} answers; not JSON or error without text: ${bad.map((e) => `${e.method} ${e.path}`).join(", ") || "none"}`);

  const perPlatform: Record<string, number> = {};
  for (const t of threads) perPlatform[String(t.platform)] = (perPlatform[String(t.platform)] ?? 0) + 1;
  return { log, state: { posted: first, drafted: third, fresh: fresh[3] ?? second, titles, perPlatform } };
}
