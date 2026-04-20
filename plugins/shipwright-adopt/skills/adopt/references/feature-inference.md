# Feature Inference — Playwright Crawl vs AST Fallback

Adopt identifies the project's functional surface (routes, pages,
user-facing features) via a two-track strategy.

## Layer 1.5 — Playwright Crawl (preferred when possible)

When the target is a web-app with a startable dev-server, Adopt runs a
BFS link-crawler over the live application. This is the **preferred
path** — framework-agnostic, ground-truth, and yields richer signals
(page titles, h1 texts, form fields, button labels, screenshots).

### Flow

1. `playwright_setup.py` installs `@playwright/test` + browsers into the
   target project (idempotent — skips if already present).
2. `dev_server.py start` spawns the target's `dev` command, waits for
   the port to become healthy (60s budget).
3. `route_crawler.py` launches Chromium, navigates to `http://localhost:<port>/`,
   extracts links, follows them BFS-style, records metadata + screenshots.
4. `dev_server.py stop` cleanly terminates the subprocess.

### BFS rules

- Max depth: `--crawl-max-depth` (default 3)
- Max pages: `--crawl-max-pages` (default 50)
- Only internal links (same origin). External, `mailto:`, `tel:`,
  `javascript:`, and anchor-only links are skipped.
- Duplicate URLs: track visited-set; skip re-visits.
- Auth-gated: `--crawl-auth-token <value>` sets a `Bearer` header on
  all requests.

### Skip conditions

- `--skip-crawl` passed explicitly
- No `dev` command detected in `package.json` scripts
- Primary language is not web-capable (`go`, `rust`, pure-CLI Python)
- Dev-server fails health-check within 60s
- Crawl produces zero routes (auth wall, broken app)

In any skip case, the AST fallback below is used, and the handoff
message documents the reason.

## Layer 1 — AST Fallback

When Playwright isn't available/applicable, `feature_inferrer.py`
enumerates routes from well-known framework file conventions:

| Framework | Conventions scanned |
|---|---|
| Next.js App Router | `src/app/**/page.tsx` (or `app/**/`), route-groups `(name)` stripped |
| Next.js Pages Router | `src/pages/**/*.tsx` (or `pages/**/`), `_app`/`_document` skipped |
| Express / Fastify / Koa | `app.get/post/put/patch/delete(...)` in `src/**/*.ts` |
| FastAPI | `@app.get/post/...('/path')` in `*.py` |
| Flask | `@app.route('/path')` / `@bp.route(...)` |

Each detected route becomes a feature with a generated FR-ID
(`FR-01.<NN>`) and a low-to-moderate confidence score.

## Merging Layer 1.5 + Layer 2

When both a Playwright crawl AND a Layer-2 enrichment exist, Adopt
builds final `features[]` by joining on `url` / `route`:

```
crawled: {url: "/dashboard", title, h1, buttons, screenshot}
enriched: {route: "/dashboard", label, description, acceptance_draft}
```

Resulting FR entry carries all of these fields. AST-inferred features
are used only when no crawl data exists.
