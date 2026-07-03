# Roadmap — Diff/Patch Coverage ("were the CHANGED lines tested?")

- **Triage anchor:** `trg-8fdebda3` (high / P1, `source=diff-coverage-followup`, opened 2026-06-30)
- **Status:** Phase 1 in flight (`iterate-2026-07-03-diff-coverage-measure-one-tier`).
  Phased so each stage is its own shippable iterate.
- **Thesis:** pass-rate (`3618/3618 green`) says nothing about whether AI-added code is
  even executed. The killer AI case: the model writes code + a trivial test that misses
  the risky branch → pass-rate stays green, new code untested. Diff-coverage
  (% of the CHANGED lines that tests execute, vs the PR merge-base) is the real control
  signal for the Test-Health dimension — the test-side analogue of making the Control
  Grade composition-neutral (`iterate-2026-07-01-grade-composition-neutral`): replace a
  gameable vanity metric with a signal that actually measures control over AI code.

## Why this is NOT redundant
- The **Test Completeness Ledger** is an author-**claimed** checklist, not instrumented.
  Diff-coverage would empirically **measure** what the ledger claims.
- The **W4 verifier already reads** `shipwright_test_results.json.coverage.total`, but the
  field is **never populated → SKIP**. A half-built hook is already waiting for this —
  **Phase 2** populates it (see the phase-split correction below).

## Scope decision
- **Monorepo-Python first (dogfood).** The generic multi-language repo-grader case is
  **deliberately deferred** — it is much harder and would explode the scope.
- Two distinct signals, two distinct homes:
  - `coverage.total` — repo-stable whole-repo line-rate. Tracked in
    `shipwright_test_results.json.coverage.total`; feeds W4. Populated in **Phase 2**
    (needs the combined repo-wide number to be honest).
  - `coverage.diff` — PR-local (% of the lines changed vs merge-base that are covered).
    **Never tracked** — written to a gitignored transient
    `.shipwright/coverage/diff_coverage.json`, surfaced in CI + the dashboard INFO line.

## Sequencing — safe by construction
Phases 1–2 do NOT touch the grade (pure measurement + INFO display). If the monorepo
coverage-combine wiring misbehaves, only an INFO line is affected, never the letter grade.
The signal grows teeth only in 3/4, after the number is stable and calibrated.

### Phase 1 — Measure + surface on ONE tier (informational) · medium

> **Design correction (2026-07-03, `iterate-2026-07-03-diff-coverage-measure-one-tier`,
> Codex-reviewed).** The original draft said Phase 1 should "populate
> `shipwright_test_results.json.coverage.total` + `.diff` (lights the dormant W4 field)".
> That is unsound and was split: `.total`/W4 moved to **Phase 2**, and `.diff` is kept
> **transient, not tracked**. Reasons: (a) `.diff` is PR-local, so committing it into a file
> read on `main` as steady state shows stale/misleading data; (b) a top-level `coverage.total`
> activates the W4 verifier (`shared/scripts/tools/verifiers/test_compliance.py` — FAIL when
> `< coverage.min`, default 70), i.e. it *is* a gate, which Phase 1 must not add; and in
> Phase 1 we only measure ONE tier, so a shared-only "total" would misrepresent whole-repo
> coverage anyway. Phase 1 still ships the full working measurement chain + a real baseline.

- Wire `--cov` into the `shared/` tier — three separate per-dir pytest processes
  (`shared/tests`, `shared/scripts/tests`, `shared/scripts/tools/tests`, each its own
  top-level `tests` package). Clear a stale `.coverage` first, then `--cov-append`
  accumulates across the three runs → one combined `coverage.xml`.
- `diff-cover coverage.xml --compare-branch=origin/main` → % of changed lines covered.
- `shared/scripts/tools/measure_diff_coverage.py` computes `total` (from `coverage.xml`)
  and `diff` (from `diff-cover`) and writes the **gitignored transient**
  `.shipwright/coverage/diff_coverage.json`. It **never** mutates the tracked
  `shipwright_test_results.json`.
- CI: `--cov` on the shared step (combined `coverage.xml`) + a **non-gating**
  `diff-cover --compare-branch=origin/main` echo step (`continue-on-error: true`, no
  `--fail-under`; uploads `coverage.xml` + the report as an artifact). Requires
  `actions/checkout` **`fetch-depth: 0`** (diff-cover needs the merge-base) and a
  `ci_gate_allowlist` entry so `check_ci_gate_coverage.py` does not flag the intentionally
  non-gating step as a loosened gate.
- Dashboard: a grade-neutral **INFO** sub-line under Test-Health reading the transient
  report ("diff-coverage: X% of changed lines — informational, not yet graded"; "n/a" when
  the transient report is absent, e.g. on a clean `main`). **No grade effect, no gate.**
- Exit criterion: the measurement chain works end-to-end and a real baseline number shows.

### Phase 2 — Roll out to all plugins + combine · medium (the fiddly part)
- `--cov` + `COVERAGE_FILE=.coverage.<plugin>` in every plugin pytest step + integration
  (each plugin has its own uv env + its own `tests` package).
- `coverage combine` with a `[paths]` mapping → one repo-relative `coverage.xml`;
  diff-cover once over the combined report.
- **Now** populate tracked `shipwright_test_results.json.coverage.total` with the combined
  **repo-wide** total (the honest whole-repo number) → this lights the dormant W4 field
  (SKIP → live). Light it GREEN via a **documented, calibrated anti-ratchet
  `shipwright_test_config.json.coverage.min` baseline** — a *new* baseline, not weakening an
  active gate (W4 has never gated this repo). `coverage.diff` stays PR-local/transient
  (never tracked). Still **no grade effect** (that is Phase 3).
- Still INFO only in the dashboard. This is where the real monorepo risk lives — hence
  only after Phase 1 has proven the chain.

### Phase 3 — Feed the Test-Health dimension (grade input, WARN) · small
- Weave diff-coverage into the Control-Grade **Test-Health** dimension (blend with
  pass-rate, or a distinct sub-signal). Below threshold → **WARN** + a moderate score
  reduction. **No hard CI block yet.**
- The grade now reflects "was the changed AI code tested", not just "is the suite green".

### Phase 4 — CI gate (warn → fail) · small
- Upgrade Phase 1's already-present non-gating `diff-cover` step to
  `diff-cover --fail-under=<threshold>`, first `continue-on-error: true`
  (warn-only, ~1–2 weeks to settle), then hard.
- PRs that add untested code get flagged/blocked.

## Threshold strategy
Do not guess a number. Take the real baseline from Phases 1–2, start conservative
(e.g. WARN < 80% diff-coverage), let it settle before Phase 4 goes hard — anti-ratchet
discipline, like the bloat gate.

## Notes for the executing session
- Each phase = one `/shipwright-iterate` (worktree → PR), medium at most.
- **CI mechanics (Phase 1+):** `actions/checkout` needs `fetch-depth: 0` for
  `--compare-branch`; the non-gating `diff-cover` step must be allowlisted in
  `ci_gate_allowlist` (else the CI-gate guard flags it); `.gitignore` must cover
  `coverage.xml` + `.shipwright/coverage/`.
- Plugin-source + CI edits → run `scripts/update-marketplace.sh` post-merge (grade wiring
  lands in the cached plugin) and, for the WebUI grade to reflect it, a WebUI re-grade
  (cache-plugin regen, no vendored grade code — see the composition-neutral change).
- If a one-click "Start Campaign" CTA in the WebUI is wanted, scaffold a draft campaign
  with `expands_triage == trg-8fdebda3` (FR-01.33) instead of running the phases ad-hoc.
