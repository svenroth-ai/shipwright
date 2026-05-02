---
run_id: iterate-20260430-phase0-i3-performance-budgets
spec: 20260430-phase0-i3-performance-budgets.md
status: locked-v3
review_history:
  - external_plan_review_v1 — 17 findings, 14 distinct adopted into spec v2 + plan v2
  - approval_gate_v1+v2 — Sven approves: Playwright pivot, Node 22 bump, AC trim 18→15, touches_build risk-flag
plan_diff_v2_to_v3:
  - Stage 3 — Node `lighthouse-runner.mjs` (~50 LoC) replaces `npx @lhci/cli` subprocess; Python wrapper subprocess-calls Node script; LHCI flag-probe step OBSOLETE
  - Stage 4 — vite-hono.json runtime.node 20.x → 22.x (Lighthouse 13 + Playwright 1.50 ESM/Node-22 only)
  - Stage 5 — verify-setup.sh edit OBSOLETE (Playwright-Chromium already covered)
  - Stage 5.5 NEW — touches_build risk-flag wiring in shipwright-iterate plugin
  - AC trim — AC-15 (pre-build scan) folded into Stage 0 LIVE; AC-18 (manual run) demoted to self-review bullet; AC-9 simplified to single SHIPWRIGHT_TEST_MODE guard
  - Plugin scripts/perf/ subdir gets `package.json` pinning lighthouse@13.x; node_modules installed by marketplace-sync OR first-invoke check
---

# Mini-Plan — Iterate 3 (T3 Performance Budgets)

## Approach

Add a sibling check-runner alongside the existing
`design_fidelity_check.py` / `ui_consistency_check.py` pattern:
`performance_check.py`. Profile-driven; `shipwright_test_config.json`
overrides; `warn`/`block` gate. Lighthouse via `npx @lhci/cli`,
bundle via Python gzip-walk on the profile's `build_output_dir`.

The runner is profile-agnostic: nothing about it knows "Next.js" or
"Vite" — it knows `dev_url` (for Lighthouse) and `build_output_dir`
(for bundle). Stack-specifics live entirely in the profile JSON.

## Files (new vs touched)

**New:**
- `plugins/shipwright-test/scripts/lib/performance_check.py` — Python runner (orchestrator + bundle-check + result builder)
- `plugins/shipwright-test/scripts/perf/lighthouse-runner.mjs` — Node script (Playwright-Chromium + Lighthouse, ~50 LoC)
- `plugins/shipwright-test/scripts/perf/package.json` — pins `lighthouse@13.x`
- `plugins/shipwright-test/scripts/perf/.gitignore` — ignores `node_modules/`
- `plugins/shipwright-test/tests/test_performance_check.py` — unit tests
- `plugins/shipwright-test/tests/test_performance_check_integration.py` — integration test (subprocess + fake-Lighthouse via SHIPWRIGHT_PERF_LHCI_FAKE seam)
- `plugins/shipwright-iterate/tests/test_classify_complexity_perf.py` — unit tests for new touches_build risk-flag (Stage 5.5)
- `plugins/shipwright-test/tests/fixtures/lhci/lhr-good.json` — fixture: passing Lighthouse run (score 92, LCP 1840ms)
- `plugins/shipwright-test/tests/fixtures/lhci/lhr-bad.json` — fixture: failing Lighthouse run (score 71, LCP 4100ms)
- `plugins/shipwright-test/tests/fixtures/bundle/sample-app/main.js` — fixture: ~150KB JS
- `plugins/shipwright-test/tests/fixtures/bundle/sample-app/styles.css` — fixture: ~30KB CSS
- `plugins/shipwright-test/tests/fixtures/bundle/sample-app/main.js.map` — fixture: must be excluded from sum (sourcemap)
- `plugins/shipwright-test/tests/fixtures/bundle/sample-app/vendor.js.gz` — fixture: must be excluded (Finding 8 — precompressed sibling)
- `plugins/shipwright-test/tests/fixtures/bundle/sample-app/vendor.js.br` — fixture: must be excluded (Finding 8 — precompressed sibling)
- `plugins/shipwright-test/tests/fixtures/bundle/empty-app/.keep` — fixture: 0 bundle files → AC-5 (f) skip case

**Touched:**
- `shared/profiles/supabase-nextjs.json` — add `testing.performance` block
- `shared/profiles/vite-hono.json` — add `testing.performance` block + bump `runtime.node` 20.x → 22.x
- `plugins/shipwright-test/skills/test/SKILL.md` — Step 3.8 (insert), Step 3.9 (extracted dev-server-stop), Step 5 results table, Completion-Gate table, Skip-reasons list
- `plugins/shipwright-iterate/skills/iterate/SKILL.md` — Risk Taxonomy table + Phase Matrix (Stage 5.5)
- `plugins/shipwright-iterate/scripts/lib/classify_complexity.py` — `touches_build` flag detector (Stage 5.5)
- `scripts/update-marketplace.sh` — confirm it copies `plugins/shipwright-test/scripts/perf/` (likely already does, verify in Stage 5)

**Conditionally touched (scope creep guard — only if needed):**
- `docs/hooks-and-pipeline.md` — Test phase entry update if we surface
  a new W-marker. **Decision: no W-marker for Performance in v1**;
  the gate is warn-default and block is opt-in, so a phase-quality
  hard-fail on missing budget would be wrong. Document defers to I4
  decision (when A11y has the same shape).

**NOT touched (out of scope):**
- `.github/workflows/` — no CI integration in v1
- existing test runners
- `shipwright-adopt` plugin — profile-defaults work is decoupled

## Build Sequence (TDD, Red-Green-Refactor)

### Stage 0 — Pre-build profile-schema consumer scan (NEW from review v1)

a. `grep -rn 'testing\.\(unit\|e2e\|integration\)' shared/ plugins/` — find readers of profile.testing.*
b. `grep -rn 'additionalProperties' shared/ plugins/ docs/` — find any JSON-Schema validators on profile JSON
c. `grep -rn '"performance"' shared/ plugins/ docs/` — confirm no name collision with existing profile field
d. Document scan result in AC-15 of the spec; if ANY hit shows a strict consumer, halt and Stop&Ask

### Stage 1 — Test Infrastructure (Red)

1. Create `plugins/shipwright-test/tests/fixtures/` if missing
2. Drop fixture files (`lhr-good.json`, `lhr-bad.json`, `sample-app/`)
3. Create `test_performance_check.py` skeleton with all 5 unit-test
   cases from AC-5; each test imports `from performance_check
   import resolve_config, parse_lighthouse_report, measure_bundle,
   evaluate_gate` — all currently `ImportError`s
4. Run `uv run pytest tests/test_performance_check.py -v` — all RED
   (ImportError, ModuleNotFoundError) confirms tests will fail
   without implementation

### Stage 2 — Pure-Python Helpers (Green)

5. Create `performance_check.py` with empty module
6. Implement `resolve_config(cli_args, project_root, profile)` —
   precedence chain (CLI > test_config.json > profile > builtin)
   - GREEN: AC-5 (a) passes
7. Implement `parse_lighthouse_report(lhr_dir: Path)` — finds
   first `lhr-*.json`, extracts `categories.performance.score` (×100)
   and `audits.largest-contentful-paint.numericValue`
   - GREEN: AC-5 (b) passes
8. Implement `measure_bundle(build_dir: Path)` — `Path.rglob` for
   `*.js` and `*.css`, exclude `*.map`, gzip-compress in memory,
   return total kb. Use `gzip.compress(bytes, compresslevel=9)`.
   - GREEN: AC-5 (c) passes
9. Implement `evaluate_gate(results: dict, gate: str) -> bool` —
   gate=warn always returns True; gate=block returns False if any
   non-skipped check failed
   - GREEN: AC-5 (d) passes
10. Implement skip-result helper, wire into the helpers above
    - GREEN: AC-5 (e) passes
11. Run `uv run pytest tests/test_performance_check.py -v` — ALL GREEN

### Stage 3 — Node lighthouse-runner.mjs + Python CLI Wrapper + Integration Test

12. Create `plugins/shipwright-test/scripts/perf/package.json`:
    ```json
    { "name": "shipwright-test-perf", "version": "0.1.0", "type": "module",
      "private": true, "dependencies": { "lighthouse": "^13.0.0" } }
    ```
13. Create `plugins/shipwright-test/scripts/perf/.gitignore` with `node_modules/`
14. Create `plugins/shipwright-test/scripts/perf/lighthouse-runner.mjs`:
    ```javascript
    // Args: <url> [--user-data-dir <dir>]
    // Reads PLAYWRIGHT_BIN_PATH if set; else uses 'playwright' module from cwd
    import { chromium } from 'playwright';   // resolved from caller cwd
    import lighthouse from 'lighthouse';
    const url = process.argv[2];
    const browser = await chromium.launch({ args: ['--remote-debugging-port=0'] });
    try {
      const wsEndpoint = browser.wsEndpoint();
      const portMatch = wsEndpoint.match(/:(\d+)\//);
      if (!portMatch) throw new Error('Could not parse CDP port');
      const port = Number(portMatch[1]);
      const { lhr } = await lighthouse(url, { port, output: 'json',
        logLevel: 'error', onlyCategories: ['performance'] });
      process.stdout.write(JSON.stringify(lhr));
    } finally {
      await browser.close();
    }
    ```
    On any error: print `{"error": "..."}` to stdout, exit 1. Caller treats
    non-zero exit as `lighthouse_unavailable`.
15. Implement `main()` in `performance_check.py` — argparse,
    orchestrates: validate dev_url → ensure node_modules (lazy
    `npm install` in scripts/perf/ if missing) → run Node script
    OR fake-seam → parse stdout → bundle-check → evaluate gate →
    print JSON. Exit code per AC-3 (h).
16. Implement `run_lighthouse(dev_url, project_root)`:
    - `validate_dev_url(dev_url)` first
    - if `_test_seam_active()` AND `SHIPWRIGHT_PERF_LHCI_FAKE`
      points at a real file/dir: read fixture JSON, return parsed
    - else: subprocess.run(["node", str(perf_dir/"lighthouse-runner.mjs"),
      dev_url], cwd=project_root, shell=False, timeout=180,
      capture_output=True, text=True). Caller cwd = project_root so
      Node resolves Playwright from project's node_modules.
    - parse stdout JSON; on TimeoutExpired or non-zero exit, return
      `lighthouse_unavailable` skip result with stderr captured.
    Code-comment documents `shell=False` rationale.
14. Create `test_performance_check_integration.py`:
    - Test (a) — temp project + fake LHCI good fixture + sample-app
      bundle dir → exit 0, success: true
    - Test (b) — fake LHCI bad fixture, gate=block → exit 1,
      success: false
15. Run integration tests — must be GREEN
16. Run smoke test from monorepo root:
    `uv run plugins/shipwright-test/scripts/lib/performance_check.py --help`
    → exit 0 (AC-14)

### Stage 4 — Profile Schema Extension

17. Edit `shared/profiles/supabase-nextjs.json` — append
    `testing.performance` block with `build_output_dir: ".next/static"`.
    Profile already pins Node 22.x, no runtime bump needed.
18. Edit `shared/profiles/vite-hono.json`:
    (a) append `testing.performance` block with
        `build_output_dir: "client/dist/assets"`
    (b) bump `stack.runtime.node` from `"20.x"` to `"22.x"` —
        Lighthouse 13 + Playwright 1.50 are ESM/Node-22 only
19. Run plugin test suite from monorepo root:
    `uv run pytest plugins/shipwright-test/tests/ -v`
    AND from shared:
    `uv run pytest shared/tests/ -v`
    No regressions on either.

### Stage 5 — SKILL.md Documentation

20. Open `plugins/shipwright-test/skills/test/SKILL.md`
21. Insert `## Step 3.8: Performance Budget Check (if applicable)`
    between current 3.7 and current 4. Sections: Condition, Run
    block (with the runner CLI), Results-record block (the JSON
    shape from AC-4), Gate behavior, Skip semantics. Mirror
    structure of existing 3.6/3.7. **Add explicit one-line callout
    (Finding G4):** *"The bundle check requires a prior production
    build (`npm run build` or equivalent). If `build_output_dir`
    doesn't exist or is empty, the bundle check skips with reason
    in the result; the Lighthouse check still runs."*
22. Extract dev-server-stop block from 3.7 into new
    `## Step 3.9: Stop Dev Server (always)`. 3.7's last paragraph
    becomes a one-line cross-reference: "Dev server is stopped in
    Step 3.9 below." **The new Step 3.9 opens with a strong
    finally-block paragraph (Findings 6+G2):** *"This step runs
    unconditionally as a cleanup pass — even if Step 3.7 or Step
    3.8 raised. A blocked test phase is recoverable; a zombie dev
    server bound to the dev port is not. Practitioners executing
    SKILL.md by hand and CI runners parsing the step list MUST
    treat this section as a `finally` clause."*
23. Update Step 5 Results-Enforcement table — add `Performance`
    row (Warn/Block).
24. Update Step 5 Completion-Gate table — add `Performance` row
    (pass/warning/skipped).
25. Update Skip-reasons list — add the three new entries
    (`profile opts out`, `no dev_url available`,
    `lighthouse_unavailable`).
26. Update intro banner Test-layers list to include
    `3.8 Performance budget (if profile opts in)` and
    `3.9 Stop dev server`.

### Stage 5.5 — touches_build risk-flag in shipwright-iterate (NEW v3)

26a. Open `plugins/shipwright-iterate/scripts/lib/classify_complexity.py`,
     read structure
26b. Add `touches_build` flag detector: glob match against
     `package.json`, `*-lock.*`, `*.lock`, `next.config.*`,
     `vite.config.*`, `tailwind.config.*`, `webpack.config.*`,
     `rollup.config.*`, `tsconfig.json`. Returns True if the
     diff'd files include any of these.
26c. Update `plugins/shipwright-iterate/skills/iterate/SKILL.md`:
     - Risk Taxonomy table: add `touches_build` row, "small" min
       complexity, enforces "Performance test layer included"
     - Phase Matrix: add Performance row with conditional "if
       touches_build flag" trigger; otherwise N/A
     - Override Classes: Performance under Safety-enforced when
       touches_build is set
26d. Add `plugins/shipwright-iterate/tests/test_classify_complexity_perf.py`:
     - test_touches_build_fires_on_package_json
     - test_touches_build_fires_on_next_config
     - test_touches_build_does_not_fire_on_src_change
26e. Run `uv run pytest plugins/shipwright-iterate/tests/ -v`
     — all green incl. the new file

### Stage 6 — Verification Loop

27. Re-run `uv run pytest plugins/shipwright-test/tests/ -v`
28. Re-run `uv run pytest shared/tests/ -v`
29. Re-run `uv run pytest integration-tests/ -v` (top level)
30. **Manual real-LHCI run (AC-18, Finding 12).** Pick an existing
    example project (or one Sven points at) and run the runner
    against a live dev server: confirm `npx @lhci/cli@0.14.0`
    actually executes, JSON parses, score is populated, no
    `.lighthouseci/` residue left. If no real example project is
    available today: mark this step `degraded`, file a follow-up
    item in `.shipwright/reviews/phase0-backlog.md` (or wherever
    Sven decides), do NOT silently skip.
31. Self-review (Step 7 of iterate)
32. External code review (Step 8 — `--mode code`)
33. Marketplace sync, push to main

## Test Strategy

**Unit tests** — fast, in-process, exercise each pure helper.
File: `test_performance_check.py`.

**Integration test** — subprocess driver, exercise CLI surface,
exercise the fake-LHCI seam to avoid actual `npx @lhci/cli` in
the test suite. File: `test_performance_check_integration.py`.

**Smoke test** — `--help` from monorepo (no UI on shipwright
itself, can't full-run Lighthouse). Documented in AC-14.

**No real Lighthouse run in CI tests.** That requires a live
URL — the test suite cannot assume one. Sven validates against
a real adopting project as part of self-review (Step 7) on a
checkout of one of the existing example projects (or skips that
validation honestly if no example project is reachable today —
in which case a follow-up validation iterate is added to the
backlog).

## Risk-Mitigations during build

- **Test fixture stability:** `lhr-good.json` and `lhr-bad.json`
  are stripped down to only the keys the runner reads
  (`categories.performance.score`, `audits.largest-contentful-paint`).
  Keeps fixtures small and avoids breakage when Lighthouse adds
  new audit categories.
- **`npx @lhci/cli` not invoked in any test.** All Lighthouse code
  paths go through the env-var seam in tests. Real-Lighthouse
  invocation is a manual self-review check by Sven.
- **`build_output_dir` glob mistakes:** the bundle measurement
  function takes a `Path`, walks with `rglob`, returns
  `files_measured: N` so a zero-file glob is visible in the
  result JSON instead of silently passing.

## Estimated effort breakdown (v3 after Approval Gate)

| Stage | Estimated time |
|---|---|
| 0 — Pre-build profile-schema scan (live) | 15 min |
| 1 — Test infra + fixtures | 45 min |
| 2 — Pure-Python helpers (deep-merge, dev_url, test-seam) | 2 h |
| 3 — Node lighthouse-runner.mjs + Python wrapper + integration test | 2 h |
| 4 — Profile schema (incl. vite-hono Node 22 bump) | 20 min |
| 5 — SKILL.md doc (Step 3.8 + 3.9 + callouts) | 1 h |
| 5.5 — touches_build risk-flag in shipwright-iterate | 45 min |
| 6 — Verification loop + manual run (real or degraded) | 1 h |
| **Total** | ~8 h (still within "1-2 days" envelope) |

## Open questions for User Approval Gate

1. **Defaults OK?** Lighthouse Score ≥85, Bundle ≤250 kb gz,
   LCP ≤2500 ms, gate `warn`. Spec wants final-justify before
   build.
2. **p95 → LCP swap OK?** Decision 3 above.
3. **`@lhci/cli` version pin OK at `@0.14.0`?** Or do you want
   me to pick a different stable line?
4. **No CI integration in v1 OK?** Confirms scope cut.
