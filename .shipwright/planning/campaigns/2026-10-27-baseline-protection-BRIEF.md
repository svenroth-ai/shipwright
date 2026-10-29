# Baseline protection (BP): no unplanned change to an existing FR merges unseen

> **STOPPED 2026-10-29 (operator decision after BL0b).** The campaign `baseline-protection` is cancelled. BL0 (PR #940) and BL0b (PR #946) were delivered and merged as measurements; BL1 to BL6 will NOT run and nothing in this brief is to be executed. Reason: the measurement (`2026-10-27-baseline-protection-BL0B.md`) shows that inferring touched FRs from the code gives too much noise (R-precision, R-cost fail) and too little recall to gate on, whichever source is used. The goal itself (no unplanned change to an existing FR slips through, with little friction) stands. A successor campaign will be planned after the options have been worked through with Opus. The campaign board was deleted (no cancelled status exists). Sections below describe the stopped plan and are kept as the record of what was measured and why.

**Stand:** 2026-10-27, rev 3 (rev 1 → internal Opus plan, architecture and doubt review + external GPT + GLM plan and architecture review, all "revise"; operator decisions of 2026-10-27; rev 2 → second Opus plan review, "revise"; §9) · **Origin:** operator conversation 2026-10-25/27 ("change 199 must never alter change 78's business logic unnoticed") · **Programme:** `2026-10-25-deterministic-first-programme-BRIEF.md` §2.1 (BP is the start condition of every plugin campaign there)
**Execution:** autonomous campaign, `branch_strategy: serial` with `depends_on` edges, no parallel units. Two operator stops (§5). Models per programme §2.4: `--finalization-model sonnet`, `--review-model opus --plan-review-model opus`.
**Naming:** the campaign is "BP"; its units are `BL0..BL6`, because `BP-1`/`BP-2` already label the FR-classification gates (`shared/scripts/lib/fr_classification.py:3,33`).

**Start conditions:**
1. This brief and the programme briefs committed to `main` through an iterate.
2. No open unit of run campaign U or of the announced run-plugin fix campaign names a file in a touch set below (expected overlap: `ci.yml`, `verify_local.py`, `campaign-mode.md`, `pyproject.toml`; checked at start and before each unit).
3. Plugin cache synced and checked (`check_plugin_cache_sync.py --strict`). BP syncs **only** at the two points of §6.
4. BP's own `scope_frs` (the FRs of the delivery, finalization and CI-gate machinery it changes) are proposed by BL0 and approved at stop 1; until then its shadow runs report BP's own PRs as out of scope, which is expected.

---

## 0. The guarantee, stated honestly

**What BP guarantees after BL6:** a PR that changes an existing FR, and whose scope the operator has not approved for that FR, does not merge automatically; it waits for the operator. "Changes an FR" means: its normative text or an AC changed (T-spec), a test bound to it changed (T-test), or code that its bound tests execute changed (T-code, §2). Changes inside an approved scope merge as today and are listed in the PR.

**Approved scope** comes only from places the runner cannot write in the same PR: a campaign brief on `main` at the merge base, or an operator label on the PR (§2). A single iterate therefore has an empty scope unless the operator labels it, so every iterate that touches an existing FR is held once; BL0 measures how often that is.

**Disclosed limits** (kept in the brief and in the ADR):
- T-code sees only Python code inside the measured coverage targets, run by the test tiers CI runs per PR. It does not see: code no FR-bound test executes; tests marked `slow` or `cross_plugin` (skipped in CI's shared tiers); code reached only through spawned subprocesses; JS/TS.
- **Behaviour that lives in prose, shell and configuration** (`SKILL.md` and references, `hooks.json`, `validate_command.sh`, JSON config) is outside T-code. In this repository that is a large share of FR behaviour. It is protected only where a test bound to the FR reads it (T-test) or the FR text changes (T-spec). The plugin conversion programme shrinks this blind spot plugin by plugin, because it moves mechanics from prose into code.
- The agent and the operator share one GitHub identity (`svroch`). The hold stops **automation** (auto-merge, the campaign merge, the guarded commands); a PreToolUse guard refuses the obvious bypasses, but it cannot stop an agent that works around it deliberately, and Codex runs have no plugin guard. CI is the authoritative check.

## 1. Facts BP builds on (verified 2026-10-27 by an exploration pass and six reviews)

Kept as they are: the **keystone AC gate** (`check_keystone_ac_gate.py`, ci.yml:417-442; derives changed ACs from the spec diff, rejects author declarations as forgeable, docstring :27-31; "code-to-spec" out of its scope, :12-17), **orphan AC binding** (ci.yml:509-522), the **AC ratchet** (ci.yml:444-507, F0 mirror `check_ac_ratchet_f0.py`), the **write-time FR gates** (`fr_gates.py:180,240-253`).

Missing or limiting:
1. Nothing compares what a diff touches with anything approved. `check_spec_impact_recorded` (`iterate_checks.py:556-640`) passes `none` on its justification alone, `add/modify/remove` if any planning `spec.md` was touched, and skips intents other than feature/change/bug (:587-592).
2. An edited test body under an unchanged AC is advisory only (`check_test_body_suspects.py`, exit 0), by a ratified ruling: "may never become a hard gate" (`:20-37`, ci.yml:533-546, P3.8). **BP supersedes it for out-of-scope FRs only**, as a hold, so "a human decides" stays true; ratified at stop 1, named in the BL6 ADR drop.
3. Normal auto-merge has no proof the verifier passed on the merged commit (`deliver_pr.py:206`; only rung 3 pins and re-verifies, `pr_self_merge.py:145-200,239-240`). Campaign units never arm; the orchestrator merges in `campaign-mode.md:1428` on the review's `shipped_head`. Two paths push new heads without re-verifying: `watch_pr_delivery` → `refresh_branch` → `ensure_current` (`pr_readiness.py:62`) and campaign step 3f-bis (`campaign-mode.md:1041-1084`).
4. `assertion_weakening.py` runs only for `fix-main-*` (ci.yml:272-301), reports a changed assertion as review-only (`:1573-1581`), compares mark names, not decorator arguments (`:1265,1328-1358`).
5. `scan_test_hygiene.py` is prose-only; its Python leg is file-scoped and always flags `skipif` (`test_hygiene.py:422-442`), needs `origin/HEAD`, passes silently on a git error (`:139-140`).
6. `fr_impact {FR: add|modify|remove|none}` exists on `work_completed` (`record_event.py:613`). `fr_tag_grammar.parse_python` misses module/class `pytestmark`; `tools/verifiers/_tag_binding_py.py` handles it.
7. **Coverage today cannot attribute:** `pyproject.toml:89-92` and `combine_coverage.py:63` omit `*/tests/*` (fixtures, conftest, helpers); `combine_to_xml` keeps only `coverage.xml` (no contexts); plugin tiers measure `--cov=scripts` from the plugin directory, shared and integration tiers `--cov=shared` (ci.yml:137-140,194,211), so cross-tier execution is not attributed; plugin test ids collide across plugins once combined.
8. `ci.yml` triggers on bare `pull_request:` (no `labeled`); the top-level token is read-only (`test_workflow_token_permissions.py` pins it).
9. Not measured: the verifier's wall-clock; the cost of per-test contexts; how many FRs a typical changed function is attributed to.

Precedents: ADR-266 rejected a mis-classification detector (68 of 92 false positives) and removed a rate-based FR-tag gate (94 % false fires). **Derive from the diff, never from a declaration, and measure false holds on real history before anything blocks.**

## 2. The model

**Touched set (derived, never declared)**, from the merge-base diff (three-dot; in the replay, the squash commit's first parent):
- **T-spec:** an FR whose normative text changed: statement or AC (keystone's AC digest). Ignored: status and promotion, Layers and `(inferred)` markers, evidence markers, AC-id tokens. FR rows from the catalog sources (`collect_known_fr_ids`, `fr_gates.py:46`).
- **T-test:** an FR bound to a modified or deleted test. Bindings from `_tag_binding_py` (module and class marks inherited; a module-mark FR counts only if the mark or a test inheriting it changed) and the manifest's runtime ids (parametrize instances). A changed decorator argument or parametrize case is a modification.
- **T-code (operator decision 2026-10-27):** an FR whose bound tests execute a changed line, from per-test coverage contexts. Production code via a **context run** (BL2) that keeps each tier's `.coverage` database, prefixes every context with its test root, and measures `shared` plus the plugin's `scripts` in every tier. Test-dir code (fixtures, `conftest`, helpers), which coverage omits, by static attribution: a fixture → the tests that request it; a `conftest.py` → the tests in its directory scope; a helper module → the test modules that import it. A pure deletion is attributed through the enclosing function: its surviving lines in head coverage, or, if the function is gone, the latest `main` run's context artifact.
- **Broad changes:** a changed function attributed to more than **N** FRs is **listed, not held** ("shared helper, 34 FRs"). N is set at stop 1 from BL0's measurement; without it, one line in a widely used helper would hold every PR (the ADR-266 pattern).
- **Fail closed:** missing contexts, fewer tiers reporting than at the base, or an unreadable artifact → held with the reason "baseline evidence incomplete". A PR cannot pass by starving its own coverage.
- **Moved, not touched:** identical normalized AST body including decorator arguments, same bindings, only relocated or renamed; detected by content. Listed in its own PR section. This is the re-anchor of programme §2.1 (operator decision 2026-10-27, variant A), made mechanical.
- **New FRs** (absent at the merge base) are never "existing".

**Approved scope (only from places the PR cannot write):**
- a campaign brief's `scope_frs` (per unit or campaign-wide), read from `main` at the merge base;
- operator labels on the PR: `baseline-scope:FR-xx.yy` (an FR approved for this PR) or `baseline-approved` (everything currently touched approved).
- Scope recorded inside the PR (events, `fr_impact`) is displayed as "agent-recorded", never trusted.

**Approval lifetime.** An approval binds to the **digest of the touched set** at the time it was given, not to a SHA. On a new push, the `Baseline` job recomputes; if the digest is unchanged (e.g. `ensure_current` merged `main` in), the approval carries over; if it changed, the job removes the labels and holds again. The job records the approved digest in its JSON artifact and in a PR comment it writes itself (`pull-requests: write` at job level, pinned in `test_workflow_token_permissions.py`). A label counts only if it was added after the head it applies to was pushed (timeline API).

**Consequence.** Non-empty `touched ∩ existing ∖ (scope ∪ moved ∪ broad)` → the `Baseline` check is red with a plain-language list ("FR-78: `test_price_rounding` changed; FR-78 is not in this unit's scope"). The guard refuses the agent's label commands and hand-posted statuses. In a campaign, step 3g reports **"held for baseline approval: FR-.."** as its STRICT-STOP reason (not the generic checks failure) and resumes the unit after the operator's label; other campaigns are unaffected.

**R3:** `spec_impact: none` or `fr_impact[X] = none` with a T-spec change on X is an error (pure consistency).

**R5 (verifier bound to the merged commit):** `verify_iterate_finalization.py`, on exit 0 and only after asserting the working tree is clean and equals the SHA, posts the commit status `shipwright/finalization-verifier` (precedent: the `PR Review` status). Every path that pushes a new head re-runs it: F11, `watch_pr_delivery`/`refresh_branch`, campaign 3f-bis. `deliver_pr.py` refuses to arm without the status on `headRefOid`; 3g requires it on `shipped_head`. The operator makes it required at BL6. PR classes that never run the verifier (release, layer promotion, manual) get the rule stop 1 decides.

**Weakening and hygiene:** report-only (BL5), a PR-summary section on every PR. A weakening in a test bound to an out-of-scope FR is already T-test.

**Where it runs.** Library in `shared/scripts/tools/verifiers/_baseline_touch_*.py` (spec, binding, coverage, scope; ADR-044/045), CLI `shared/scripts/tools/check_baseline_lock.py`. CI: its own workflow `baseline.yml` (`types: [opened, synchronize, reopened, labeled, unlabeled]`, `actions: read` for artifacts), running the checker **from a detached worktree of the base revision** (`git worktree add --detach`), with `--mode shadow|block` in the workflow file (one-line kill switch). On `labeled`/`unlabeled` it reuses the touched set from the latest run's artifact instead of re-running coverage. Bootstrap: if the checker does not exist at the base (BL3's own PR), the job reports "not yet active" and exits 0. The `(shadow)` step exits 0 by mode, never via `continue-on-error`. Locally: a separate, intent-independent verifier check (WARNING in shadow, ERROR in block), and an F0 **preview** ("these FRs are outside your scope; the PR will be held"), labelled non-authoritative. Registered in `verify_local.CI_ONLY_GATES` with its reason.

## 3. Units

| id | Unit | Touch set | depends_on | Cx |
|---|---|---|---|---|
| **BL0** | Library (T-spec, T-test, moved) + L1 tests; measured: verifier wall-clock (5 iterates), context-run cost on two roots, attribution fan-out (FRs per changed function) and a proposal for N; PR-class inventory over the last 100 merged PRs; replay of T-spec + T-test over those PRs and of T-code over 20 of them (context runs at their merge base), against their historical `fr_impact` (fallback `affected_frs`, else "none"); hold rate per PR class under the scope rule; **mutation probes** in 5 historical PRs (which source notices a seeded production change); labels `correct-harmful` / `correct-benign` (friction) / `wrong`; BP's own `scope_frs` proposal | new `shared/scripts/tools/verifiers/_baseline_touch_*.py` + tests; new `shared/scripts/tools/replay_baseline_lock.py`; report `.shipwright/planning/campaigns/2026-10-27-baseline-protection-REPLAY.md` | - | large |
| **BL1** | Scope read side: `scope_frs` in the campaign-brief template and `campaign-mode.md` (one paragraph); label parsing; approval digest; R3 against `fr_impact`. **Then cache sync 1** (§6) | campaign-brief template, `campaign-mode.md`, `verifiers/_baseline_touch_scope.py` + tests, `fr_classification.py` (R3 only), hooks doc | BL0, stop 1 | medium |
| **BL2** | Context run: per-tier `.coverage` kept as an artifact, contexts prefixed by root, `shared` + plugin `scripts` measured; static test-dir attribution; deletion attribution; fail-closed rules | `.github/workflows/ci.yml` (coverage steps), `pyproject.toml` (context run config only; the existing omit stays for the diff-coverage gate), `shared/scripts/tools/combine_coverage.py`, `verifiers/_baseline_touch_coverage.py` + tests | BL0 | large |
| **BL3** | `baseline.yml` in shadow: CLI, base worktree, bootstrap, `--mode`, label rules and approval digest, comment, summary + JSON artifact, collector (`replay_baseline_lock.py --from-ci-runs`); the verifier check; F0 preview; guard lines (labels, statuses, `gh pr merge` on a held PR); 3g "held" reason and resume; seeded S1-S12, S15-S17 | new `check_baseline_lock.py`, new `.github/workflows/baseline.yml`; `test_workflow_token_permissions.py`; `iterate_checks.py` (new check only); `verify_local.py` (`CI_ONLY_GATES`); `test_verify_local_ci_drift.py`; `validate_command.sh` + tests; `campaign-mode.md` (3g); F0 reference (one line); hooks doc | BL1, BL2 | large |
| **BL4** | R5: verifier posts its status after the clean-tree check; re-run on every re-push (F11, `watch_pr_delivery`/`refresh_branch`, 3f-bis); `deliver_pr.py` and 3g require it; live checks: push after arm, already-mergeable PR; seeded S13, S14, S18 | `verify_iterate_finalization.py`, `deliver_pr.py`, `watch_pr_delivery.py`, `lib/pr_delivery_host.py`, `lib/pr_readiness.py` if needed, `campaign-mode.md` (3f-bis, 3g), `validate_command.sh`, tests; F11 (one line) | BL3 | medium |
| **BL5** | Weakening and hygiene report-only: a separate module for decorator arguments and `assertion_changed`; `scan_test_hygiene` with `--base-sha`, a line-scoped Python leg, fail-closed on git errors; `(shadow)` steps into the PR summary | new `shared/scripts/lib/assertion_weakening_args.py`; `scan_test_hygiene.py`, `test_hygiene.py`; ci.yml; `verify_local.py`; tests | BL3 | medium |
| **BL6** | Flip: `--mode block`; the operator makes `Baseline` and `shipwright/finalization-verifier` required (an operator action at stop 2); `(shadow)` → `(gate)` in ci.yml, `verify_local.py`, the drift test; required-checks drift tooling (`required_checks_drift.py`, `check_required_checks.py`); guide ch. 8, glossary (Baseline hold, Approved scope, Moved test; replace, not only add), conventions; ADR drop (P3.8 supersession, the §0 limits) | the files named; docs; decision drop | BL4, BL5, stop 2 | small |

## 4. Seeded regressions (each in its owning unit; L2; all required before BL6)

| # | Change | Expected |
|---|---|---|
| S1 | edit an assertion in an FR-01.09 test, scope without FR-01.09 | held, FR-01.09 named |
| S2 | the same, FR-01.09 in the brief's `scope_frs` | passes, listed |
| S3 | move an FR-01.09 test, body identical | passes as "moved" |
| S3b / S3c | move it and change an expected value / a parametrize case | held |
| S4 | test in a module with a module-level `covers` mark edited | held for that module's FRs only |
| S5 | change a fixture requested only by FR-01.09 tests, out of scope | held (static test-dir attribution) |
| S6 | change production code executed by FR-01.09 tests, out of scope | held (T-code) |
| S7 | change production code executed by no bound test | passes; listed "unattributed" (disclosed limit) |
| S8 | FR status promotion / Layers marker / AC-id mint, text unchanged | passes |
| S9 | AC text of FR-01.09 changed with `spec_impact: none` | R3 error |
| S10 | release PR, layer-promotion PR | the rule stop 1 decided |
| S11 | a PR that loosens `check_baseline_lock.py` itself | judged by the base checker, held |
| S12 | `baseline-approved`, then a push that changes the touched set | label removed, held again |
| S13 | arm auto-merge, then push | not merged: status missing on the new head |
| S14 | campaign 3g with a `shipped_head` lacking the verifier status | refused |
| S15 | a PR that disables `--cov-context` or marks bound tests `slow` | held: evidence incomplete |
| S16 | `baseline-approved`, then `ensure_current` merges `main` in, touched set unchanged | approval carries over |
| S17 | delete a line of production code executed by FR-01.09 tests | held (deletion attribution) |
| S18 | refresh push by `watch_pr_delivery` | verifier re-run, status on the new head |

## 5. Operator stops

1. **Stop 1, after BL0:** the replay report with base rates (PRs with a non-empty touched set, PRs carrying `fr_impact`), the hold rate per PR class, the T-code fan-out and the proposed N, the mutation-probe results, labels per hit, and a **random sample the operator re-labels**. Decisions, each in plain language: N; the rule per PR class (release, layer promotion, revert, manual); BP's own `scope_frs`; the P3.8 supersession; per source at most 3 `wrong` per 100 PRs, else that source is redone before BL1; if the replay shows no `correct-harmful` hit and the probes show nothing is noticed, the operator decides whether BP proceeds.
2. **Stop 2, before BL6:** the shadow log from the collector, counted from cache sync 1: at least 10 PRs with a non-empty touched set, at least one Codex-driven iterate if any ran; the **hold rate** (share of PRs that would have been held) and the friction rate, each against a threshold the operator sets at stop 1. Flip preconditions: no campaign active in `loop_state` (drain announced), cache sync 2, the operator sets the two required checks.

## 6. Cache sync points

The tools BP changes run from `~/.claude/plugins/cache` (and the Codex install). The campaign syncs exactly twice: after BL1 (the shadow clock starts here) and before BL6. Each sync: `update-marketplace.sh`, `check_plugin_cache_sync.py --strict`, Codex bundle rebuilt. Programme P14 otherwise applies.

## 7. Not in BP (own briefs later)

- The gates in the target-project CI templates.
- Mutation testing per FR as a scheduled report.
- Blocking unbound test weakening and hygiene findings (only if the shadow data shows a need).
- Per-test coverage for JS/TS, subprocess-spawned tests, and the `slow`/`cross_plugin` tiers.
- Attributing prose, shell and config to FRs (the plugin conversions reduce this instead).

## 8. Repo rules for every unit

As in the pilot brief §6: docs in the same diff; new files at most 300 lines; one pytest root per process; in-process L1 tests; `uv run scripts/verify_local.py` and `uvx ruff@0.15.15 check .` before push; tests tagged with FR/AC minted by the producers; review cascade with `model=opus`; a unit red twice is released with its dependents; anything needing an operator answer between stops = STRICT-STOP.

## 9. Review log

**Rev 1** reviewed by: internal Opus plan review (revise; 2 blockers, 6 high), internal architecture review (revise; 3 high), internal doubt review (4 high, 9 medium), external plan review GPT + GLM (both revise), external architecture review GPT (revise) + GLM (approve). Integrated in rev 2:
- The declaration is no longer load-bearing (all five): the derived touched set is compared with an approved scope, and the consequence is a hold for the operator (operator decision 2026-10-27).
- The production-code gap is closed where tests reach (doubt D1; operator decision 2026-10-27).
- Re-anchor made mechanical (doubt D4, GPT); `fr_impact` reused (plan B1, doubt D12); bindings from `_tag_binding_py` and the manifest (plan B2).
- Checker from the base revision (plan H2, doubt D13); nothing read from the PR body (plan H3, doubt D3, GLM, GPT).
- Normative-only spec digest, catalog rows, PR classes (plan H4, doubt D5); R5 as a per-SHA status (doubt D9, plan M6, GPT, GLM); hygiene and weakening report-only (plan H5, doubt D6, D7); cache sync points and drain (plan H6, doubt D10, D11); kill switch (GLM, GPT); separate verifier check, `CI_ONLY_GATES`, `(shadow)` naming, BL6 touch set (plan M1-M3, doubt D8, D18, D19); shadow artifact, collector, thresholds, operator re-labelling, mutation probes (plan M4, L2, doubt D14); P3.8 named (architecture, plan M9); seeded regressions per unit (plan M8, doubt D16, GLM).
- Not taken: "only print the touched set" (the operator chose holding); "no separate re-anchor category" (kept, it costs nothing once mechanical).

**Rev 2** reviewed by a second Opus plan review (revise; 3 blockers, 4 high). Integrated in rev 3:
- T-code made feasible against today's coverage: a context run that keeps per-tier databases, prefixes contexts by root and measures `shared` plus plugin `scripts`; static attribution for fixtures, `conftest` and helpers, which coverage omits; deletion attribution (B1, B2, M1).
- Label approval: own workflow with `labeled`/`unlabeled` triggers, labels valid only if added after the head was pushed, approval bound to the touched-set digest so refresh pushes keep it, artifact reuse on label events, token permission pinned (B3, H1).
- R5 re-run on every path that pushes a new head (`watch_pr_delivery`, 3f-bis), with a clean-tree check before posting (H1).
- Iterate scope only from operator labels or a brief on `main`; agent-recorded scope displayed, never trusted; single iterates therefore held once when they touch an existing FR, and BL0 measures that rate (H2).
- Fail closed when coverage evidence is missing or shrinks (H3, S15).
- Broad-change rule with N from BL0's fan-out measurement, T-code replayed over 20 PRs, hold-rate threshold at stop 2 (H4).
- Base revision as a detached worktree, bootstrap rule (M2); the 3g "held" reason and resume (M3); §0 discloses prose, shell, config, `slow`/`cross_plugin` and subprocess blind spots (M4); BP's own `scope_frs` (L1); required-checks drift tooling in BL6 (L2); no `continue-on-error` (L3).

Rev 3 has not been reviewed again. The remaining open points are implementation detail for each unit's own plan review; the design questions are settled by the operator decisions and stop 1.
