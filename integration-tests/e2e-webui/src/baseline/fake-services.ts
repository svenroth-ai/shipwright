// Local fake of Syften, Apify and the Hacker News Algolia API: replays the package's recorded answers
// (`seed/recorded/index.json` maps a request to a file). One server on 127.0.0.1 and a free port, one path prefix per service,
// so the three base-URL variables of the companion point at it. Records every request the companion makes.
import fs from "node:fs";
import http from "node:http";
import type { AddressInfo } from "node:net";
import path from "node:path";

export type ServiceName = "syften" | "apify" | "hn_algolia";
export interface Route { service: string; method: string; path: string; when?: string; status: number; file: string }
export interface Index { recorded_at: string; routes: Route[] }
export interface Seen { service: ServiceName; method: string; url: string; headers: Record<string, string | string[] | undefined>; body: string }

/** The path prefix each service lives under on the fake; the recorded routes are relative to it. */
export const PREFIX: Record<ServiceName, string> = { syften: "/syften", apify: "/apify/v2", hn_algolia: "/hn/api/v1" };

export const loadIndex = (recordedDir: string): Index => JSON.parse(fs.readFileSync(path.join(recordedDir, "index.json"), "utf8")) as Index;

/** Whether a route's `when` sentence (as written in index.json) holds for this request. No `when` always holds. */
export function whenHolds(when: string | undefined, body: Record<string, unknown>, query: URLSearchParams): boolean {
  if (!when) return true;
  if (/no 'before'/.test(when)) return body.before === undefined;
  if (/has 'before'/.test(when)) return body.before !== undefined;
  const url = /postUrls\[0\]\.url contains '([^']+)'/.exec(when);
  if (url) {
    const first = (body.postUrls as { url?: unknown }[] | undefined)?.[0]?.url;
    return typeof first === "string" && first.includes(url[1]);
  }
  const offset = /query offset=(\d+)/.exec(when);
  if (offset) return Number(query.get("offset") ?? "0") === Number(offset[1]);
  return /any other/.test(when); // the catch-all is listed last, so every earlier route has been tried
}

export function pickRoute(index: Index, service: ServiceName, method: string, pathname: string, body: Record<string, unknown>, query: URLSearchParams): Route | null {
  return index.routes.find((r) => r.service === service && r.method === method && r.path === pathname && whenHolds(r.when, body, query)) ?? null;
}

export interface Fake {
  port: number;
  /** The three base-URL variables, in the form the companion documents (Syften with a trailing slash, the others without). */
  env: { SYFTEN_BASE_URL: string; APIFY_BASE_URL: string; HN_ALGOLIA_BASE_URL: string };
  seen: Seen[];
  /** Requests no recorded route answered (the companion asked for something the package never recorded). */
  unmatched: string[];
  /** While set, every call of that service answers this HTTP status instead of the recording. */
  fail: Partial<Record<ServiceName, number>>;
  stop(): Promise<void>;
}

export async function startFakeServices(recordedDir: string): Promise<Fake> {
  const index = loadIndex(recordedDir);
  const seen: Seen[] = [];
  const unmatched: string[] = [];
  const fail: Partial<Record<ServiceName, number>> = {};
  const send = (res: http.ServerResponse, status: number, text: string) => {
    res.writeHead(status, { "content-type": "application/json" });
    res.end(text);
  };
  const server = http.createServer((req, res) => {
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(c));
    req.on("end", () => {
      const url = new URL(req.url ?? "/", "http://127.0.0.1");
      const service = (Object.keys(PREFIX) as ServiceName[]).find((s) => url.pathname.startsWith(`${PREFIX[s]}/`));
      const text = Buffer.concat(chunks).toString("utf8");
      if (!service) return send(res, 404, '{"error":"unknown service prefix"}');
      seen.push({ service, method: req.method ?? "GET", url: req.url ?? "", headers: req.headers, body: text });
      const forced = fail[service];
      if (forced) return send(res, forced, JSON.stringify({ error: "synthetic failure" }));
      const auth = String(req.headers.authorization ?? "");
      if (service !== "hn_algolia" && !/^Bearer\s+\S+/.test(auth)) return send(res, 401, '{"error":"unauthorized"}');
      let body: Record<string, unknown> = {};
      try {
        body = text ? (JSON.parse(text) as Record<string, unknown>) : {};
      } catch {
        body = {};
      }
      const rel = url.pathname.slice(PREFIX[service].length);
      const route = pickRoute(index, service, req.method ?? "GET", rel, body, url.searchParams);
      // The recording holds the first dataset page only; any later page is empty, so a paging loop ends.
      if (!route && /^\/datasets\/[^/]+\/items$/.test(rel)) return send(res, 200, "[]");
      if (!route) {
        unmatched.push(`${req.method} ${req.url}`);
        return send(res, 404, '{"error":"no recorded answer"}');
      }
      send(res, route.status, fs.readFileSync(path.join(recordedDir, route.file), "utf8"));
    });
  });
  await new Promise<void>((resolve, reject) => server.once("error", reject).listen(0, "127.0.0.1", resolve));
  const port = (server.address() as AddressInfo).port;
  const root = `http://127.0.0.1:${port}`;
  return {
    port, seen, unmatched, fail,
    env: { SYFTEN_BASE_URL: `${root}${PREFIX.syften}/`, APIFY_BASE_URL: `${root}${PREFIX.apify}`, HN_ALGOLIA_BASE_URL: `${root}${PREFIX.hn_algolia}` },
    stop: () => new Promise<void>((resolve) => { server.closeAllConnections?.(); server.close(() => resolve()); }),
  };
}
