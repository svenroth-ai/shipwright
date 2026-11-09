# Deterministic-first pilot: `/shipwright-changelog`

**Stand:** 2026-11-09, rev 5 (re-cut to programme rev 5; after two review rounds and the operator decisions of 2026-10-27 and 2026-11-09; programme §10, this brief §7) · **Programme:** `2026-10-25-deterministic-first-programme-BRIEF.md` (P1-P24, the stops of §4 and the template of §5 are binding here and not repeated)
**Execution:** autonomous campaign, `branch_strategy: serial` with `depends_on` edges, **no parallel units**. Exactly three operator stops: stop 1 after P0; stop 2 = the operator procedure P2-op, after P2p; stop 3 = the operator procedure P7-op, after P7. An autonomous run reads **this** document; progress lives in the campaign's `status.json`.

**Start conditions (operator checks before starting):**
1. ac-at-start Q1 merged (#1014) and the F11 dry run done on a throwaway extraction diff, per programme §2.1 (replaces "BP merged"; BP was stopped on 2026-10-29). Q2 phase 1 is merged (#1022, #1023). The fix of Q1's order check is merged. The first P0 run checks that the runner's `work_completed` event carries `source: iterate` and `adr_id` = its run id; if not, STRICT-STOP.
2. Done: run campaign B unit **B5** (#926; it catalogued the changelog asks and added `unattended`) and, after it, the standalone **AC04 iterate** (#937). The changelog has changed since: #935 (the release event never pushes `main` untagged), #996 (`package_lock_json` manifest format), and the events-drop-files units #1004, #1005, #1013 and #1015 (Step 7 stages `shipwright_events.d`).
3. **The events flip (S9a) is merged.** Operator decision 2026-11-09: the pilot starts right after it, without the observation period, and characterizes the skill after the flip. Scenarios pin `events_layout` and run both `legacy` and `drops`; replay and L3 unset `SHIPWRIGHT_EVENTS_LAYOUT[_TEST]` (programme §2.2).
4. No open unit of campaign B or U names a file in this brief's touch sets. No atomic-frs split names FR-01.09 or FR-01.01: re-run `fr_cluster_report.py --fr FR-01.09` and `--fr FR-01.01` at start (neither was flagged on 2026-11-08). A split of either waits for stop 3.
5. **Scope:** `scope_frs: FR-01.09, FR-01.01` (the canon-marker pin, P0.3); P0 proposes any further FR that owns a pin, and the operator extends the list at stop 1. A unit whose AC record names an AC outside it is a STRICT-STOP (programme §2.1). Runners pass `--ac-mode auto`. The STRICT-STOP reads the record: any kind other than `unchanged` stops the unit, and so does any `exempt` item other than D1 (`update-step`). A unit counts as `unchanged` only with equal traces and an unchanged lock (programme §2.1).
6. Both briefs committed; budgets written down; L3 tool verified (programme §2.4-2.5); plugin cache synced and checked.
7. The cross-cutting themes changelog touches are cut (programme P22; expected: none, the operator confirms); the code-versus-AI convention file `shared/prompts/building-skills-plugins-agents.md` is merged, and this brief's runners are pointed at it (programme §2.7).
8. Re-measured on the `main` the pilot starts from (the flip may change them): `changelog/SKILL.md` lines (443 on 2026-11-09; bloat entry: limit 400, exception 443, ADR-348), ACs with a deterministic test (13 of 15; AC15 none), the pin list by breaking the prose (30 tests in 13 files on 2026-11-09, MEASURE §7.3).

---

## 0. Why changelog first

- 1,038 prompt lines, almost all mechanics. The judgement is small and already sits in the target pattern: the release-note condensing is a model call wrapped in code with a fixed output check (`publish_release_notes.py` → `condense_release_notes`).
- One FR, FR-01.09, with 15 ACs: small enough to cover completely.
- Its outputs (`CHANGELOG.md`, tag, ADR numbers, evidence documents, manifests) are deterministic and comparable.
- It is converted to **one CLI** plus a thin `SKILL.md`; no engine (programme P2).

## 1. Inventory pre-assessment (P0 confirms or corrects it; operator approves at stop 1)

| Section | Class | Target |
|---|---|---|
| A banner (incl. the advertised `--from vX` argument), B plugin root, D setup, Step 0 context | mechanic | `cli:prepare` |
| C mode resolution; `error` mode → STOP, `ok:false` | mechanic | `cli:prepare` |
| C out-of-sequence warning | ask | truth table |
| Steps 1-3 history, categories, suggested version | mechanic | `cli:prepare` |
| Step 3 accept or enter another version | ask | truth table |
| Step 4 aggregate (dry run, real run), ADR drops, cherry-pick fallback (`append_changelog_entry.py`) | mechanic | `cli:aggregate` |
| Step 4 legacy bullets "operator chooses" | ask | truth table |
| Step 4 refused re-run "reconcile by hand" | **operator action**: a hard stop naming the disagreement, never agent judgement (AC08) | `cli:aggregate` exit 1 |
| Step 4 re-run paragraphs | rationale | already in `references/rerunning-a-release.md`; prose deleted |
| Step 5 accept / edit / cancel; "edit" | ask; edit is judgement | truth table; `keep` |
| Steps 5.4 manifests, 5.5 evidence documents | mechanic | `cli:sync` |
| Step 6 commit, verify, tag | mechanic; explicit pathspec, `git commit -- <paths>` (`--only` semantics), commit first, both `--verify-commit` on the committed HEAD, tag only if every step exits 0 | `cli:commit-and-tag` |
| Step 7 push, PR, merge, tag push | **outward**: literal commands the agent runs (programme P4) | `keep`, one line each |
| Step 7 event record and its commit | mechanic | `cli:record-event` |
| Step 7 release page | mechanic, already one script | `keep` (`publish_release_notes.py`) |
| Step 7 canon C1-C3, phase history, `update-step`, restore | mechanic; `update-step` per decision D1 | `cli:close-phase` |
| `references/release-notes-prompt.md` | **runtime-input** (read by `publish_release_notes.py:44-48`) | `keep`, hash pinned |
| other references | reference / rationale | what/how kept, history deleted |

## 2. Truth table (filled in P0 from the code as it stands after B5; approved at stop 1; pinned by L2)

Rows: `{standalone, pipeline}` × `{guided, autonomous, unattended}` × each question (out-of-sequence, version, legacy bullets, preview, PR merge). Each cell: asks / auto-accepts / skips / resolves through `gate_policy` (gate id, catalog default), with the `SKILL.md` line or catalog entry it comes from. Gate ids catalogued by B5 (`shared/config/gate_catalog.json`): `changelog.out-of-sequence-continue`, `changelog.version-suggestion`, `changelog.entry-preview`. The PR merge and the legacy-bullet choice have no gate id. Known cells: autonomous auto-accepts the version, skips the preview, merges the PR (`SKILL.md:352-355` on 2026-11-09); guided asks. P0 re-reads every line number from the tree it starts on. The conversion reproduces every cell; changing one is a deviation.

## 3. Known findings (programme P17: reproduced 1:1, reported, not fixed here)

The pilot reproduces each of these exactly as it behaves today and records it in `2026-10-25-dfp-pilot-changelog-FINDINGS.md` with the proposed fix below; the follow-up campaign decides. Where the prose contradicts itself (D1), stop 2 decides which behaviour is today's oracle, from the replay and the real-model runs.

| # | Today | Proposed fix (for the follow-up campaign) |
|---|---|---|
| D1 | `update-step` forbidden by Step C, called by Step 7 | call it only in standalone mode (keeps today's run-config bootstrap); or drop it |
| D2 | AC11: tags and the release page are published before the PR is merged; autonomous merges at once | on a feature branch: no tag push and no release page until the PR is merged |
| D3 | ~~an **untracked** events file is never committed~~: resolved before the pilot (the Step 7 block now runs `git add` when the file exists and commits the staged event paths, #935 and #1004); S1 asserts it | none |
| D4 | `--since "{last_tag}"` with no tag can render `null..HEAD` | pass no `--since` when there is no tag |
| D5 | a breaking change recorded only in a drop file, not in a commit message, gives minor or patch | read breaking markers from drops as well |
| D6 | opening the PR is `prompt-only (judgement)` by req3-06 D7 | not a finding: stays a literal command in the prompt; D7 unchanged |
| D7 | `gh pr create` (`SKILL.md:333`) runs before `git push origin HEAD` (`:349`); `git push --tags origin main` from a feature branch or after an autonomous merge pushes a stale local `main` | push the head before opening the PR; push tags without pushing a local `main` |

Further findings come from P0 (inventory against FR-01.09 and guide chapter 4), from the operator's answers at stop 1, and from the real-model runs at stops 2 and 3 (`model-improvised`: e.g. a model that pushes before opening the PR).

## 4. Units

| id | Unit | Real touch set | depends_on | Cx |
|---|---|---|---|---|
| **P0** | Inventory, coverage checker, truth table, pin list, subprocess map, findings report, profile key listing, ledger reconcile; promise list with candidates and the count of ACs that can get a green driver-level test (P19); P24 "before" measurement | new `skills/changelog/inventory.json` (+ truth table, subprocess map as data next to it); new `.shipwright/planning/campaigns/2026-10-25-dfp-pilot-changelog-FINDINGS.md`; new `shared/scripts/tools/check_skill_inventory.py` + tests; `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md` + its re-measured header (`measure_ac_evidence_ledger.py`) | - | medium |
| **P1** | Seams and offline proof: one shared argv-prefix helper for `gh` used by `setup-changelog.py`, `create_github_release.py` and any other `gh` caller on the path; a fixture model for condensation; proof (or a seam) that a scratch project passes `--verify-commit --release-audit` offline | the helper (new, under `shared/scripts/`); `plugins/shipwright-changelog/scripts/checks/setup-changelog.py`, `shared/scripts/tools/create_github_release.py`, `condense_release_notes.py`, the audit path if a seam is needed; L1 tests proving each default is unchanged | P0 | medium |
| **P2a** | Harness: `golden_trace.py`, scratch builder (`minimal_valid_project` + git + bare `origin`), `gh` stub with its contract, environment builder, driver interface, freeze test | new `shared/testkit/golden_trace.py`, `shared/testkit/release_scratch.py`, `shared/testkit/gh_stub.py` (stdlib only); their unit tests in `shared/tests/`; new `plugins/shipwright-changelog/tests/golden/conftest.py`, `test_trace_freeze.py` | P1 | large |
| **P2b** | Scenarios, replay driver, coverage checks green on the unchanged skill, seeded regressions | new `plugins/shipwright-changelog/tests/golden/` (scenarios, `driver_replay.py`, generated `*.trace.json`) | P2a | large |
| **P2p** | Promise tests for the promise list approved at stop 1, through the driver interface, green against the unchanged skill; ACs whose only oracle is the replay marked `oracle: trace` (programme P19); the promise lock's hashing (normalized AST of the test and its fixtures, AC ids resolved through `## AC-Move-Map`, programme P21) | new `plugins/shipwright-changelog/tests/golden/test_promise_*.py`, `promise_list.json`; the hashing helper in `shared/testkit/` with its tests; existing `covers` tests only where the list rebinds them | P2b | medium |
| **P2-op** | Operator procedure (§5) | lock file (traces and promise tests), `approved_deltas.json`, pinned prose copy, committed by an iterate | P2p | - |
| **P3** | CLI part 1: `prepare`, `aggregate`; ADR drop "Deterministic-first skills"; the prose-rule map once, as an experiment (programme P20) | new `plugins/shipwright-changelog/scripts/release.py`, `scripts/lib/release_*.py` + L1 tests + boundary test; new `tests/golden/driver_cli.py` (steps A-4); `SKILL.md` Steps A-4; `inventory.json`; `docs/hooks-and-pipeline.md` rows | P2-op | medium |
| **P4** | CLI part 2: `sync`, `commit-and-tag`, `record-event`, `close-phase` | the same files; `driver_cli.py` (steps 5.4-7); `SKILL.md` Steps 5.4-7; `inventory.json`; hooks-doc rows | P3 | medium |
| **P5** | Thin `SKILL.md`; pins moved | `SKILL.md`, references; the pins from P0 | P4 | medium |
| **P6** | Ratchet; guide, glossary, architecture; bloat entry lowered last | new `shared/config/converted_skills.json`, `shared/scripts/tools/check_prompt_mechanics.py` + tests; `.github/workflows/ci.yml` (`python-checks`, a `(gate)` step); `scripts/verify_local.py`; `shared/tests/test_verify_local_ci_drift.py` if needed; docs; `shipwright_bloat_baseline.json` | P5 | medium |
| **P7** | Conversion checker and report; the orphan removals approved per test (programme P18); the saving report (P24); inventory and coverage checks retired for changelog | new `shared/scripts/tools/check_plugin_conversion.py` + tests; the approved orphan tests (removed) | P6 | medium |
| **P7-op** | Operator procedure (§5) | report | P7 | - |

## 5. Unit specs

### P0
1. Inventory per programme P10, covering `SKILL.md` and all seven references.
2. Truth table (§2) as data, every cell citing its source.
3. **Pin list, found by breaking the prose, not by grep:** run every test root once with the changelog `SKILL.md` and the references other than `release-notes-prompt.md` replaced by a placeholder; every test that fails is a pin. **Measured 2026-11-09** (`2026-11-07-dfp-pre-q1-MEASURE.md` §2 and §7.3): 30 tests in 13 files.
   - Behaviour through prose: `plugins/shipwright-changelog/tests/test_skill_event_blocks_behaviour.py` (7, AC01; a promise candidate that rebinds to the CLI) and `shared/tests/test_events_drop_hardening.py` (4).
   - Text pins: `test_skill_event_ships_in_release_pr.py` (3), `test_skill_release_flag_wiring.py` (4, no `covers` mark), `test_changelog_judgement_drift.py` (1), `test_setup_changelog_version_suggestion.py` (1), `test_skill_upgrade_notes_check.py` (2), all in the changelog root; `shared/tests/test_release_pathspec_doc_sync.py` (3).
   - Cross-plugin guards, constraints the thin `SKILL.md` must keep satisfying, not pins (programme P11): `shared/tests/test_canon_marker_write_contract.py` (FR-01.01), `test_phase_gate_discipline_present.py`, `test_events_reference_guard.py`, `integration-tests/test_phase_skill_invocation_mode_canon.py`, `test_multi_session_removal_residue.py`.
   - Not pins, despite the original list: `test_condense_release_notes.py`, `test_changelog_aggregation_idempotency.py`.

   P0 measures again on its own starting tree and uses that list.
4. **Subprocess map** (programme P7a): every binary, `uv run --with` resolution, audit and network call on each scenario path, with the plan for each (seam, offline, impossible). Known: `gh` in `setup-changelog.py:48,60` and `create_github_release.py:62-136`; the release audit (`refresh_compliance_docs.py:173-177` → `audit_compliance_lifecycle.py`); condensation over HTTPS; `.env.local` loaded at import (`condense_release_notes.py:52`).
5. Ledger reconcile both ways for FR-01.09, including whether each test that claims an AC exercises the path the skill actually takes (the AC04 precedent: a green test on a function the skill never called).
6. Promise list (programme P18, P19): every FR-01.09 AC in plain language, with its candidates from existing `covers` tests (for example `test_skill_event_blocks_behaviour.py`, "promise, rebinds to the CLI"), and the count of ACs that can get a green driver-level test against the unchanged skill. Fewer than half is reported at stop 1.
7. P24 "before" measurement: test count and wall-clock of the changelog test root and of the pins in other roots (JUnit durations, one root per process).
8. The findings report (§3 plus what P0 finds) and the profile key listing, in the PR body; the questions where FR-01.09 and the guide are silent, in plain language. **STOP 1.**

### P1
Every seam is an environment variable named `SHIPWRIGHT_TEST_*`, read in one place, documented, inert when unset, and covered by an L1 test that the default path is unchanged. On Windows `gh` is spawned as `["gh", ...]`, so the seam is an argv prefix (interpreter + stub script), not a `.cmd`. `create_github_release` refuses to publish fixture-model text unless the `gh` seam is also set, so a stray variable cannot publish fixture notes for real.

### P2a
1. Scratch project = `minimal_valid_project` + a git repository + a local bare `origin` with a fake GitHub-style URL (for `resolve_repo_identity`) and a file push URL.
2. Environment built explicitly: no API keys, no `SHIPWRIGHT_ROOT`, `GIT_ALLOW_PROTOCOL=file`, working directory = the scratch repo; the test fails if a key leaks in.
3. `gh` stub contract: `pr create` refuses unless the head branch is on the bare remote; `pr merge` really merges into the remote's base branch and deletes the head branch; `release create` refuses unless the tag is on the remote and persists state, so a later `release view` returns `exists`. Its argv log is part of the trace.
4. The driver interface (programme P7); the freeze test (programme P9) in the changelog test root.

### P2b
Scenarios (each listed AC is asserted by the oracle, not merely touched):

| # | Scenario | ACs / rows |
|---|---|---|
| S1 | first release, no tag (fresh repo, untracked events file) | AC01, AC04, D3 (regression guard), D4 |
| S2g / S2a / S2u | `feat` + `fix` since 1.x, guided / autonomous / unattended | AC02, AC04, AC06, truth table |
| S3 / S3b | breaking since `0.x` in a commit / only in a drop | AC04, D5 |
| S4 | breaking since 1.x | AC04 |
| S5a / S5b | no commits since the tag / commits but no drops (`--fail-if-empty`) | AC03 |
| S6 | re-run converges (incl. the `--release-date` rule) | AC07 |
| S7a / S7b / S7c | re-run refused: drops disagree / withdrawn marking / two sections claim the version | AC07, AC08 |
| S8 | legacy bullets | AC09 |
| S9 | dry run writes nothing | AC10 |
| S10 | two decision drops numbered at release; cherry-pick fallback | AC05 |
| S11a / S11b | declared manifests incl. nested catalog / a manifest left at the old version → stop, no tag | AC12, AC13 |
| S12a / S12b / S12c | release page created (fixture model) / condensed text fails the shape check / creation fails, release not undone | AC14, AC15 |
| S13 | pipeline mode: dispatched with `phaseTaskId`, real `single-session-apply` with enforcement on (`_validate_changelog`, `phase_history` run id) | AC01, AC11 |
| S14a / S14b / S14c | feature branch / `main` / a repo whose default branch is `master` | AC01, AC11, D2, D7 |
| S15 | an unrelated staged file and an unrelated unstaged file stay out of the release commit | Step 6 invariant |
| S16 | refusal paths: 5.4 or 5.5 not `ok`, `--release-audit` fails, a pre-commit hook rejects, push rejected, `gh` missing | no tag, no event |
| S17 | `error` mode (stale `phaseTaskId`) → STOP; out-of-sequence warning | Step C |
| S18 | Step 5 cancel and edit after the real aggregation (today's order kept) | truth table |
| S19 | `--from vX` | banner |

1. `driver_replay.py`: per scenario the command sequence of today's prose, each command citing its line.
2. Where the stub contract refuses today's order (D7), the replay records the refusal as today's behaviour.
3. Coverage checks P8a-c green; three seeded regressions as L2 cases: tag on `HEAD~1`, commit without pathspec (S15), drops not deleted after aggregation.

### P2p
The promise tests call the driver interface only, never a module path or a `SKILL.md` block. Each is green against the unchanged skill through the replay driver. Adding is free; an existing `covers` test is rebound to the driver, not deleted. The lock's hash ignores formatting, comments, docstrings, import order and markers, and includes every same-module helper and fixture the test calls (spike: MEASURE §4; `conftest.py` fixtures are added here).

### P2-op (operator procedure → STOP 2)
1. The plugin is loaded from a directory at the commit after P2p (hash recorded), never from the installed cache (programme P7a).
2. Runs per scenario group with the models of programme §2.4 (Opus, at least three, more where samples disagree). Every difference from the replay, and every place the model improvised (e.g. pushing before opening the PR), is listed with a proposed answer.
3. Optional, if the fork tool is merged and a run reached the changelog phase (programme P23): one fork of that run at `--at changelog` with `--repo` at the commit that closes stop 2, a local bare remote and the `gh` stub and `SHIPWRIGHT_E2E_STOP_AFTER=changelog`. Its commits, tag, `CHANGELOG.md` and release event are kept as the "before" sample for P7-op.
4. The operator decides which behaviour is today's; `approved_deltas.json` records each such decision; the model-improvised steps go into the findings report; the traces, the promise lock, `golden_trace.py` and a copy of the prose are frozen by hash; one iterate commits them.

### P3, P4 - the CLI
1. `release.py <subcommand>`, JSON out; thin wrappers over the existing tools with the same flags; no logic duplicated. Imports per programme P16; run's `orchestrator.py` through one constant with an L1 test across the repo and cache layouts.
2. Each subcommand re-checks its postcondition from git and the filesystem, so a re-run after an interruption works with any run id.
3. In-process L1 tests with an injected runner for every subcommand (diff coverage).
4. `commit-and-tag` keeps every Step 6 invariant (§1) and refuses to tag unless every step exits 0.
5. `close-phase` keeps `--canon-marker --phase changelog` (L1 test on its argv, FR-01.01) and the `phase_history` run-id behaviour `_validate_changelog` reads.
6. `driver_cli.py` drives the moved steps; every scenario's trace through the CLI driver equals the frozen trace (or its approved variant). The prose of the moved steps becomes one call each; `inventory.json` and the hooks-doc rows change in the same diff.
7. P3 only: the prose-rule map (programme P20), once. An AI maps each moved instruction to its new home (function, test, or `dropped: <reason>`); code checks that every rule is listed and every named function and test exists. The result, and whether it found a gap P8 missed, goes into the findings report. It never blocks the PR.
8. The locked promise tests stay untouched and green through the CLI driver. Each unit's AC record is `unchanged` per kept AC, listing every observable file (programme §2.1).

### P5 - thin `SKILL.md`
Per programme §5. The description stays word for word. Mode resolution stays visible (`--phase-task-id` when handed one; the integration pin stays on `SKILL.md`). Outward commands stay literal, one line each. Questions per the truth table, in plain language. Every pin from P0.3 is moved or replaced in this diff, mapped one by one in the PR; none is deleted without its replacement.

### P6, P7, P7-op
Per programme P12 and §5 (Tr, Tz). P7 checks every seeded regression is caught by L1/L2, the Codex bundle resolves `release.py`, and `verify_local.py` is green; then it retires the changelog inventory and coverage checks and closes the findings report. P7 also removes the orphans the operator approved per test and writes the saving report (programme P24). P7-op: L3 on the plugin loaded from the P7 commit (hash recorded; the checker refuses the T1 hash); if P2-op made a fork sample, a second fork of the same run at the same boundary with `--repo` at the P7 commit, compared with the first (differences are findings or approved deltas, never silently accepted); a canary release in a throwaway repo with a private remote, the cache sync, then the first real release; the findings report is handed over as the input of the follow-up campaign. **STOP 3.**

## 6. Repo rules for every unit

Docs in the same diff; edits local and rebased on `main`; new files at most 300 lines; one pytest root per process; `uv run scripts/verify_local.py` and `uvx ruff@0.15.15 check .` before push; tests tagged with FR/AC minted by the producers; a unit edits a test only if it is in its touch set; review cascade per CLAUDE.md (`model=opus` explicitly); a unit red twice is released with its dependents; P2a, P2b or P2p red = STRICT-STOP; anything needing an operator answer between stops = STRICT-STOP.

## 7. Review log

- **Rev 1 → rev 2:** see programme §10. Pilot-specific changes:
  - The engine units are removed; a CLI replaces them.
  - Seams, harness and the operator procedure are separated.
  - P1b is replaced by the standalone AC04 iterate and the deviation list.
  - The scenarios are widened.
  - "Reconcile a refused re-run" becomes an operator action, and `release-notes-prompt.md` a runtime input.
  - The pin list is completed, outward commands stay literal, and the CI step is named.
- **Rev 2 → rev 3, after the second Opus review (revise; 4 blockers):**
  - P2-op loads the plugin from a recorded commit, not the cache.
  - Deviation variants are approved at stop 2, so a `Tdev` unit needs no stop.
  - P2 is split into a harness (P2a) and scenarios (P2b), with a per-step driver interface. P3 and P4 own `driver_cli.py`.
  - A subprocess map is added. `setup-changelog.py` is in the `gh` seam, and the release audit is proven to run offline.
  - The truth table covers the code after B5, adds `unattended`, and B5 → AC04 is ordered.
  - D7 is added (PR before push, stale `main`), and the `gh` stub contract is widened.
  - L2 lives in the plugin's test root.
  - Pins are discovered by breaking the prose, not by grep.
  - The ledger is in the touch sets.
  - Import boundaries and the `orchestrator.py` constant are fixed.
  - `SHIPWRIGHT_TEST_*` seams get a publish guard.
  - `--from` is covered (S19).
  - Rev 3 has not been reviewed again. Further review is better spent on each unit's own plan review.
- **Rev 3 → rev 4, operator decisions of 2026-10-27:** strictly 1:1; the deviations become findings for a follow-up campaign (programme P17); `Tdev` and the replay variants are removed; models and L3 runs per programme §2.4; B5 is merged.
- **Rev 4 → rev 5, re-cut to programme rev 5 (2026-11-09):**
  - New unit P2p (promise tests through the driver, the lock's hashing); stop 2 now follows P2p.
  - P0 adds the promise list, the protectable-AC count and the P24 "before" measurement. P3 runs the prose-rule map once. P7 removes the approved orphans and writes the saving report.
  - Start conditions: Q1, Q2, B5 and the AC04 iterate are merged; the pilot starts right after the events flip (operator 2026-11-09); no atomic-frs split of FR-01.09 or FR-01.01 meanwhile; the 2026-11-07 measurements are repeated on the starting `main`.
  - The B5 gate ids are filled in (§2). D3 is resolved before the pilot.
  - An optional E2 fork comparison at P2-op and P7-op (programme P23).
  - Opus plan and doubt review (2026-11-09): stops named by their procedures; P2p red is a STRICT-STOP; the STRICT-STOP rule and the event-field check moved into the start conditions; both event layouts pinned; the pin list replaced by the 2026-11-09 measurement (30 tests, 13 files); the fork uses a local remote and the `gh` stub.
