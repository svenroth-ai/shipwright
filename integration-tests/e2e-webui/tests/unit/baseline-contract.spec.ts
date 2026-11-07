// No model: the dynamic part of the baseline checks (start the built companion, talk HTTP to it) against a tiny stand-in
// backend written in Python for this test. It implements only the generic API rules (Host, X-Board, 404, 400, 413), once
// correctly and once with a flaw, to show the checks can pass and can fail, and that the companion is started and stopped cleanly.
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { expect, test } from "@playwright/test";
import { badRequests, localAccess } from "../../src/baseline/checks-contract.js";
import { scenario, type Ctx } from "../../src/baseline/ctx.js";
import { resolvePython } from "../../src/baseline/companion.js";
import { startFakeServices } from "../../src/baseline/fake-services.js";
import { Probe } from "../../src/baseline/probe.js";

const repo = path.resolve(import.meta.dirname, "..", "..", "..", "..");
const recorded = path.join(repo, "integration-tests", "fixtures", "social-engagement-baseline", "seed", "recorded");

const SERVER = (flaw: string) => `
import argparse, json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
ap = argparse.ArgumentParser(); ap.add_argument("--host"); ap.add_argument("--port", type=int); ap.add_argument("--data-dir")
a = ap.parse_args()
FLAW = ${JSON.stringify(flaw)}
class H(BaseHTTPRequestHandler):
    def log_message(self, *x): pass
    def send(self, code, obj):
        b = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8"); self.send_header("Content-Length", str(len(b)))
        self.send_header("Cache-Control", "no-store"); self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers(); self.wfile.write(b)
    def local(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        if FLAW != "host" and host not in ("127.0.0.1", "localhost"):
            self.send(403, {"error": "local access only"}); return False
        return True
    def do_GET(self):
        if not self.local(): return
        if self.path == "/api/health": self.send(200, {"ok": True, "app": "social-engagement", "data_dir": a.data_dir, "version": "0"})
        else: self.send(404, {"error": "not found"})
    def do_POST(self):
        if not self.local(): return
        if self.headers.get("X-Board") != "1": self.send(403, {"error": "local board only"}); return
        n = int(self.headers.get("Content-Length") or 0)
        if n > 20000 and not self.path.startswith("/api/runs"): self.read = self.rfile.read(n); self.send(413, {"error": "too large"}); return
        raw = self.rfile.read(n)
        try: json.loads(raw)
        except Exception: self.send(400, {"error": "body is not JSON"}); return
        if self.path == "/api/status": self.send(404, {"error": "unknown thread " + "x"}); return
        self.send(200, {"ok": True})
    do_PUT = do_POST
ThreadingHTTPServer((a.host, a.port), H).serve_forever()
`;

async function withStub(flaw: string, fn: (ctx: Ctx) => Promise<void>) {
  const project = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-stub-project-"));
  fs.mkdirSync(path.join(project, "backend"));
  fs.writeFileSync(path.join(project, "backend", "server.py"), SERVER(flaw));
  const fake = await startFakeServices(recorded);
  const ctx: Ctx = { project, fixtureDir: "", python: resolvePython(), tmpRoot: fs.mkdtempSync(path.join(os.tmpdir(), "e2e-stub-run-")), fake, tokens: { syften: "a", apify: "b" }, leaks: [], synthetic: [] };
  try {
    await fn(ctx);
  } finally {
    await fake.stop();
    fs.rmSync(project, { recursive: true, force: true });
    fs.rmSync(ctx.tmpRoot, { recursive: true, force: true });
  }
}

// @covers FR-01.06
test("a correct backend passes the local-access and bad-request checks, the data folder and logs are collected, the process is gone", async () => {
  await withStub("none", async (ctx) => {
    const probes = { access: new Probe(), bad: new Probe() };
    let port = 0;
    await scenario(ctx, "stub", {}, async (s) => {
      port = s.c.port;
      await localAccess(s, probes.access);
      await badRequests(s, probes.bad);
    });
    expect(probes.access.verdict().evidence).not.toMatch(/broken: a foreign Host/);
    expect(probes.bad.verdict()).toMatchObject({ pass: true });
    expect(ctx.leaks.some((l) => l.where.includes("answer to"))).toBe(true);
    await expect(fetch(`http://127.0.0.1:${port}/api/health`)).rejects.toThrow();
  });
});

// @covers FR-01.06
test("a backend that accepts any Host fails the local-access check and says which rule broke", async () => {
  await withStub("host", async (ctx) => {
    const p = new Probe();
    await scenario(ctx, "stub-flawed", {}, (s) => localAccess(s, p));
    const v = p.verdict();
    expect(v.pass).toBe(false);
    expect(v.evidence).toContain("a foreign Host is refused with 403 local access only");
  });
});

// @covers FR-01.06
test("a companion that cannot start is reported with its output, not hung", async () => {
  await withStub("none", async (ctx) => {
    fs.writeFileSync(path.join(ctx.project, "backend", "server.py"), "import sys; print('boom'); sys.exit(3)\n");
    await expect(scenario(ctx, "broken", {}, async () => undefined)).rejects.toThrow(/exited with 3.*boom/s);
  });
});
