# t0 — Seam survey: FR cluster → existing test boundary

> Campaign `req3-05-test-backfill-mono`, sub-iterate **t0** (seam-survey, BLOCKING,
> read-only, no ACs of its own). This is the ONE repo-wide answer to "which existing
> seam does a backfilled test for FR-01.NN attach to" that t1–t9 cite instead of
> re-deciding. Cite a row; do not re-argue the seam for a cluster this table already
> covers. Re-derive the AC-count columns from `shipwright_ac_coverage_baseline.json`
> before trusting them — this table is a snapshot at survey time (2026-09-11), and the
> baseline shrinks as t1–t9 land.
>
> **Placed here, not under `.shipwright/planning/iterate/campaigns/req3-05-test-backfill-mono/`,
> deliberately:** that directory is gitignored (`.gitignore` line ~263 — "campaign planning
> dirs are local-only operational planning, not durable product artifacts"), so a file placed
> only there would never reach `origin/main` and would vanish with the worktree. This survey is
> the shared reference every later unit cites — it needs git-history durability, unlike
> `campaign.md`/`status.json`. A one-line pointer stub was ALSO written directly to
> `.shipwright/planning/iterate/campaigns/req3-05-test-backfill-mono/seam-survey.md` for
> in-worktree discovery, and `campaign.md` itself now carries a one-line pointer too — but
> **neither is visible in this run's diff** (both paths are gitignored, so no diff can ever
> show them; external code review, glm, medium, correctly flagged that the diff alone cannot
> verify this claim). Confirm they exist on disk if you need to rely on them from a different
> tool than this file.
>
> **Scope note (external plan review, openai, high — see External-Plan-Review-Findings
> below):** t0's own sub-iterate spec states "ACs in this unit: n/a (survey unit)" and
> "Test root(s): all roots (read-only)," yet the spec's boilerplate Acceptance Criteria block
> (identical, word-for-word, in every t1–t9 spec — it is a shared template, not tailored per
> unit) reads as if t0 must itself regenerate the baseline and produce green tests. It cannot:
> a survey with no AC cluster of its own has nothing to bind. This document, not a baseline
> regen or a test file, is t0's deliverable, per the orchestrating campaign's own framing of
> this unit. The mismatch between the generic checklist and t0's actual (narrower) mandate is
> a spec-authoring gap worth fixing when campaign.md's sub-iterate specs are next touched, not
> something t0 should paper over by inventing binding work outside its read-only scope.
>
> **Rejected-with-reason (external code review, openai, high — "regenerate the baseline or
> obtain a spec amendment"):** t0's `FR cluster:` field in its own spec is literally `-` — it
> has no AC ids to bind and no baseline entries of its own to touch. "Regenerate the baseline"
> presupposes a cluster t0 does not have; running the regenerator now would do nothing (t0
> changed zero source/test files) and would misrepresent a no-op as evidence of work. The
> `run_id`/spec citation IS the record that this reading was deliberate, not an oversight.
>
> **Where the "recorded reason" for THIS document's own no-seam ACs lives (external code
> review, glm, medium):** the two Named Exceptions below, for the specific AC ids listed in
> their tables (FR-01.12 AC01's precondition/AC02/AC03/AC07/AC09; FR-01.15 AC02/AC03/AC06),
> ARE that recorded reason — t8 and t9 should cite this survey by section (not re-derive a
> reason) when they record those exact AC ids as unbound-with-reason at their own baseline
> regeneration, and should link back to it (a decision-drop reference or a spec.md-adjacent
> comment naming this file) so the reason survives past this PR the way Finding 5 says it must.

## Method (reproducible)

1. FR titles + AC text: `.shipwright/planning/01-adopted/spec.md` (`### FR-01.NN — <title>`
   headings, `[ACnn]` bullets).
2. AC total / unbound / bound counts per FR: cross `shipwright_ac_coverage_baseline.json`
   (`unbound` list) against the AC ids minted in spec.md.
3. Existing precedent: `grep -rn 'covers("FR-01\.NN/AC` across the tree — every FR/AC pair
   that is **already bound** shows, by its own file's path, which test root and module the
   framework itself already uses to prove that FR's behavior. Precedent beats guessing.
4. Owning implementation module per unbound AC: read the AC text against
   `plugins/<name>/scripts/` and `shared/scripts/{lib,tools}/` to find the real
   deterministic surface (not just the FR's nominal plugin title — see Finding 1 below).
5. Test-root inventory: `plugins/*/tests`, `shared/tests`, `shared/scripts/tests`,
   `shared/scripts/tools/tests`, `integration-tests` (the five ADR-044 roots; ONE per
   pytest process, `--junitxml` per root — CLAUDE.md, repo-root `conftest.py` exit 4).

**Caveat (external plan review, openai, medium):** the precedent evidence above is
`grep`-derived, not execution-derived — it shows a `@pytest.mark.covers(...)` decorator
exists in a file under a given root, not that pytest currently collects and passes it from
that root. t0 spot-checked one (`shared/tests/test_phase_history.py`, `--collect-only`,
18 tests collected clean under `shared/tests` — confirming that root/precedent pair), but did
not re-run all ~40 precedent files cited below. **Before trusting a DIFFERENT precedent row,
run a private, uncommitted `uv run pytest <root>/<file> -q --collect-only` spot-check first**
— this is a local confidence probe only, throwaway, and is NOT a substitute for, and does not
relax, the binding ADR-044 rule that the unit's real, evidence-bearing test run is one pytest
invocation per root with its own `--junitxml` (external code review, openai, medium: an
earlier draft of this caveat could have been misread as licensing a second, junit-less
invocation as part of the recorded run — it does not; run the spot-check, throw it away, then
run the real `--junitxml` invocation once per root as ADR-044 requires).

**Known false-positive source (Stage-2 code review, medium):** the `grep` in step 3 above
will match `shared/scripts/tools/tests/test_backfill_ac_provenance_*.py` (e.g.
`test_backfill_ac_provenance_cli.py:91,116,128,129,168`,
`test_backfill_ac_provenance_apply_skips.py:36,41,44,46,89`) — these contain literal
`covers("FR-01.NN")` / `covers("FR-01.NN/ACnn")` strings as the backfill tool's OWN test
fixture data (source text the tool rewrites, and decoy strings inside docstrings/comments/
assertions it must NOT touch), not real `@pytest.mark.covers` bindings on tests the file
itself is collected under. Do not count a hit in this file as precedent for any FR/AC pair;
t1-t9 should skip it when scanning grep output rather than each rediscovering this by hand.

## Key findings (read before using the table)

**Finding 1 — the FR's plugin title is not always its test root.** campaign.md's framing
("every FR-01.xx maps 1:1 onto a plugin … so the FR cluster IS the test seam") holds for the
*majority* of ACs, but the already-bound precedent falsifies it as a universal rule: FR-01.01
(titled `/shipwright-run`) has its one bound AC (`AC08`, phase-history-note freshness) proven
across a dozen files entirely under `shared/tests/` (`test_phase_history.py`,
`test_c3_cross_phase_verdict.py`, `test_completion_writers*.py`) because the behavior — the
phase-history join — is implemented in `shared/scripts/lib/`, not in
`plugins/shipwright-run/scripts/`. Likewise FR-01.11's two bound ACs (`AC17` merge-state,
`AC18` silent-revert) live in `shared/tests/test_pr_blockers_merge_state.py` and
`shared/tests/test_silent_revert*.py` — shared cross-cutting infrastructure every iterate
calls, not `/shipwright-iterate`-specific code. **Rule for t1–t9: find where the AC's
behavior is actually implemented (grep the verb of the AC against `shared/scripts/lib`
first, then the plugin's own `scripts/`) before picking a root — do not default to
"my FR's plugin dir" without checking.**

**Finding 2 — almost the entire backlog is virgin ground, not a backlog of near-misses.**
Of 259 unbound ACs, only 4 FRs have ANY existing AC-level binding at all (FR-01.01: 1/8 bound,
FR-01.07: 4/18, FR-01.11: 2/29, FR-01.13: 2/8) — every other FR is 0% bound. There is no
"finish the last few" pattern anywhere; every unit is greenfield backfill against whatever
seam already exists for that behavior (a `tests/` dir, a CLI harness, a fixture corpus), not
against an existing partial AC-tag pattern to extend.

**Finding 3 — the binding idiom is settled and repo-wide.** Every existing AC-level bind uses
`@pytest.mark.covers("FR-01.NN/ACnn")` (the `covers` marker is registered once, root
`pyproject.toml`, applies to every ADR-044 root). `shared/scripts/lib/fr_tag_grammar.py` is
the parser; a bare `covers("FR-01.NN")` (no `/ACnn`) does not bind a specific AC and will not
clear this baseline. **Every backfilled test MUST use the `/ACnn`-qualified form.**

**Finding 4 — two named exceptions have no existing deterministic seam at all** (see below):
FR-01.12 (`/shipwright-preview`) and, partially, FR-01.15 (cross-repo output contract).

**Finding 5 — the baseline JSON has no field to hold a "recorded reason" (external plan
review, glm, medium).** `shipwright_ac_coverage_baseline.json` (`schema_version: 1`) is a
flat `unbound: [ "FR-xx/ACnn", ... ]` list — set membership only, per
`shared/scripts/tools/check_ac_coverage_ratchet.py`'s own docstring. The per-unit exit
condition ("or is recorded with a reason why it cannot be proven at an existing seam") has
nowhere machine-checkable to live: today that reason can only live as spec-adjacent prose (a
decision-drop, or a comment beside the AC in `spec.md`), which is exactly the "rots into
someone wrote a paragraph once" risk the external review named. **t0 does not fix this** — a
baseline schema change is out of scope for a read-only survey — but t1–t9 should be aware:
when you record a no-seam reason, put it somewhere a later reader (or a future automated
check) can actually find it again (the AC's own line in `spec.md`, or a decision-drop titled
with the FR/AC id), not only in a PR description that gets buried.

**Finding 6 — some existing `covers(...)` tags are bare-FR, not AC-qualified (external plan
review, glm, low).** The changelog family (FR-01.09) and a few others carry
`@pytest.mark.covers("FR-01.09")`-style tags with no `/ACnn` suffix (Finding 3's precedent
grep found zero AC-qualified changelog binds despite the FR clearly being exercised by tests).
A bare tag does not bind a specific AC and will not move an entry out of `unbound`. t5 should
either upgrade an existing bare tag to the qualified form where the test already proves that
exact AC, or add a new qualified tag — do not assume the bare tag already "counts."

## Master mapping table

> The **Total / Unbound ACs** column is a snapshot at survey time (2026-09-11) and is
> **non-normative** — re-derive it from `shipwright_ac_coverage_baseline.json` before citing a
> number (external plan review, glm, low: this column will drift stale the moment t1 lands).
> The durable part of this table is the FR → root → harness mapping to its right; that does
> not change as the baseline shrinks.

| FR | Title | Total / Unbound ACs (snapshot, re-derive) | Existing test root(s) | Harness / entry point | Precedent (bound AC, if any) | Sub-iterate |
|---|---|---|---|---|---|---|
| FR-01.01 | /shipwright-run | 8 / 7 | `plugins/shipwright-run/tests` (plugin-owned ACs); `shared/tests` (phase-history / completion-writer ACs — Finding 1) | `plugins/shipwright-run/tests/test_lifecycle_cli.py` (real subprocess CLI over `scripts/lib/orchestrator.py` — the highest E2E boundary this plugin has); `test_orchestrator.py`, `test_phase_state_machine.py` for in-process behavior | `shared/tests/test_phase_history.py` etc. → `FR-01.01/AC08` | t8 |
| FR-01.02 | /shipwright-project | 15 / 15 | `plugins/shipwright-project/tests` | `test_integration.py` (drives `setup_session.py` end to end — the real skill entry point); `test_state.py`, `test_manifest.py`, `test_config.py` for individual ACs | none yet | t6 |
| FR-01.03 | /shipwright-plan | 21 / 21 | `plugins/shipwright-plan/tests` | `test_integration.py` (`setup_planning_session.py` pipeline); `test_review_iterate.py` / `test_review_routing_contract.py` for the external-review ACs (AC02–AC04, AC09–AC13, AC19–AC21) | AC20/AC21 have no deterministic surface (DeepSeek superseded by GLM) — **see Named Exception 6**; AC03/AC11 have no observable artifact — **see Named Exception 8** | t3 |
| FR-01.04 | /shipwright-design | 12 / 12 | `plugins/shipwright-design/tests` | `test_setup_design.py` (design-session pipeline); `test_screen_registry.py` (per-requirement screen mapping, AC01/AC04) | AC10's full claim isn't enforced by production code — **see Named Exception 7** | t3 |
| FR-01.05 | /shipwright-build | 8 / 8 | `plugins/shipwright-build/tests` | `test_integration.py`, `test_setup_implementation.py`, `test_sections.py` / `test_section_builder_contract.py` | none yet | t8 |
| FR-01.06 | /shipwright-test | 18 / 18 | `plugins/shipwright-test/tests` | `test_test_runner.py`, `test_smoke_test.py`, `test_playwright_runner.py`, `test_journey_coverage.py`, `test_boundary_coverage_report.py` (already the plugin's densest suite — attach beside it) | none yet | t4 |
| FR-01.07 | /shipwright-security | 18 / 14 | `plugins/shipwright-security/tests`; `shared/tests` for the shared scan-card/coverage surface (Finding 1) | `test_generate_security_report.py`, `test_gitleaks_*`, `test_coverage_*`; shared: `test_security_scan_card.py` | `shared/tests/test_security_scan_card.py` → `AC04, AC08, AC11`; `plugins/shipwright-security/tests/test_gitleaks_extend_smoke.py` → `AC06` | t4 |
| FR-01.08 | /shipwright-deploy | 15 / 15 | `plugins/shipwright-deploy/tests` | `test_smoke_e2e_cli.py`, `test_rollback_e2e_cli.py` — genuine subprocess E2E CLI harnesses already exist here; prefer them over the narrower `test_validate_deploy.py`/`test_rollback.py` unit files where an AC is itself about the CLI's observable behavior | none yet | t5 |
| FR-01.09 | /shipwright-changelog | 15 / 15 | `plugins/shipwright-changelog/tests`; `shared/tests` for the aggregation/idempotency surface (Finding 1) | `test_integration.py`; shared: `test_changelog_aggregation_idempotency.py`, `test_changelog_aggregation_refusal.py`, `test_aggregate_changelog.py`, `test_changelog_sections_shared.py` | none AC-bound yet (only bare-FR tags found) | t5 |
| FR-01.10 | /shipwright-compliance | 14 / 14 | `plugins/shipwright-compliance/tests` | `test_audit_*` family (Group A–I audits) — pick the audit group file matching the AC's dimension; `test_rtm_generator.py` for traceability ACs | none yet | t7 |
| FR-01.11 | /shipwright-iterate | 29 / 27 | `plugins/shipwright-iterate/tests` (plugin-specific mechanics); `shared/tests` for cross-cutting infra ACs the whole pipeline shares (merge-state, revert-detection — Finding 1); AC08/AC09 need a third root — **see Named Exception 3**; AC12's ordering clause has no seam yet — **see Named Exception 4** | `test_diff_risk_recheck.py`, `test_sub_iterate_runner_*`, `test_classify_complexity.py`, `test_campaign*.py` | `shared/tests/test_pr_blockers_merge_state.py` → `AC17`; `shared/tests/test_silent_revert*.py` → `AC18` | t1 |
| FR-01.12 | /shipwright-preview | 9 / 9 | **No plugin-owned implementation module — see Named Exception 1.** Route through `shared/scripts/tests` for the sub-behaviors it actually orchestrates (dev-server, browser verify) | `shared/scripts/tests/test_browser_verify.py`, `test_detect_frontend_changes.py`; `shared/scripts/dev_server/` has no test dir of its own yet — check before adding one | none yet | t8 |
| FR-01.13 | /shipwright-adopt | 8 / 6 | `plugins/shipwright-adopt/tests` | `test_adopt_evidence_disclosure.py`, `test_skill_md_env_scaffold.py` | → `AC05` (`test_skill_md_env_scaffold.py`), `AC08` (`test_adopt_evidence_disclosure.py`) | t8 |
| FR-01.14 | Triage Inbox | 29 / 29 | `shared/tests` (primary — 86 existing triage test files); `shared/scripts/tools/tests` for the CLI-tool layer (`triage_add.py`, `triage_cli.py`, `triage_repair.py`) — **two ADR-044 roots, one unit** | `shared/tests/test_github_api_artifact.py`, `test_drift_triage_emit.py`, `test_security_triage_emit.py`, `test_performance_triage_emit.py`; `shared/scripts/tools/tests/test_suite_race_triage.py` | AC26 has no deterministic surface — **see Named Exception 5** | t2 |
| FR-01.15 | Cross-repo output contract | 8 / 8 | `shared/tests` — but see **Named Exception 2**: no CLI gate script exists yet, only library-level modules | `shared/scripts/lib/contract_baseline.py`, `contract_skeleton.py`; tests: `test_contract_skeleton.py`, `test_cross_repo_contract_documented.py` | none yet | t9 |
| FR-01.16 | Guided requirement elicitation | 10 / 10 | `shared/tests` (single root — see harness column; code review confirmed AC09 is provable here alone, not a 3rd/4th root) | `shared/tests/test_requirement_elicitation_rigor.py`, `test_requirement_elicitation_discovery.py`, `test_requirement_elicitation_refs.py`; `_elicitation_discovery.py` (shared harness) globs `plugins/*/skills/*/references/*.md` directly from the shared root (see `shared/tests/_elicitation_discovery.py:61`), so AC09's "which capabilities are bound" check across the three invoking surfaces (`shipwright-project`, `shipwright-adopt`, `shipwright-iterate`) is read as doc content from `shared/tests` — it does NOT require running those plugins' own test suites or adding roots | none yet | t6 |
| FR-01.17 | Independent re-check on the code host | 7 / 7 | `shared/tests` — CI/PR-review surface; the "code host" itself cannot run inside a test, so the existing seam treats `.github/workflows/*.yml` content + the gate scripts that decide merge-readiness as the observable boundary | `shared/tests/test_pr_review_convergence.py`, `test_pr_review_fail_closed.py`, `test_pr_review_fork_trust.py`, `test_check_ci_supplychain_*`, `_pr_review_workflows.py` (fixture reading real workflow YAML) | none yet | t9 |
| FR-01.18 | /shipwright-grade | 8 / 8 | `plugins/shipwright-grade/tests` | `test_grade_cli.py` (real CLI entry point), `test_authoritative.py`, `test_negative_fixtures.py`, `test_network_policy.py` (consent-gating ACs) | none yet | t7 |
| FR-01.19 | Recovery of a broken shared branch | 10 / 10 | `plugins/shipwright-iterate/tests` (main-repair mechanics); `shared/tests` for the shared assertion-weakening / size-limit gate (Finding 1) | `plugins/shipwright-iterate/tests/test_main_repair_hooks.py`; `shared/tests/test_assertion_weakening.py`; bloat/size-crossing ACs (AC08) need the anti-ratchet gate tests (`shared/tests` bloat family, see `shared/glossary.md`) | none yet | t9 |
| FR-01.20 | Context-Cost Meter | 6 / 6 | **Three roots**: `shared/tests`, `shared/scripts/tests`, `shared/scripts/tools/tests` — pick per AC by which layer it describes (hook capture vs. session fold vs. CLI summary/statusline) | `shared/tests/test_context_cost_core.py`, `test_context_cost_fold.py`; `shared/scripts/tests/test_track_context_cost*.py`, `test_context_cost_integration.py`; `shared/scripts/tools/tests/test_context_cost_readiness.py`, `test_context_cost_summary.py`, `test_context_cost_statusline.py` | none yet | t9 |

## Quick-decide notes for the multi-root FRs (external plan review, openai, high — partial fix)

Full AC-by-AC seam pre-assignment for all 259 ACs is out of proportion for a BLOCKING survey
unit itself scoped `small` (it would mean t0 doing t1–t9's own classification work up front).
Instead, here is the one-sentence decision rule per FR that already spans >1 root, so the
owning unit spends seconds, not a re-investigation, per AC:

- **FR-01.01** (t8): if the AC is about the phase-history NOTE / freshness / cross-phase
  verdict join, it is `shared/tests` (already proven, AC08). If it is about the pipeline's own
  sequencing, override recording, or one-conversation-mode behavior, it is
  `plugins/shipwright-run/tests` — check `plugins/shipwright-run/scripts/lib/orchestrator.py`
  for the function first.
- **FR-01.07** (t4): if the AC is about a specific scanner's own behavior (gitleaks, Semgrep,
  CodeQL config), it is `plugins/shipwright-security/tests`. If it is about the aggregated
  scan-card shape, coverage comparison, or cross-scanner reporting, it is `shared/tests`
  (proven precedent: `test_security_scan_card.py`).
- **FR-01.11** (t1): if the AC is `/shipwright-iterate`-specific mechanics (complexity
  classification, campaign orchestration, sub-iterate runner contract), it is
  `plugins/shipwright-iterate/tests`. If the AC is about merge-state, revert detection, or any
  mechanic every phase's iterate shares, it is `shared/tests` (proven precedent: AC17, AC18). If
  the AC is about test-suite execution mechanics itself — parallel-vs-serial race handling
  (AC08), or CI/local parity of which shared dirs run (AC09) — it is `shared/scripts/tools/tests`,
  a third root (found during t1's own execution, not surveyed here — see **Named Exception 3**;
  campaign-owner accepted for t1). AC12's ordering clause (independent reviewer runs before any
  outside second opinion) has no existing seam at all yet — see **Named Exception 4**; do not
  bind it to a test that only proves its model-configuration clause.
- **FR-01.19** (t9): if the AC is about main-repair's own decision logic (claim/abandon, filed
  vs. repaired), it is `plugins/shipwright-iterate/tests/test_main_repair_hooks.py`'s
  neighborhood. If the AC is about the test-weakening detector or the size-crossing gate
  itself (assertion strength, bloat ratchet), it is `shared/tests` (`test_assertion_weakening.py`
  and the bloat-gate family — `shared/glossary.md` names the exact modules).
- **FR-01.20** (t9): the three-root split is by LAYER, not by ambiguity — hook-level capture
  (`shared/scripts/hooks/track_context_cost.py`) is `shared/scripts/tests`; session-fold /
  core dedup logic (`shared/scripts/lib/context_cost_core.py`,
  `context_cost_session.py`) is `shared/tests`; CLI-facing summary/statusline/readiness
  (`shared/scripts/tools/context_cost_*.py`) is `shared/scripts/tools/tests`. Read the AC's
  verb (captured? folded? displayed?) to pick the layer.

## Named exceptions (no existing boundary — argued)

### Exception 1 — FR-01.12 (`/shipwright-preview`)

`plugins/shipwright-preview/` has **no `scripts/` directory at all** — the entire capability
is SKILL.md prose executed by the agent, not a deterministic script. The one existing test
file, `test_preview_checks.py`, says so in its own header comment: its helper functions
"mirror the SKILL.md logic" — i.e. the test re-implements the logic it is meant to check
rather than importing the real thing. A test attached there would not prove anything; it
would assert that a duplicate agrees with itself, which is exactly the
non-circumvention violation the campaign header and SPEC 1.4.1 forbid.

**Resolution for t8 — AC-by-AC split (external plan review, both reviewers: make this
concrete rather than deferred)**, from `spec.md` FR-01.12 AC01–AC09:

| AC | What it asks | Bucket | Real seam |
|---|---|---|---|
| AC01 | project running + address handed back on request | **split — record BOTH halves, not just the provable one** (external code review, openai, medium: an earlier draft left this AC's precondition half unaccounted for) | the spawn/URL-return half is real (`shared/scripts/dev_server/spawn.py`); the "at least one build section is complete" precondition is the SAME unimplemented `check_build_ready` as AC02 — record that half with AC02's identical no-seam reason, never let the spawn half's test stand in as proof of the whole AC |
| AC02 | nothing built yet → explains and stops | **no seam** | `check_build_ready` exists ONLY inside `test_preview_checks.py` itself (self-referential) and in SKILL.md prose — nothing else implements it |
| AC03 | missing settings → operator walked through | **no seam** | conversational/agent behavior, no deterministic surface |
| AC04 | already running → reuse, don't start a second | **real seam** | `shared/scripts/dev_server/spawn.py` (`_is_pid_running`) + `health.py` (`_is_port_in_use*`) |
| AC05 | address shown, survives past the conversation, next request reuses it | **real seam** | same `dev_server` health/spawn module pair |
| AC06 | a stranger's process on that address is never reused as this project's | **real seam** | `shared/scripts/dev_server/validation.py` / `health.py` — verify the exact ownership check before citing a line |
| AC07 | failure is investigated and addressed, not merely reported | **no seam** | agent-behavior AC, no deterministic surface to assert against |
| AC08 | a new stack previews without changing the preview capability | **real seam** | `shared/scripts/dev_server/profile_config.py` + `shared/profiles/` — provable by adding/using a second stack profile and asserting no `dev_server` code path changed |
| AC09 | a preview is machine-local evidence only, never a release claim | **no seam** | a policy/documentation guarantee, not an executable behavior |

Do not add a new harness for the "no seam" rows (AC02, AC03, AC07, AC09) — SKILL.md-only
behavior is out of scope for what a pytest seam can prove; record the honest reason per the
per-unit exit condition instead. The "real seam" rows attach under `shared/scripts/tests/`
(already exercising these same `dev_server` modules via `test_browser_verify.py` and
`test_detect_frontend_changes.py`) — **not** `plugins/shipwright-preview/tests/`, and never by
extending the self-referential `test_preview_checks.py`.

### Exception 2 — FR-01.15 (Cross-repo output contract), the gate half

`contract_baseline.py` / `contract_skeleton.py` are real, imported, unit-tested library
modules — a legitimate seam for ACs about the CONTRACT'S OWN SHAPE. But three ACs describe a
**gate that runs on the actual PR diff**, which no `shared/scripts/checks/` script wraps
these modules into today:

| AC | What it asks | Provable now (library unit test) | Residual guarantee NOT provable without a gate script |
|---|---|---|---|
| AC01 | shape published, versioned, alongside the payload | yes — `contract_baseline.py`/`contract_skeleton.py` shape + version fields | — |
| AC02 | comparison against the LAST-published shape fails until version is raised for a breaking change | partially — the comparison FUNCTION can be unit-tested with two synthetic shapes | that it actually RUNS as a merge gate on a real diff — nothing invokes it today |
| AC03 | published shape read from a state the proposed change cannot alter (never a same-PR copy) | no | the git-immutable-base-ref read itself; a library unit test supplies its own fixture text, which cannot demonstrate immutability |
| AC04 | a field becoming optional is a breaking change even though nothing disappeared | yes — same comparison function, one more fixture case | — |
| AC05 | a weakly-observed field (always empty/absent) is stated as a stated weakness | yes — `contract_skeleton.py` fixture provenance | — |
| AC06 | checked against what the reader ACTUALLY fetches, not just what the producer emits | no | requires running the real consuming command and diffing its real stdout — no such harness exists |
| AC07 | the producing capability states plainly that it has an outside reader | yes — `test_cross_repo_contract_documented.py` | — |
| AC08 | the contract binds only this side, not the receiver's behavior | yes — documentation/scope assertion, same file | — |

This is not "no seam is possible" the way Exception 1 is — the library primitives already
exist and a gate script is a normal, buildable extension of them. Per the binding seam rule
("no new harness where one fits"), unit-testing the library directly is not a new harness —
it is the existing one — so t9 should default to it for AC01/04/05/07/08. **For AC02/03/06,
t9 must NOT close them via the library unit test alone** (external plan review, openai,
medium: "do not let t9 claim completion... through library-only tests") — record them with
the specific residual guarantee named above, and file a tracked follow-up (triage card or
decision-drop) for the missing gate script + its CI wiring, naming an owner rather than
leaving the gap only as prose in this survey.

**Concrete machine outcome (Stage-2 code review, medium — the "partially" language above was
ambiguous about the actual `unbound`-list action; stated explicitly here so t9 does not
guess):** for AC02 specifically — despite the comparison FUNCTION being unit-testable today
— **do NOT tag `FR-01.15/AC02`** (i.e. do not remove it from `shipwright_ac_coverage_baseline.json`'s
`unbound` list). The AC's own text asks about the gate *running on a real diff*, which the
library unit test does not exercise; tagging it now would mark the AC bound while its actual
behavior remains unproven. Leave AC02 in `unbound`, citing this section's residual-gate
reason, until the gate script exists and a test invokes it against a real diff. The identical
rule applies to AC03 and AC06 for the same reason (column above: "no" / not provable now).

### Exception 3 — FR-01.11 AC08/AC09 (found during t1 execution, not surveyed here)

This survey's row for FR-01.11 (above) named 2 roots. Executing t1 found that 25 of the 27
unbound ACs fit those two roots, but **AC08** (parallel-vs-serial test-suite race handling)
and **AC09** (CI/local parity of which shared dirs run) do not: their real implementation and
only existing tests — `run_test_suite.py` / `test_run_test_suite.py` and
`test_f0_ci_parity.py` — live in `shared/scripts/tools/tests`, a third, already-canonical
ADR-044 root (listed in `CLAUDE.md` alongside `shared/tests`/`shared/scripts/tests`). This
is the same forced-by-where-the-behavior-lives pattern this survey already accepts for
FR-01.20 (3 roots) and FR-01.14 (2 roots, one of which is this same
`shared/scripts/tools/tests`) — not a new kind of exception, just one this survey's own
per-FR pass did not surface because only 2 of FR-01.11's 27 ACs need it.

**Authorization (corrected 2026-09-11 after a Stage-1 spec-review REJECT on t1's PR #730):**
the first version of this section had t1 amending this survey to grant itself the deviation,
citing t0's recommendation (a) below in the "Flagged deviation" section as if that already
covered t1. It does not: that recommendation, and the campaign-owner confirmation it asks for,
was scoped by t0 to **t4, t5, t8 and t9 only** — the four units the per-FR pass actually
surfaced as exceeding campaign.md's two-root guidance. FR-01.11/t1 was not one of them (this
survey's own row for it named 2 roots), so t1 had no standing recommendation to cite, and a
unit does not get to decide for itself that a campaign-level guideline doesn't apply to it by
editing the document that states the guideline — that call belongs to whoever owns campaign.md,
whatever the guideline's own status turns out to be.

(Clarifying the guideline's own status, so this isn't overstated either way: campaign.md's
"keep it at one or two roots" line is a **cost heuristic the campaign author wrote at cut time**,
not an ADR-044 requirement — ADR-044 only forbids one pytest *process* from spanning multiple
roots, and says nothing about how many roots a unit may touch across several invocations. Root
count is forced by where a cluster's behavior actually lives, as Finding 1 already established;
that was always the right substantive answer. What was missing was not a rule violation to
excuse, but a decision only the campaign owner can make about the campaign's own guidance —
which unit gets to say "my case is one of the forced ones.")

**The campaign owner (Sven) has since reviewed and accepted the deviation for t1 specifically**
(2026-09-11, in the same session that produced this correction) — on the same substantive
grounds t0's recommendation (a) already gives for t4/t5/t8/t9 (the roots are forced by where
the behavior lives, not chosen), given the scale here (2 of 27 ACs, both already-passing
existing tests, no new harness). That owner decision, not t1's own citation, is what makes the
deviation authorized. Triage card `trg-ff6ea5f0` (amended alongside this correction) records
t1 as resolved-by-owner, distinct from t4/t5/t8/t9, whose own confirmation is expected but not
yet finalized as of this writing. The F3 decision-drop for `iterate-2026-09-11-t1-iterate-surface`
carries the same reasoning in its `decision` and `rationale` fields (its `consequences` field
carries only the corrected AC-count/unbound-count numbers).

**Second-order fix this exposed:** binding those two ACs' tags requires
`.shipwright/compliance/test-traceability.json` to be regenerated from a tree the collector
actually scans, and `shipwright_compliance_config.json`'s `traceability.test_roots` predated
ADR-044's canonical root list — it named `shared/tests` but not `shared/scripts/tests` or
`shared/scripts/tools/tests`. t1 added both (restoring the config to the already-documented
canonical list, not introducing a new root) — see that run's mini-plan
(`2026-09-11-t1-iterate-surface-miniplan.md`) for the empirical before/after verification.

### Exception 4 — FR-01.11 AC12, the ordering clause (found during t1 execution, external code review)

`FR-01.11/AC12` conjoins two clauses in one AC (`spec.md`, FR-01.11 AC12): **(a)** an
independent reviewer checks the plan first, the same way `/shipwright-plan`'s own plan review
does, **before** any outside second opinion is asked (an ordering guarantee); and **(b)** that
reviewer runs on a Claude model configurable per project, defaulting to the session's own model
when unset (a configuration guarantee).

| Clause | Provable now (existing seam)? | Real seam |
|---|---|---|
| (b) model configuration | **yes** | `shared/tests/test_model_tier_config.py::test_plan_review_role_resolves_independently_of_review`, `::test_unset_resolves_to_inherit_with_source_unset` — both already pass, prove exactly clause (b) |
| (a) internal-before-external ordering | **no** | there is no enforcement seam at all: the internal reviewer arm (`opus-plan-reviewer`) is not wired into the iterate's plan-review path today — `/shipwright-iterate`'s plan review is external-only, and the review-record schema's `plan_internal` type exists to be recorded but is permanently `not_run` (a documented gap, never promoted; see `reviews.plan_internal` in this run's own review record). Nothing deterministic runs "the internal reviewer, then the external one" for this AC to observe |

**Concrete machine outcome (same rule as Exception 2's AC02, external code review, medium — t1
had bound this AC to the clause-(b) tests alone before this correction):** clause (b) being
provable does not make the whole conjunctive AC provable. **Do NOT tag `FR-01.11/AC12`** — t1's
two `@pytest.mark.covers("FR-01.11/AC12")` decorators are removed in the same commit as this
correction, and the AC stays in `shipwright_ac_coverage_baseline.json`'s `unbound` list. Tagging
it would mark the AC bound while its primary clause remains structurally unenforced, not merely
untested. Both `test_model_tier_config.py` tests keep proving clause (b) in their own right (a
future unit reads this note rather than re-deriving the split); a future unit should re-tag
`FR-01.11/AC12` only once clause (a) has an actual enforcement seam to assert against — wiring
the internal reviewer arm into the iterate's plan-review path so that it actually runs before
the external pass, rather than being an unused fallback, is the fix that would create one.

### Exception 5 — FR-01.14 AC26 (no deterministic surface, found during t2 execution)

`FR-01.14/AC26` ("the Triage Inbox is explicitly not a plan") is a
definitional/policy guarantee about what the Triage Inbox *is not* — the same
class of AC as Exception 1's "no seam" rows (FR-01.12 AC02/AC03/AC07/AC09):
there is no deterministic surface anywhere in the codebase that implements or
enforces "this is not a plan"; it is a documentation/scope claim, not
executable behavior. No amount of grepping the `shared/tests` or
`shared/scripts/tools/tests` roots surfaces a candidate seam, because none
exists — attaching a test to some nearby triage behavior would prove that
behavior, not this claim.

**Concrete machine outcome:** do NOT tag `FR-01.14/AC26`. It stays in
`shipwright_ac_coverage_baseline.json`'s `unbound` list, with this section as
its recorded reason (the same Named-Exception mechanism Exception 1 and
Exception 4 already use for the campaign's other "no seam exists" ACs — not a
new convention). The run's own F3 decision drop
(`iterate-2026-09-11-t2-triage-inbox_001.json`) carries the same reasoning in
its `decision` field; this section is the durable, campaign-wide record a
future unit or auditor would actually look at (external plan review, openai +
glm, medium: a decision-drop alone is not sufficient for a claim the
acceptance criterion itself calls a "recorded reason").

### Exception 6 — FR-01.03 AC20/AC21 (obsolete provider, found during t3 execution)

`FR-01.03/AC21` names DeepSeek-specific ZDR-endpoint routing as part of the
external-review reviewer roster. `shared/scripts/lib/external_review_routing.py`
documents that GLM replaced DeepSeek as `/shipwright-plan`'s reviewer identity
(`iterate-2026-09-02-glm-plan-code-review-swap`, predating this campaign) — no
current plan-review code path invokes DeepSeek at all; DeepSeek's remaining ZDR
routing now serves only the Tier-3 PR-review gate's operator-overridable model
choice (FR-01.17, a different FR). This is not the same class as Exceptions 1/5
("no seam ever existed") — a seam DID exist, for a provider the product has
since retired. Binding AC21 to GLM's own routing test would misrepresent which
provider the AC names; binding it to the Tier-3 gate's DeepSeek test would
misrepresent which FR's behavior is proven.

**AC20 amended into this exception (Stage-1 spec-review REJECT, corrected
2026-09-12):** t3's first pass bound `FR-01.03/AC20` — "the default outside
reviewers are invoked... identified truthfully as **DeepSeek and OpenAI**" —
to two tests that actually assert the *current* roster (glm/openai) is
identified truthfully, silently substituting the roster the AC names for the
one the codebase currently runs. That is the identical obsolete-provider
situation as AC21, given the opposite (wrong) treatment: quietly retargeted
and marked bound instead of left unbound with a recorded reason. Corrected:
the `@pytest.mark.covers("FR-01.03/AC20")` markers were removed from
`plugins/shipwright-plan/tests/test_check_plan_gates_reviewers.py`'s
`test_a_historical_schema_marker_is_still_read_truthfully` and
`test_a_current_schema_marker_cannot_borrow_a_historical_reviewer_name` — both
tests remain (they genuinely prove the *current* roster's truthful
identification, a real and valuable guarantee), just not as AC20's binding.

**Concrete machine outcome:** do NOT tag `FR-01.03/AC20` or `AC21`. Both stay
in `shipwright_ac_coverage_baseline.json`'s `unbound` list, with this section
as their recorded reason (same Named-Exception mechanism as Exceptions 1/4/5 —
not a new convention). t3's own F3 decision drop and ADR
(`.shipwright/planning/adr/iterate-2026-09-12-t3-plan-design-fr-01-03-01-04-ac-backfill.md`)
carry the same reasoning; this section is the durable, campaign-wide record.
If a future spec revision retargets AC20/AC21 at the current roster
(GLM/openai), this exception is void and both should bind normally at that
point.

### Exception 7 — FR-01.04 AC10 (AC's full claim not enforced, found during t3 execution)

`FR-01.04/AC10` — "given feedback on a single screen, when it is applied, then
only that screen is regenerated and **the others are left untouched**" — was
first bound to `test_a_flagged_screen_left_untouched_fails`, which only
asserts the *flagged* screen was touched; it asserts nothing about other
screens staying untouched. That gap is not a test-design oversight: the gate
it calls, `iteration_touched_flagged_screens`
(`shared/scripts/lib/design_gate_extras.py:279-300`), explicitly documents and
implements the opposite of AC10's "others are left untouched" guarantee —
extra modified files beyond the flagged set are a warning, not a failure,
because Chrome Change Propagation legitimately touches every screen in one
round. AC10 as written admits no such carve-out, so the production code
cannot make the bound test's implied full claim true; binding it anyway would
be a test shaped around what the implementation checks, not around what the
AC actually requires (Stage-1 spec-review REJECT, corrected 2026-09-12,
`plugins/shipwright-design/tests/test_check_design_gates.py`). Same class as
Exception 4's conjunctive-AC guidance: a partially-provable clause does not
make the whole AC provable.

**Concrete machine outcome:** do NOT tag `FR-01.04/AC10`. It stays in
`shipwright_ac_coverage_baseline.json`'s `unbound` list, with this section as
its recorded reason. Resolving it for real needs a product decision this test
backfill campaign does not make unilaterally: either tighten
`iteration_touched_flagged_screens` to actually enforce "others untouched"
(a behavior change, and Chrome Change Propagation's legitimate multi-screen
case would need an explicit carve-out in AC10's own text first), or amend
AC10's text to state the carve-out that already exists in production. Flagged
to the operator rather than decided here.

### Exception 8 — FR-01.03 AC03/AC11 (no observable artifact, found during t3 PR review)

`FR-01.03/AC03` ("the plan's own author re-reading it never satisfies the
review step unless the independent reviewer could not be reached either")
and `FR-01.03/AC11` ("either reviewer's reject stops the run and asks a
person to choose") were bound to drift-pin tests
(`test_self_review_fallback_only_runs_when_no_independent_review_completed`,
`test_architecture_reject_stops_and_asks_the_user_to_choose` in
`plugins/shipwright-plan/tests/test_review_routing_contract.py`) that assert
the instruction text is present in `step-5-external-review.md` — the same
class of judgement-criterion AC that `FR-01.03/AC02` already uses this
pattern for (`test_missing_key_stop_and_ask_drift.py`). The Tier-3 external
PR review (openai/gpt-5.6-luna, high) found this insufficient to PROVE either
AC: a production implementation that silently ignored the instruction would
still pass, because the would-be observable artifact
(`self_review_fallback_ran`) is write-only — nothing reads it — and AC11's
"stopped and asked a person" has no recorded flag at all. Unlike AC02
(already-merged, pre-existing precedent this unit did not introduce), AC03
and AC11 are net-new bindings in this diff, so the campaign's actual
required merge gate (not a documented precedent from an earlier unit) is the
live arbiter here.

**Concrete machine outcome:** do NOT tag `FR-01.03/AC03` or `FR-01.03/AC11`.
Both stay in `shipwright_ac_coverage_baseline.json`'s `unbound` list, with
this section as the recorded reason. The drift-pin tests are kept
(unmarked) as a guard against the reference doc itself drifting, since that
much is still worth catching even though it does not prove the AC. A future
correction to AC02's own binding is a separate campaign-wide question this
unit does not decide; wiring a real observable seam (e.g. making
`self_review_fallback_ran` readable and asserting it, or recording the
three-way choice for AC11) is a production change, not a test-selection one,
and is flagged to the operator rather than decided here.

## Per-unit ADR-044 root count (for the "keep it at one or two roots" campaign constraint)

| Unit | FR(s) | Roots touched | Root count |
|---|---|---|---|
| t1 | FR-01.11 | `plugins/shipwright-iterate/tests`, `shared/tests`, `shared/scripts/tools/tests` | 3 (found during execution — see Exception 3; **accepted by the campaign owner**, 2 of 27 ACs, no new harness) |
| t2 | FR-01.14 | `shared/tests`, `shared/scripts/tools/tests` | 2 |
| t3 | FR-01.03, FR-01.04 | `plugins/shipwright-plan/tests`, `plugins/shipwright-design/tests` | 2 |
| t4 | FR-01.06, FR-01.07 | `plugins/shipwright-test/tests`, `plugins/shipwright-security/tests`, `shared/tests` | 3 (watch this one — see below) |
| t5 | FR-01.08, FR-01.09 | `plugins/shipwright-deploy/tests`, `plugins/shipwright-changelog/tests`, `shared/tests` | 3 (watch) |
| t6 | FR-01.02, FR-01.16 | `plugins/shipwright-project/tests`, `shared/tests` | 2 |
| t7 | FR-01.10, FR-01.18 | `plugins/shipwright-compliance/tests`, `plugins/shipwright-grade/tests` | 2 |
| t8 | FR-01.01, FR-01.05, FR-01.12, FR-01.13 | `plugins/shipwright-run/tests`, `plugins/shipwright-build/tests`, `plugins/shipwright-adopt/tests`, `shared/tests`, `shared/scripts/tests` | 5 (watch — largest fan-out) |
| t9 | FR-01.15, FR-01.17, FR-01.19, FR-01.20 | `shared/tests`, `shared/scripts/tests`, `shared/scripts/tools/tests`, `plugins/shipwright-iterate/tests` | 4 (watch) |

ADR-044 (repo-root `conftest.py`, exit 4) blocks a single pytest **process** from spanning
roots — it does not cap how many roots a *unit* may touch across multiple invocations. t4, t5,
t8 and t9 should plan on 3–5 separate `uv run pytest <root> --junitxml=...` invocations, not
one.

**Flagged deviation, not a reinterpretation (external plan review, glm, medium — accepted;
corrected 2026-09-11 after Stage-1 spec-review REJECT — the first version of this paragraph
named only t8/t9 and silently under-reported t4/t5, which the table two rows above it had
already shown at 3 roots each. A survey that reports only part of its own finding is worse
than none: it implies completeness it doesn't have. Re-checked systematically against every
row of the table above, not spot-checked, before writing this correction):**
campaign.md states the cut should "keep that count at one or two, never more." **Five units**
exceed that as surveyed / as later found during execution: t1 (3 roots — found during t1's own
run, see Exception 3), t4 (3 roots), t5 (3 roots), t8 (5 roots) and t9 (4 roots) — not only
t8/t9. (This guideline is a cost heuristic the campaign author wrote at cut time, not an
ADR-044 requirement — ADR-044 governs only how many pytest *processes* a single root may
span, not how many roots a unit may touch. That does not make the guideline optional to
individual units, though: it does make (a) below the substantively right answer whenever the
per-FR data forces it, which is exactly what Finding 1 already established.) t0 does not have
the authority to waive a binding campaign guideline by relabeling it a "target" — that decision
belongs to whoever owns campaign.md, not to the unit whose fan-out happens to exceed it. **t1's
case is now RESOLVED** — the campaign owner reviewed and accepted the deviation for t1
specifically (2026-09-11; see Exception 3's Authorization note above) — but **this remains an
open conflict for the campaign owner to resolve before t4, t5, t8 or t9 run**, with two honest
options on the table for each of the four: (a) accept the deviation explicitly (the fan-out
reflects where the behavior already lives, not scope creep chosen by the unit — the same
grounds t1's deviation was accepted on), or (b) re-cut the FR grouping so each unit stays
within two roots (e.g. split t4's FR-01.07 shared-scan-card ACs, t5's FR-01.09
shared-aggregation ACs, or t8's `shared/scripts/tests`-only AC bucket from FR-01.12's real-seam
rows, into their own passes). t0 recommends (a) for all four — the roots are forced by
Finding 1 (behavior lives where it lives), not chosen — but does not decide it unilaterally.
Triage card `trg-ff6ea5f0` names all five units, t1 marked resolved and t4/t5/t8/t9 still open
(amended alongside this correction); see it for the campaign owner's decision point. A similar
ruling for t4/t5/t8/t9 is expected but not yet finalized as of this writing.
