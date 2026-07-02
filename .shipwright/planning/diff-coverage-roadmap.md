# Roadmap — Diff/Patch Coverage ("were the CHANGED lines tested?")

- **Triage anchor:** `trg-8fdebda3` (high / P1, `source=diff-coverage-followup`, opened 2026-06-30)
- **Status:** planned, not started. Phased so each stage is its own shippable iterate.
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
  field is **never populated → SKIP**. A half-built hook is already waiting for this.

## Scope decision
- **Monorepo-Python first (dogfood).** The generic multi-language repo-grader case is
  **deliberately deferred** — it is much harder and would explode the scope.
- Anchor field to populate: `shipwright_test_results.json.coverage` (`total` +
  a new `diff`/`patch` value).

## Sequencing — safe by construction
Phases 1–2 do NOT touch the grade (pure measurement + INFO display). If the monorepo
coverage-combine wiring misbehaves, only an INFO line is affected, never the letter grade.
The signal grows teeth only in 3/4, after the number is stable and calibrated.

### Phase 1 — Measure + surface on ONE tier (informational) · small–medium
- Wire `--cov` into one self-contained tier first (suggest the `shared/` suite: large,
  one `tests` package) → `coverage.xml`.
- `diff-cover coverage.xml --compare-branch=origin/main` → % of changed lines covered.
- Populate `shipwright_test_results.json.coverage.total` + `.diff` (lights the dormant
  W4 field: SKIP → live).
- Dashboard: an **INFO** sub-line under Test-Health ("diff-coverage: X% of changed lines").
  **No grade effect, no gate.**
- Exit criterion: the measurement chain works end-to-end and a real baseline number shows.

### Phase 2 — Roll out to all plugins + combine · medium (the fiddly part)
- `--cov` + `COVERAGE_FILE=.coverage.<plugin>` in every plugin pytest step + integration
  (each plugin has its own uv env + its own `tests` package).
- `coverage combine` with a `[paths]` mapping → one repo-relative `coverage.xml`;
  diff-cover once over the combined report.
- Still INFO only in the dashboard. This is where the real monorepo risk lives — hence
  only after Phase 1 has proven the chain.

### Phase 3 — Feed the Test-Health dimension (grade input, WARN) · small
- Weave diff-coverage into the Control-Grade **Test-Health** dimension (blend with
  pass-rate, or a distinct sub-signal). Below threshold → **WARN** + a moderate score
  reduction. **No hard CI block yet.**
- The grade now reflects "was the changed AI code tested", not just "is the suite green".

### Phase 4 — CI gate (warn → fail) · small
- CI step `diff-cover --fail-under=<threshold>`, first `continue-on-error: true`
  (warn-only, ~1–2 weeks to settle), then hard.
- PRs that add untested code get flagged/blocked.

## Threshold strategy
Do not guess a number. Take the real baseline from Phases 1–2, start conservative
(e.g. WARN < 80% diff-coverage), let it settle before Phase 4 goes hard — anti-ratchet
discipline, like the bloat gate.

## Notes for the executing session
- Each phase = one `/shipwright-iterate` (worktree → PR), medium at most.
- Plugin-source + CI edits → run `scripts/update-marketplace.sh` post-merge (grade wiring
  lands in the cached plugin) and, for the WebUI grade to reflect it, a WebUI re-grade
  (cache-plugin regen, no vendored grade code — see the composition-neutral change).
- If a one-click "Start Campaign" CTA in the WebUI is wanted, scaffold a draft campaign
  with `expands_triage == trg-8fdebda3` (FR-01.33) instead of running the phases ad-hoc.
