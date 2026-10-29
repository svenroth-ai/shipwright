// A faithful stand-in for the built companion: serves the board page and the JSON API of the fixture's brief.md
// ("Companion API"), so the harness adapters (HTTP calls, browser snapshot) run end to end without a model.
// `flaws` switch off one behaviour at a time to prove each hard check can fail.
import http from "node:http";

export interface Flaws {
  repeatFetchAdds?: boolean;
  postedWithoutDraft?: boolean;
  htmlNotFound?: boolean;
  chatBox?: boolean;
  wrongAccent?: boolean;
  plainBadge?: boolean;
  noPersist?: boolean;
}

const PLATFORMS = ["reddit", "hackernews", "linkedin"];
const LABEL: Record<string, string> = { reddit: "Reddit", hackernews: "Hacker News", linkedin: "LinkedIn" };

interface Thread { id: number; platform: string; title: string; author: string; text: string; url: string; status: string; draft: string | null }

export interface Stub {
  origin: string;
  close(): Promise<void>;
}

export function boardPage(threads: Thread[], flaws: Flaws): string {
  const cards = threads.map((t) => `<div class="card" data-platform="${t.platform}"${t.platform === "reddit" ? "" : ' hidden'}><strong>${t.title}</strong> ` +
    `<span class="${flaws.plainBadge ? "tag" : "badge"}">${t.status}</span></div>`).join("");
  const tabs = PLATFORMS.map((p, i) => `<button role="tab" data-p="${p}"${i === 0 ? ' aria-selected="true"' : ""}>${LABEL[p]}</button>`).join("");
  return `<!doctype html><html><head><meta charset="utf-8"><title>Board</title><style>:root{--color-bg:#f6f7f9;--color-primary:${flaws.wrongAccent ? "#ff0000" : "#2563EB"};--font-size-base:16px}</style></head>` +
    `<body><div role="tablist">${tabs}</div>${flaws.chatBox ? '<input type="text" placeholder="Type a message">' : ""}<main>${cards}</main>` +
    `<script>document.querySelectorAll('[role=tab]').forEach(b=>b.onclick=()=>{document.querySelectorAll('.card').forEach(c=>c.hidden=c.dataset.platform!==b.dataset.p)})</script></body></html>`;
}

export async function startStub(flaws: Flaws = {}, withThreads = true): Promise<Stub> {
  const threads: Thread[] = [];
  let keywords: string[] = [];
  const seed: Thread[] = Array.from({ length: 9 }, (_, i) => ({
    id: i + 1, platform: PLATFORMS[i % 3], title: `Thread ${i + 1}`, author: `u${i}`, text: "t", url: "http://127.0.0.1/x", status: "new", draft: null,
  }));
  if (withThreads) threads.push(...seed.map((t) => ({ ...t })));
  const send = (res: http.ServerResponse, status: number, body: unknown) => {
    res.writeHead(status, { "content-type": "application/json" });
    res.end(JSON.stringify(body));
  };
  const server = http.createServer((req, res) => {
    const url = new URL(req.url ?? "/", "http://127.0.0.1");
    const chunks: Buffer[] = [];
    req.on("data", (c: Buffer) => chunks.push(c));
    req.on("end", () => {
      const body = chunks.length ? (JSON.parse(Buffer.concat(chunks).toString("utf8")) as Record<string, unknown>) : {};
      const m = /^\/api\/threads\/(\d+)(?:\/(draft|posted))?$/.exec(url.pathname);
      if (req.method === "GET" && url.pathname === "/") {
        res.writeHead(200, { "content-type": "text/html" });
        return void res.end(boardPage(threads, flaws));
      }
      if (url.pathname === "/api/redirect") {
        res.writeHead(302, { location: "http://example.invalid/elsewhere" });
        return void res.end();
      }
      if (url.pathname === "/api/health") return send(res, 200, { status: "ok" });
      if (req.method === "POST" && url.pathname === "/api/fetch") {
        const fresh = seed.filter((s) => !threads.some((t) => t.id === s.id));
        threads.push(...fresh.map((t) => ({ ...t })));
        return send(res, 200, { added: fresh.length + (flaws.repeatFetchAdds && fresh.length === 0 ? 1 : 0) });
      }
      if (req.method === "GET" && url.pathname === "/api/threads") return send(res, 200, { threads });
      if (m) {
        const t = threads.find((x) => x.id === Number(m[1]));
        if (!t) return send(res, 404, { error: `There is no thread ${m[1]}` });
        if (!m[2]) return send(res, 200, t);
        if (m[2] === "draft" && flaws.noPersist) return send(res, 200, { ...t, draft: "echo only", status: "drafted" });
        if (m[2] === "draft") {
          t.draft = `Hi ${t.author}, thanks for "${t.title}".`;
          t.status = "drafted";
          return send(res, 200, t);
        }
        if (t.status !== "drafted" && !flaws.postedWithoutDraft) return send(res, 409, { error: "Only a drafted thread can be marked as posted" });
        t.status = "posted";
        return send(res, 200, t);
      }
      if (url.pathname === "/api/keywords") {
        if (req.method === "PUT") keywords = (body.keywords as string[]) ?? [];
        return send(res, 200, { keywords });
      }
      if (url.pathname.startsWith("/api/") && flaws.htmlNotFound) {
        res.writeHead(404, { "content-type": "text/html" });
        return void res.end("<h1>Not found</h1>");
      }
      return send(res, 404, { error: "Not found" });
    });
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const port = (server.address() as { port: number }).port;
  return { origin: `http://127.0.0.1:${port}`, close: () => new Promise((resolve) => { server.closeAllConnections(); server.close(() => resolve()); }) };
}
