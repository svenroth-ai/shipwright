# Iterate: Interleaved-serial as the single documented campaign default

- **Run ID:** `iterate-2026-06-13-campaign-serial-default`
- **Intent:** CHANGE · **Spec Impact:** MODIFY (campaign orchestration behavior + docs)
- **Complexity:** medium (classifier said `large` — keyword false-positive on
  "retire/restructure/single default"; the diff is one prose restructure + a
  small additive `cmd_next` branch + doc edits + tests → medium; recorded in
  `degraded[]`)
- **Risk flags:** `cross_component` (touches `autonomous_loop.py`,
  `campaign_init.py`, `campaign-mode.md`) → integration coverage + full suite.

## Problem

`references/campaign-mode.md` documents the OPPOSITE of what is safe. The
autonomous loop builds **all** sub-iterate PRs first (auto-merge deferred via
`SHIPWRIGHT_ITERATE_AUTOMERGE=0`), then a Step-4 "Serial Merge Drain" merges
them one-by-one with `ensure_current.py` snapshot regeneration. Because every
branch is built BEFORE any merge, siblings touching the same file (A+B both edit
`record_event.py`) never see each other → the drain must 3-way + regenerate each
branch against the advancing `origin/main` = recurring **merge theater**. The
whole regenerate-at-merge machinery only exists to paper over builds-before-merges.

## Change

Make **interleaved-serial** the single documented campaign default; retire
build-all-then-drain. The loop builds ONE sub-iterate → opens PR → waits for CI
green (no shoot-and-forget) → merges → advances local `main` → builds the NEXT
from fresh `origin/main`. Each sub-iterate is built on a `main` that already
contains all prior ones, so shared-file edits compose naturally. **Key
simplification:** only ever ONE open sub-iterate PR at a time → the
simultaneous-open-PR cascade that motivated the drain machinery cannot occur.

New `branch_strategy` value **`serial`** (base = fresh `origin/main`,
merge-before-next), becomes the `campaign_init` default. `stacked` drops out of
the documented flow but is kept as a code value for back-compat (shipwright-build
sections still use `single-branch`/`stacked`; `autonomous_loop.py` is shared).
The `SHIPWRIGHT_ITERATE_AUTOMERGE=0` defer stays (PR doesn't self-arm; the
orchestrator owns the merge), but it now merges each PR in turn right after its
build, not at an end-stage drain.

## Acceptance Criteria

- [ ] AC1: `autonomous_loop.py` — `VALID_STRATEGIES` includes `serial`; `cmd_next`
      returns `base_branch` = the **freshly-fetched remote default ref**
      (`origin/<default>`, resolved from `origin/HEAD`, fallback `origin/main`;
      fail-soft `git fetch`) for `serial`, so a sub-iterate can never branch off a
      stale LOCAL `main` (external-review HIGH: code-enforce, don't trust prose;
      also fixes hardcoded-`main`).
- [ ] AC2: `campaign_init.py` — `--branch-strategy` default is `serial`, choices
      `[serial, stacked, independent]`; `init_campaign` default param is `serial`.
- [ ] AC3: `campaign-mode.md` — autonomous loop restructured to interleaved
      (build→merge(CI-green)→advance main→next); no separate end-stage drain;
      setup/init examples use `serial`; explicit CI-wait mechanism
      (`watch_pr_delivery.py`/`gh pr checks`); **strict-stop on non-delivered**
      (CI fail / merge conflict / timeout → STOP campaign, merged subs stay
      durable, do NOT proceed to next — external-review HIGH #4).
- [ ] AC4: `SKILL.md` §5b + F11 index row + `F11.md` campaign prose +
      `sub-iterate-runner.md` base all reflect interleaved-per-iteration merge
      (base = fresh `origin/main`); the `SHIPWRIGHT_ITERATE_AUTOMERGE=0` defer
      mechanism is preserved.
- [ ] AC5 (integration, cross_component): a real-scenario **git** test (bare
      origin + fetch + merge) proves *content composition* — sub-iterate 1 changes
      a shared file and merges to origin; sub-iterate 2, branched off the `serial`
      base returned by `cmd_next`, **sees that change** as its starting tree (not
      merely `base=="origin/main"` — external-review #7). Recorded
      `category:"integration"`.
- [ ] AC7: reader/doc sweep (required, not best-effort) — every `branch_strategy`
      consumer accepts `serial` (no allowlist rejects it); a campaign persisted
      with `branch_strategy: serial` loads through the status/resume path; no stale
      `stacked`/`Serial Merge Drain` refs remain in docs/fixtures
      (external-review #2/#3).
- [ ] AC6: `test_campaign_serial_drain.py` rewritten to pin the interleaved
      sequence; `test_campaign.py` default-strategy assertions updated to
      `serial`; `test_f11_automerge_arm.py` campaign-defer asserts still green.

## Affected Boundaries

- **`autonomous_loop.py` ↔ campaign-mode.md prose** (producer of `base_branch` ↔
  orchestrator that checks out + advances main). The contract: `serial` →
  `base_branch="main"`; orchestrator MUST advance local `main` before each `next`.
- **`campaign_init.py` CLI** (`--branch-strategy` public surface) ↔ `status.json`
  / `campaign.md` frontmatter `branch_strategy:` ↔ `autonomous_loop init
  --branch-strategy` (must be in `VALID_STRATEGIES` or argparse rejects it).
- **`cross_component` gate** (`integration_coverage.check_integration_coverage`)
  recomputes the flag from `merge-base..HEAD`; the diff touches three matched
  paths → requires the AC5 `category:"integration"` behavior.

## Self-Review (7-item)

1. Spec Compliance — PASS: AC1–AC7 all covered (see ACs + tests).
2. Error Handling — PASS: `git fetch`/`symbolic-ref` fail-soft (fallback `main`,
   tested `test_serial_fetch_failure_is_failsoft`); non-delivered → strict-stop (prose).
3. Security Basics — PASS: fixed-arg `subprocess.run` (no `shell=True`), no secrets.
4. Test Quality — PASS: real-git composition proves the behavioral fix; back-compat
   (`stacked`/`single-branch`) retained; outcomes asserted, not internals.
5. Performance Basics — PASS (noted): serial-only `git fetch` under the
   single-orchestrator loop lock; build/single-iterate paths untouched.
6. Naming & Structure — PASS: consistent `serial`; `campaign_init.py`/`test_campaign.py`
   kept ≤300 LOC; no dead code.
7. Affected Boundaries — PASS: all three boundaries round-trip-probed (below).

## Confidence Calibration
- **Boundaries touched:** autonomous_loop base_branch contract; campaign_init CLI
  default/choices; the campaign-mode orchestration prose; the cross_component gate.
- **Empirical probes run (results):**
  (1) serial base resolution — `test_serial_provides_fresh_remote_default_base`,
  `_first_unit_also_off_fresh_remote`, `_respects_non_main_default_branch`
  (origin/develop), `_fetch_failure_is_failsoft` → all green; no findings.
  (2) campaign_init default round-trip — init default + CLI default = `serial`,
  explicit `serial` accepted, `stacked` still accepted, bogus rejected → green.
  (3) **composition (the real fix)** — real-git: S2 branched off the serial base
  SEES S1's merged change while LOCAL main stays stale (v0) → green.
  (4) back-compat — full `test_autonomous_loop` (24) + campaign suites + the
  parallel-merge cascade (integrate_main untouched) → green.
- **Test Completeness Ledger:** every AC → a test; AC5 is the
  `category:"integration"` behavior; no testable-but-untested behavior.
- **Confidence-pattern check:** asymptote reached — two clean probe rounds (full
  suites green, no new findings); breadth — loop state machine + CLI + docs drift;
  **integration composition** — AC5 proves `serial` composes end-to-end.
- **Edge-cases not probed (acceptable):** live `gh pr checks --watch` / real PR
  merge in the campaign loop = `requires-external-nondeterministic-service`
  (agent-executed prose, pinned by `test_campaign_interleaved_serial`).

## External-Code-Review-Findings (OpenRouter: GPT)

| Sev | Finding | Disposition |
|---|---|---|
| MED | runner `git fetch origin` unconditional → regresses stacked in origin-less env | **accepted-and-fixed**: sub-iterate-runner.md fetch now serial/remote-base only |
| HIGH | `cmd_next` `independent` still hardcodes `"main"` | **rejected-with-reason**: `independent` is legacy/out-of-scope; the `"main"` predates this change; touching it risks legacy behavior |
| MED | composition test asserts literal `origin/main` | **rejected-with-reason**: fixture default IS main; non-main generality covered by `test_serial_respects_non_main_default_branch` |
| MED | `test_no_end_stage_drain` only checks string absence | **rejected-with-reason**: positive merge-ordering already pinned by `test_merge_is_inside_the_loop_and_ci_green_gated` |
| MED | intro prose `origin/main` vs contract `origin/<default>` | **accepted (minor)**: contract sections precise; intro keeps readable `origin/main` |

## External-Plan-Review-Findings (OpenRouter: GPT + Gemini)

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | HIGH | Prose-only "fresh main" → stale-base regression | **accepted-and-fixed**: AC1 — serial base = freshly-fetched `origin/<default>` in code |
| 5 | MED | Hardcoded `"main"` assumes default branch | **accepted-and-fixed**: AC1 resolves `origin/HEAD`, fallback `origin/main` |
| 7 | MED | AC5 must prove content composition, not base string | **accepted-and-fixed**: AC5 now a real-git composition test |
| 4 | HIGH | Non-green outcomes stall serial; undefined | **accepted-and-fixed**: AC3 strict-stop + CI-wait prose |
| 2 | HIGH | All `branch_strategy` readers must accept serial | **accepted-and-fixed**: AC7 required reader sweep + persisted-load test |
| 3 | MED | Doc sweep required not optional | **accepted-and-fixed**: AC7 grep stacked/drain across docs/fixtures |
| 6 | MED | Existing `stacked` campaigns resume unchanged | **accepted**: stacked untouched in `cmd_next`; `test_stacked_provides_base_branch` retained |
| 9 | LOW | Per-iteration merge must keep CI-green gate | **accepted**: `watch_pr_delivery` (merged+green) applies per sub-iterate |
| Gemini | MED | In-`cmd_next` open-PR guard | **rejected-with-reason**: state machine must not query GitHub; `record→merge→watch-delivered→next` already enforces one-at-a-time |
| Gemini | LOW | `ensure_current` skip when serial | **rejected-with-reason**: already a no-op (branch off fresh `origin/<default>` isn't behind); wrong layer |
| 8 | MED | Externally-merged-PR race | **rejected-with-reason**: fetch-before-next reconciles; one-PR-at-a-time makes it rare/benign |
| 10 | LOW | Don't over-abstract the new value | **accepted**: serial added only where orchestration needs it; semantic table added to campaign-mode.md |

## Out of scope

- Removing `stacked`/`independent` code values (kept for back-compat; build uses them).
- Changing `ensure_current.py` / `integrate_main` (the F11 refresh-if-behind
  guard stays as a general per-iterate mechanism, harmless no-op under serial).
- Auto-advancing `main` inside `autonomous_loop` (orchestrator/prose owns it).
