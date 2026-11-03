// Raw HTTP client for the companion API. node:http (not fetch) so the Host and Origin headers can be set exactly as a test needs,
// and an oversized or malformed body can be sent as written. Loopback origins only: the callers pass the harness's own port.
import http from "node:http";

export interface Answer {
  status: number;
  headers: http.IncomingHttpHeaders;
  text: string;
  /** Parsed body, or undefined when the body is not JSON. */
  json: unknown;
}

export interface Req {
  method?: string;
  path: string;
  /** Sent as JSON. */
  body?: unknown;
  /** Sent as written (not JSON.stringify'd), for malformed and oversized bodies. */
  raw?: string;
  headers?: Record<string, string>;
  /** POST and PUT carry `X-Board: 1` unless this is false. */
  xBoard?: boolean;
  timeoutMs?: number;
}

export type Api = (req: Req) => Promise<Answer>;

export function apiFor(origin: string, sink?: (req: Req, answer: Answer) => void): Api {
  const url = new URL(origin);
  return (req) => new Promise<Answer>((resolve, reject) => {
    const method = req.method ?? (req.body !== undefined || req.raw !== undefined ? "POST" : "GET");
    const payload = req.raw ?? (req.body === undefined ? undefined : JSON.stringify(req.body));
    const headers: Record<string, string> = { ...(req.headers ?? {}) };
    if (payload !== undefined) {
      headers["Content-Type"] ??= "application/json";
      headers["Content-Length"] = String(Buffer.byteLength(payload));
    }
    if ((method === "POST" || method === "PUT") && req.xBoard !== false) headers["X-Board"] ??= "1";
    const r = http.request({ host: url.hostname, port: Number(url.port), method, path: req.path, headers, timeout: req.timeoutMs ?? 60_000 }, (res) => {
      const chunks: Buffer[] = [];
      res.on("data", (c: Buffer) => chunks.push(c));
      res.on("end", () => {
        const text = Buffer.concat(chunks).toString("utf8");
        let json: unknown;
        try {
          json = JSON.parse(text);
        } catch {
          json = undefined;
        }
        const answer: Answer = { status: res.statusCode ?? 0, headers: res.headers, text, json };
        sink?.(req, answer);
        resolve(answer);
      });
    });
    r.on("timeout", () => r.destroy(new Error(`timeout after ${req.timeoutMs ?? 60_000} ms: ${method} ${req.path}`)));
    r.on("error", reject);
    r.end(payload);
  });
}

export type Obj = Record<string, unknown>;
export const obj = (v: unknown): Obj => (v && typeof v === "object" && !Array.isArray(v) ? (v as Obj) : {});
export const arr = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
export const str = (v: unknown): string => (typeof v === "string" ? v : "");
export const errOf = (a: Answer): string => str(obj(a.json).error);

export const get = (api: Api, path: string, headers?: Record<string, string>) => api({ method: "GET", path, headers });
export const post = (api: Api, path: string, body: unknown) => api({ method: "POST", path, body });
export const put = (api: Api, path: string, body: unknown) => api({ method: "PUT", path, body });
