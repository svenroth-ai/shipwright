---
run_id: iterate-20260430-phase0-i3-performance-budgets
type: feature
complexity: medium
status: locked-v3
phase0_iterate: I3 (T3 — Performance Budgets)
spec_source: .shipwright/reviews/phase0-iterates.md
strategic_frame: .shipwright/reviews/phase0-decisions.md (cluster 1b)
review_history:
  - external_plan_review_v1 (2026-04-30 — gemini + openai via openrouter, 17 findings: 3 HIGH + 9 MEDIUM + 5 LOW, all 14 distinct adopted into v2)
  - approval_gate_v1 (2026-04-30 — Sven approves all 3 v2 follow-ups: install-doc fix, touches_build iterate hook, AC trim 18→15)
  - approval_gate_v2 (2026-04-30 — Sven pivots Lighthouse driver: Playwright + lighthouse npm, NOT @lhci/cli. vite-hono.json node bumped to 22.x. install-doc fix obsolete: Playwright already brings Chromium.)
architecture_pivots_v3:
  - "Lighthouse driver: lighthouse npm (programmatic) against Playwright-launched Chromium via CDP. Replaces @lhci/cli. Reasons: zero new user dep (Playwright already in stack), no double-Chromium install, no verify-setup.sh edit needed, deterministic Chromium version pinned by Playwright."
  - "vite-hono profile: stack.runtime.node 20.x → 22.x (Lighthouse 13 + Playwright 1.50 are ESM/Node-22 only)"
  - "Iterate touches_build risk-flag added: triggers performance check in /shipwright-iterate when change touches package.json / lockfile / next.config.* / vite.config.* / tailwind.config.*"
  - "AC count: 18 → 15 (cut AC-15 pre-build scan now done live during Stage 0; cut AC-18 manual-run formality now a self-review bullet; simplified AC-9 test-seam to single SHIPWRIGHT_TEST_MODE guard)"
---

# Iterate Spec — Performance Budgets (Phase 0, I3 / T3)

## Goal

Add a new `performance` test category to `/shipwright-test` that enforces
a **discipline-layer performance budget** on every adopted project: a
Lighthouse-derived web-vital floor, plus a built-output gzipped bundle
ceiling. Defaults activate automatically when the stack profile opts in;
projects override per-profile or via `shipwright_test_config.json`. The
gate runs `warn` by default (logs and continues) and `block` (fails the
test phase) when the project opts in.

This is the first true capability iterate after I1/I2 (doc-only). The
pattern established here — `testing.{category}` block on the profile +
`shipwright_test_config.json.{category}` override + `_check.py` runner
+ SKILL.md step — is intentionally re-used by I4 (A11y Gate) without
modification.

## Architecture Decisions (locked)

**1. Lighthouse driver: `lighthouse` npm (programmatic) against
Playwright-launched Chromium via CDP — NOT `@lhci/cli`.** Approval-Gate
v2 pivot: adopting projects already have Playwright (the existing E2E
runner brings Chromium with it). Reusing that Chromium means zero new
user dependency, no double-Chromium install (LHCI's Puppeteer-bundled
Chromium would have been a separate ~30 MB download next to
Playwright's), no `verify-setup.sh` edit, deterministic Chromium
version (pinned by Playwright). Trade-off accepted: we lose LHCI's
built-in budget assertion (we build our own around our
`success/skipped/skip_reason` schema — wanted that anyway for output
consistency with the other `_check.py` runners). Implementation is a
small Node script (`scripts/perf/lighthouse-runner.mjs`, ~50 LoC) that:
   - launches Chromium via `playwright.chromium.launch({ args:
     ['--remote-debugging-port=0'] })` (port 0 = OS-assigned, no
     collisions)
   - reads the CDP debug-port from the spawned process
   - runs `lighthouse(url, { port, output: 'json' })`
   - prints LHR JSON to stdout, closes browser
The Python runner subprocess-calls this `.mjs` file, parses stdout.

**2. Bundle measurement: zero-config Python direct measurement, NOT
`size-limit`.** `size-limit` is the framework-agnostic budget tool of
choice for projects that want fine-grained per-bundle assertions, but
it requires `.size-limit.json` in every project. For a discipline gate
we measure the built artifact directly: walk the profile's declared
`build_output_dir`, sum gzip-compressed sizes of `*.js` + `*.css`
(excluding `*.map`), compare against budget. Stack-agnostic, zero
user-project dependency, deterministic. `size-limit` integration is a
follow-up iterate when (and only when) a real adopting project asks
for per-bundle granularity.

**3. p95 Route Latency dropped from defaults; Lighthouse LCP used
instead.** Spec ([phase0-iterates.md L262](`.shipwright/reviews/phase0-iterates.md`))
proposed `p95 ≤ 200ms` as a default, but realistic p95 measurement
needs a load-test rig (k6, autocannon) — overkill for v1 and adds a
heavy dependency. Lighthouse already produces `largest-contentful-paint`
(LCP) on the dev URL; we adopt Google's "good" threshold of 2500ms as
the latency-surrogate default. `p95-latency` reactivation is a Phase-0
backlog candidate if a real project surfaces the need.

**4. Gate default `warn` is intentionally lenient.** Phase 0 ships
the discipline; tightening to `block` is the project owner's call once
the budget calibrates against their codebase. Default-block would gate
existing projects on first adoption and break flow.

**5. Override precedence (most-specific wins, DEEP-MERGE at nested
levels — Review Finding 4):**
   1. CLI flag (`--perf-gate block|warn`) — for one-off testing only
   2. `shipwright_test_config.json` → `performance.{lighthouse: {...},
      bundle: {...}, gate}` — per-project lock
   3. Profile `testing.performance.{...}` — stack-level default
   4. Built-in fallback values (Lighthouse 85, bundle 250 kb gz,
      LCP 2500 ms, gate "warn")

   **Deep-merge semantics:** the nested `lighthouse` and `bundle`
   blocks merge field-by-field, NOT object-replace. A project that
   sets only `performance.lighthouse.min_score` in
   `shipwright_test_config.json` inherits `lcp_max_ms` from the
   profile (or builtin if profile didn't set it). The flat fields
   (`gate`, `enabled`) merge by simple assignment — last writer wins.
   Unit test (h) in AC-5 enforces this.

**6. Skip-when-not-applicable, never silent-pass.** The runner emits
an explicit `skipped` result with a reason in any of these cases:
   - Profile has no `testing.performance` block AND
     `shipwright_test_config.json` has no override → `skipped: profile
     opts out`
   - `dev_url` not resolvable (HTTP HEAD fails with connection error,
     DNS error, or timeout — Review Finding 5) → `skipped: no dev_url
     available`. Reachable non-200 responses do NOT trigger skip; the
     Lighthouse run proceeds and reports the actual score (Lighthouse
     itself handles error pages).
   - `build_output_dir` not present (project never built) → bundle
     check returns `skipped: no build artifacts found`, Lighthouse
     still runs if dev_url is up
   - `build_output_dir` exists but `files_measured == 0` (Review
     Finding 3 — never silent-pass at 0 KB) → bundle check returns
     `skipped: no bundle assets matched (0 *.js / *.css files in
     <dir>)`, with the directory path in the reason for diagnosis.
   - `npx @lhci/cli` execution fails for transport reasons (network,
     Chrome unavailable, subprocess timeout — Review Finding 11) →
     `skipped: lighthouse_unavailable` with the stderr captured
   The completion gate in SKILL.md treats `skipped` with a recorded
   reason as a valid result, consistent with the existing
   integration/pgtap/E2E pattern.

**7. Lighthouse output isolation (Review Findings 1+2+G1) — adapted
to Playwright pivot.** Lighthouse-result is captured as JSON via
`output: 'json'` and printed directly to stdout by the Node script,
NOT written to a shared filesystem location like `.lighthouseci/`.
The Python wrapper reads the subprocess stdout. This forecloses the
stale-report-reuse failure mode by construction — no on-disk
artifact to leak across runs. The Chromium instance is closed in a
`try/finally` block to prevent zombie processes.

**8. dev_url SSRF guard (Review Finding 9).** The runner accepts
`dev_url` only if it parses as `http://` or `https://`. Schemes like
`file://`, `gopher://`, etc., raise `ValueError` before subprocess
invocation. Non-loopback hosts (anything other than `localhost`,
`127.0.0.1`, `::1`) emit a stderr WARNING ("Lighthouse target is
non-loopback: <host> — verify this is intentional") but proceed.
Discipline-tool stays permissive; explicit warning catches accidents.

**9. Test-seam guard (Review Finding 10) — simplified per Approval
Gate v2.** `SHIPWRIGHT_PERF_LHCI_FAKE` is honored ONLY when
`SHIPWRIGHT_TEST_MODE=1` is also set in the same env. (Original v2
plan also accepted `PYTEST_CURRENT_TEST`; trimmed to single guard
because pytest sessions can be made to set `SHIPWRIGHT_TEST_MODE`
trivially in a conftest.) Without the guard the env var is ignored
and a stderr WARNING is emitted ("SHIPWRIGHT_PERF_LHCI_FAKE set but
SHIPWRIGHT_TEST_MODE not — ignoring"), then real Lighthouse runs.
This forecloses the "leaked CI env var silently fakes Lighthouse in
prod" failure mode.

**10. Iterate hook via `touches_build` risk-flag — added per
Approval Gate v2.** `/shipwright-iterate` adds a new risk-flag
`touches_build`, triggered when the change touches any of:
   - `package.json`, `package-lock.json`, `npm-shrinkwrap.json`,
     `yarn.lock`, `pnpm-lock.yaml`, `bun.lockb` (dependency surface)
   - `next.config.*`, `vite.config.*`, `tailwind.config.*`,
     `webpack.config.*`, `rollup.config.*`, `tsconfig.json` (build
     config)

When this flag fires, the iterate runner invokes the
performance-check via the same `/shipwright-test` Step 3.8 path. Gate
behavior follows the project's profile/test_config (warn or block).
Skip-rules apply normally (no `dev_url` → skip, no build artifacts →
skip bundle). Eliminates the "package.json touched, nobody noticed"
failure mode without taxing every iterate.

## Acceptance Criteria

- [ ] **AC-1 — Profile schema extended additively.** Both
      `shared/profiles/supabase-nextjs.json` and `shared/profiles/vite-hono.json`
      gain a `testing.performance` object:
      ```json
      "performance": {
        "enabled": true,
        "lighthouse": { "min_score": 85, "lcp_max_ms": 2500 },
        "bundle": { "max_kb_gz": 250, "build_output_dir": ".next/static" },
        "gate": "warn"
      }
      ```
      The `vite-hono` profile uses `build_output_dir: "client/dist/assets"`
      (Vite default). All other existing profile fields untouched. No
      consumer of the profile JSON breaks (verified by running the
      existing test suite green after schema change).

- [ ] **AC-2 — `shipwright_test_config.json` override documented.**
      A new `performance` object is documented in SKILL.md as a
      per-project override; same shape as the profile block, but every
      sub-field is optional and shallow-merges over the profile's
      values (e.g. project sets only `gate: "block"` and inherits
      everything else from profile). Documented precedence chain (CLI
      > test_config > profile > builtin) reproduced verbatim from
      Architecture Decision 5.

- [ ] **AC-3 — Performance runner exists.**
      `plugins/shipwright-test/scripts/lib/performance_check.py` is a
      new executable Python module that:
      (a) accepts `--cwd <project>` `--profile-path <path>`
          `--dev-url <url>` `--gate <warn|block|inherit>` flags
          (`inherit` means use the resolved profile/config value);
      (b) loads the profile JSON + optional `shipwright_test_config.json`
          and applies the precedence chain;
      (c) runs the Lighthouse step (`npx @lhci/cli@<pinned> collect
          --url=<dev-url> --numberOfRuns=1 --settings.preset=desktop`)
          unless the bundle-only short-circuit applies;
      (d) parses the produced `.lighthouseci/lhr-*.json`, extracts
          `categories.performance.score` (×100) and
          `audits.largest-contentful-paint.numericValue`;
      (e) walks `build_output_dir` and sums gzip-compressed sizes of
          all `*.js` and `*.css` files (no `*.map`);
      (f) compares each measured value against its budget;
      (g) emits a single JSON object on stdout matching the Result
          Schema (AC-4);
      (h) exits 0 unless `gate=block` AND any non-skipped check fails.

- [ ] **AC-4 — Result-schema is consistent with existing runners.**
      Output JSON shape:
      ```json
      {
        "success": true,
        "skipped": false,
        "skip_reason": "",
        "gate": "warn",
        "lighthouse": {
          "ran": true,
          "score": 92,
          "score_budget": 85,
          "score_passed": true,
          "lcp_ms": 1840,
          "lcp_budget_ms": 2500,
          "lcp_passed": true,
          "skip_reason": ""
        },
        "bundle": {
          "ran": true,
          "total_kb_gz": 187.4,
          "budget_kb_gz": 250,
          "passed": true,
          "files_measured": 14,
          "skip_reason": ""
        },
        "duration_seconds": 12.7
      }
      ```
      Mirrors the `success`/`skipped`/`skip_reason`/`duration_seconds`
      shape used by `design_fidelity_check.py` and
      `ui_consistency_check.py` so the SKILL.md report-section can
      consume it the same way.

- [ ] **AC-5 — Unit test for runner-wrapper.**
      `plugins/shipwright-test/tests/test_performance_check.py` covers
      with no Lighthouse subprocess invocation:
      (a) `resolve_config()` correctly applies precedence (CLI > test
          config > profile > builtin) — basic case;
      (b) `parse_lighthouse_report()` extracts score + LCP from a
          fixture JSON copied from a real `lhr.json`;
      (c) `measure_bundle()` walks a temp dir of fixture JS/CSS files
          (some `.map`, `.gz`, `.br` — Review Finding 8 — which must
          all be excluded) and returns the correct total kb-gz figure;
      (d) `evaluate_gate()` returns `success=False` only when
          `gate=block` AND a non-skipped check failed; `gate=warn`
          always returns `success=True`;
      (e) skip-cases produce structured `skipped: true` results with
          non-empty `skip_reason` and `success: true`;
      (f) `measure_bundle()` on an empty/no-match dir returns
          `skipped` with `files_measured: 0` and a diagnostic
          `skip_reason` (Review Finding 3) — NOT `passed: True` at 0KB;
      (g) `validate_dev_url()` raises ValueError on `file://` /
          `gopher://` / unknown schemes (Review Finding 9);
      (h) `resolve_config()` deep-merge case — project sets only
          `performance.lighthouse.min_score`, inherits `lcp_max_ms`
          from profile (Review Finding 4);
      (i) test-seam guard — `SHIPWRIGHT_PERF_LHCI_FAKE` set without
          `PYTEST_CURRENT_TEST` and without `SHIPWRIGHT_TEST_MODE`
          returns `False` from `_test_seam_active()` and emits
          stderr warning (Review Finding 10).

- [ ] **AC-6 — Integration test with faked Lighthouse output.**
      `plugins/shipwright-test/tests/test_performance_check_integration.py`
      drives `performance_check.py` end-to-end via subprocess with the
      Lighthouse step monkey-patched (env var
      `SHIPWRIGHT_PERF_LHCI_FAKE=<path-to-fixture-dir>` short-circuits
      the `npx @lhci/cli` call and returns the fixture JSON instead).
      Two cases:
      (a) all-pass scenario — fixture lighthouse score 92, fixture
          bundle dir 180 kb gz, default budgets → exit 0, JSON shows
          `success: true`;
      (b) lighthouse fail under `gate=block` → exit 1, JSON shows
          `success: false`, `lighthouse.score_passed: false`.
      The fake-LHCI mechanism is a documented, supported test seam
      (NOT a hidden hack); it is gated to test contexts only and
      explained in the runner's docstring.

- [ ] **AC-7 — SKILL.md gains Step 3.8 + completion-gate update.**
      A new `## Step 3.8: Performance Budget Check (if applicable)`
      section sits between current Step 3.7 (Design Fidelity) and
      Step 4 (Security). Section structure mirrors Step 3.6/3.7:
      condition (when does it run), command-block invoking the runner,
      result-recording block (`shipwright_test_results.json.performance`
      shape from AC-4), gate behavior (warn vs block), skip
      semantics. The `Results Enforcement` table gets a new row:
      `Performance` → `Warn (default) / Block (opt-in)`. The
      `Completion Gate` table gets a new row: `Performance` → `pass`,
      `warning`, or `skipped: {reason}`. The Skip-reasons list gets
      three new entries: `skipped: profile opts out`,
      `skipped: no dev_url available`,
      `skipped: lighthouse_unavailable`.

- [ ] **AC-8 — Step 3.8 placement is "after Design Fidelity, before
      dev-server stop."** Step 3.7 today stops the dev server at the
      end. To run Lighthouse against a live dev server, Step 3.8 must
      execute BEFORE the dev-server-stop block in 3.7 — OR Step 3.7's
      stop block moves to a new Step 3.9. The plan picks the second
      (move the stop block to a new `## Step 3.9: Stop Dev Server
      (always)` so step ordering remains chronological + readable).
      `dev_server.py stop` invocation is unchanged.

      **Step 3.9 explicit "always-run" semantics (Review Findings
      6+G2):** the new section heading and first paragraph state
      explicitly that this step runs as a finally-block — even if
      Step 3.7 or Step 3.8 hard-failed. The wording mirrors a
      shell `trap`: *"Stop the dev server unconditionally. Run this
      cleanup even if Steps 3.7 or 3.8 raised. A blocked test phase
      is recoverable; a zombie dev server is not."* This forecloses
      the failure mode where a `gate=block` Lighthouse failure
      aborts the practitioner mid-pipeline and leaves a server bound
      to the dev port.

- [ ] **AC-9 — Documented test seam, not a backdoor.**
      `SHIPWRIGHT_PERF_LHCI_FAKE` env var is documented in the
      runner's module docstring as a test-only short-circuit. Two
      guards apply:
      (1) the env value MUST point at an existing JSON file
          (a saved Lighthouse-result document) OR a directory
          containing at least one `lhr-*.json`;
      (2) `SHIPWRIGHT_TEST_MODE=1` MUST also be set in the same env;
      (3) violations of (1) or (2) emit a stderr WARNING and the
          runner falls through to the real Playwright+Lighthouse
          path (NOT a silent-skip — explicit rejection is louder).
      No equivalent backdoor for the bundle measurement — the bundle
      walker is pure Python and trivially mockable in unit tests.

- [ ] **AC-10 — Output format consistency check passes.**
      The new `performance` object in `shipwright_test_results.json`
      conforms to the same JSON shape used by `design_fidelity` and
      `consistency` siblings. Specifically:
      `passed`/`total` keys when applicable; `skipped: bool`;
      `skip_reason: str`. (Exact mapping documented in SKILL.md
      Step 5 results-section update.)

- [ ] **AC-11 — Plugin tests pass clean.**
      `cd plugins/shipwright-test && uv run pytest tests/ -v`
      exits 0, including the two new test files. Existing
      shipwright-test tests still pass (no regressions introduced
      by SKILL.md changes or shared script updates).

- [ ] **AC-12 — Lighthouse npm version pinned, not floating.**
      The Node script `lighthouse-runner.mjs` imports `lighthouse`
      from a pinned major (`lighthouse@13.x`); shipwright-test
      ships a `package.json` next to the script that pins the
      exact version installed in the plugin's `node_modules`.
      Plugin's `node_modules` lives in
      `plugins/shipwright-test/scripts/perf/node_modules/`,
      installed via `npm install` either at marketplace-sync time
      or on first invocation by the Python wrapper (idempotent
      check: if `node_modules/` missing, run `npm install` once).
      Documented in code comment: floating version = non-reproducible
      budget runs as Lighthouse algorithm changes between versions.
      Playwright is NOT pinned by us — we use the project's
      Playwright version (the one that already runs E2E).

- [ ] **AC-13 — No Python runtime dependency added to
      `shipwright-test` pyproject.toml.** The Python runner uses
      only stdlib: `gzip`, `subprocess`, `json`, `pathlib`,
      `argparse`, `tempfile`, `urllib.request`, `urllib.parse`. No
      new pip package required. Node side: `lighthouse`,
      `playwright` are devDeps of the user project (already there
      for E2E); the plugin contributes only `lighthouse-runner.mjs`
      and a tiny `package.json` to pin `lighthouse`.

- [ ] **AC-14 — Smoke-test on Shipwright monorepo: `--help` works.**
      `uv run plugins/shipwright-test/scripts/lib/performance_check.py
      --help` exits 0 and prints usage. (We can't run a full
      Lighthouse pass on the monorepo itself — there's no UI. The
      help-smoke + the integration test with fake LHCI output cover
      the executable surface.)

- [ ] **AC-15 — Bundle measurement semantic explicit (Review
      Findings 8+G3).** `measure_bundle()` excludes ALL of:
      `*.map` (source maps), `*.gz`, `*.br` (precompressed
      siblings — would double-count what we just gzipped). Result
      JSON's `bundle.total_kb_gz` carries a sibling field
      `bundle.measurement_semantic: "gzipped *.js + *.css payload —
      excludes assets, source-maps, precompressed siblings"`. SKILL.md
      Step 3.8 prose includes one-line callout: *"This budget covers
      JavaScript + CSS payload, not full transfer size. Static-asset
      budgets are out of scope for v1."*

- [ ] **AC-16 — Lighthouse subprocess timeout + dev_url scheme
      guard (Review Findings 5+9+11+G5).** Python wrapper invokes
      `subprocess.run(["node", "lighthouse-runner.mjs", url, ...],
      shell=False, timeout=180)`; on `TimeoutExpired` returns the
      lighthouse-skipped result. The subprocess argv is constructed
      as a pure Python list (NOT a shell string), and a code-comment
      documents the shell-injection-safety rationale.
      `validate_dev_url()` raises `ValueError` on schemes other than
      `http`/`https`; non-loopback hosts emit a stderr WARNING but
      proceed (not block — discipline tool stays permissive on dev
      machines).

- [ ] **AC-17 — Iterate `touches_build` risk-flag wired (Approval
      Gate v2).** `plugins/shipwright-iterate/scripts/lib/classify_complexity.py`
      gains a new risk-flag `touches_build`, triggered by changes
      to: `package.json`, `*-lock.*`, `*.lock`, `next.config.*`,
      `vite.config.*`, `tailwind.config.*`, `webpack.config.*`,
      `rollup.config.*`, `tsconfig.json`. When the flag fires, the
      iterate runner adds Performance to the test layers it invokes
      (via the same `/shipwright-test` Step 3.8 path). Iterate's
      Phase Matrix and Risk Taxonomy table both updated. Unit test
      added in `plugins/shipwright-iterate/tests/` covering: (a)
      package.json change → flag fires; (b) src/foo.tsx change →
      flag does NOT fire; (c) flag fires + standalone test
      invocation includes Performance.

## Affected FRs

Self-iterate mode — no FR map exists for the Shipwright monorepo.
Phase-0 spec source: `.shipwright/reviews/phase0-iterates.md` Iterate 3.

## Out of Scope

- **No CI integration.** Performance gate today runs only via
  `/shipwright-test`. Hooking it into `.github/workflows/` is a
  follow-up iterate when (and only when) Sven asks for it.
- **No `size-limit` integration.** Future iterate if an adopting
  project needs per-bundle granularity.
- **No real p95-latency load-test integration.** Reactivation a
  Phase-0 backlog candidate.
- **No mobile Lighthouse preset.** Default `desktop`. Mobile
  preset adds Throttling complexity; deferred.
- **No multiple-URL Lighthouse runs.** Single dev_url per pass.
  Multi-URL is a `lighthouserc.js`-level config that adopting
  projects can wire later.
- **No upload of Lighthouse reports to LHCI server.** Local JSON
  parsing only. `--upload` flag deliberately not exposed.
- **No automatic budget-tightening recommendation engine.**
  Budgets are user-set; the runner reports actual vs budget,
  doesn't suggest "you could lower this by X."
- **No history tracking.** Each run is independent. Comparing
  scores over time is a future feature.
- **No A11y check** — that's I4.
- **No refactor of the existing test runners** (`test_runner.py`,
  `playwright_runner.py`, `design_fidelity_check.py`,
  `ui_consistency_check.py`) — the new runner adds a sibling, not
  a refactor.
- **No `shipwright_test_config.json` schema validator** — the
  config file is read defensively (missing keys fall through to
  profile / builtin); a JSON-Schema for it is overkill for v1.

## Risks

1. **Lighthouse non-determinism.** Same site, same run, same
   network = different score within ±3 points. Mitigation:
   `--numberOfRuns=1` keeps single-run jitter explicit; default
   budget 85 leaves slack. Project owners who want tighter
   tolerance can move to `--numberOfRuns=3` via a future flag.

2. **`npx @lhci/cli` cold-start cost.** First run downloads
   ~30 MB. Acceptable for a discipline gate; documented in
   SKILL.md Step 3.8.

3. **`build_output_dir` profile assumption.** Next.js `.next/`
   layout has changed across versions; Vite `dist/` is more
   stable. Mitigation: defaults are conservative globs (`.next/static`
   for Next, `client/dist/assets` for Vite), the profile owner
   can override per-project, and the runner reports
   `files_measured: N` so a 0-file run is visible.

4. **Profile-schema additive change scope.** AC-1 only touches the
   two existing profiles. If `/shipwright-adopt` generates new
   profiles, those won't auto-include `performance` block — and
   the runner correctly skips with `profile opts out` reason. No
   silent failure path. Adopt-side enhancement is a follow-up
   when Sven decides default-on for new projects.

5. **Test seam env var leakage.** AC-9 risk: a misconfigured CI
   env could leave `SHIPWRIGHT_PERF_LHCI_FAKE=...` set and
   silently fake the Lighthouse step in production. Mitigation:
   runner verifies the env value points at a real directory with
   `lhr-*.json` inside; otherwise it ignores the env (logs a
   warning) and runs the real LHCI command.

## Stop & Ask points (resolved before build)

- **Default budget values (Lighthouse 85, bundle 250 kb gz, LCP
  2500ms).** Numbers are picked from industry-standard "good"
  thresholds. Sven confirms or adjusts in the Approval Gate.
- **`gate: "warn"` default.** Phase 0 says "warn (default) vs
  block (opt-in)". Confirming this stays as written.
- **p95-latency drop in favor of LCP.** Architecture Decision 3.
  Documented above; explicit confirmation in the Approval Gate.
- **`@lhci/cli` version pin.** Need to pick a specific version.
  Suggest `@0.14.0` (current stable as of Apr 2026); confirmable
  during build.

## Reflection Notes (filled at finalize)

_Filled during F3a after build is complete._
