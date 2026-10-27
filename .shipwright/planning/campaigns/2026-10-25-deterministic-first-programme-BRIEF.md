# Deterministic-first plugins: the programme for all 14 plugins

**Stand:** 2026-10-27, rev 4 (rev 1 → internal Opus plan, architecture and doubt review + external GPT + GLM plan and architecture review; rev 2 → second Opus plan review; rev 4 → operator decisions of 2026-10-27; §10) · **Origin:** operator conversation 2026-10-25 ("everything that can be code becomes code; the prompt keeps only what needs an AI")
**What this is:** not a campaign. It fixes the principle, the binding decisions, the per-plugin campaign template (§5), the order and the start conditions. Each plugin gets its own brief instantiated from §5. The first is the pilot `2026-10-25-dfp-pilot-changelog-BRIEF.md`.
**Prerequisite:** the **baseline-protection campaign (BP)** runs first, under its own brief `2026-10-27-baseline-protection-BRIEF.md` (§2). It is unrelated to the completed `brief-driven-run-a-real-gates` campaign, which the run brief also calls "A".

---

## 0. Why

The operator's goal: the FRs and ACs (the baseline) and the tests bound to them stay intact, every change to them is deliberate, and the framework keeps working with models other than the largest one. A rule that lives as prose is a request; a rule that lives as code is a guarantee, is model-independent, and fails reproducibly.

Measured on `main` 2026-10-25 (`SKILL.md` + `references/*.md` + `agents/*.md`; test files under the plugin's `tests/` that mention a skill or reference path):

| Plugin | Prompt lines | Prose-reading test files |
|---|---|---|
| iterate | 10,084 | 126 |
| design | 4,714 | 4 |
| build | 4,132 | 10 |
| adopt | 2,223 | 27 |
| plan | 2,085 | 7 |
| project | 2,027 | 10 |
| test | 1,978 | 4 |
| security | 1,282 | 2 |
| changelog | 1,038 | 3 (plus at least 5 in `shared/tests` and `integration-tests`) |
| deploy | 1,011 | 7 |
| run | 1,008 | 12 |
| compliance | 254 | 5 |
| grade | 226 | 0 |
| preview | 132 | 2 |

What preparing the pilot found in `changelog` alone (verified by three reviewers against the code):

1. **AC04 is violated by the prompt.** `SKILL.md:137-142` tells the model to compute the bump itself ("`BREAKING CHANGE` → major"). AC04 and `git_utils.suggest_version_bump` (`:172-175`) say a break before 1.0 raises the second number. The skill never calls `suggest-version`; `setup-changelog.py` returns no suggestion. The AC-evidence ledger (row 4 of FR-01.09) nevertheless marks AC04 `enforced, tested` by a function the skill never calls. Inferred, not yet observed: a model following the prompt proposes `1.0.0` from `0.x`.
2. **`update-step` contradiction.** Step C forbids `orchestrator.py update-step` in **both** modes (`SKILL.md:54` pipeline, `:60` standalone); Step 7 (`:405-411`) and `references/compliance-evidence.md` call it unconditionally. In a driven run it is inert; in standalone it bootstraps and writes `shipwright_run_config.json` and re-runs the compliance update. No AC covers it: an operator decision, not a defect fix.
3. **Candidate deviation from AC11.** On a feature branch, Step 7 pushes tags and publishes the GitHub Release before the PR is merged, and in autonomous mode merges the PR immediately (`SKILL.md:352-376`). AC11: preparing a release publishes nothing by itself.

The motivating risk: change 199 must never alter change 78's business logic unnoticed. BP makes that a code guarantee. This programme then moves mechanics out of prose **under** that guarantee and under behaviour traces, so the move itself cannot regress silently.

**Outside the programme, now:** item 1 is a live AC violation and is fixed as a standalone iterate (Step 3 calls `suggest-version`, the setup returns it, an AC04-bound test, the ledger row corrected). Items 2 and 3 are not fixed by the pilot: they go into its findings report (P17).

## 1. Design decisions (binding for every plugin campaign)

**P1 Code first, prompt for judgement.** Everything that can be decided mechanically becomes a function or a CLI with tests. The prompt keeps the judgement, the questions to the user, and one line per tool call.

**P2 No new runtime layer until a plugin needs flow control.** The mechanics group (§6) is converted to **one CLI per plugin** (subcommands with JSON in and out) plus a thin `SKILL.md`. No step engine, no `workflow.json`, no task files. Whether flow control needs a shared engine is decided **in the iterate campaign** and nowhere earlier, starting from the question "extend `shared/scripts/lib/autonomous_loop.py` (it already has `next`/`record`, `depends_on` readiness, result validation, locks) or build something new", and how it composes with run's single-session loop. An engine, if any, is frozen only after a third, unlike plugin has used it.

**P3 The agent stays in the loop.** No headless driver steers the model. The agent runs in the operator's session, calls the CLIs, and keeps the conversation; the operator can interrupt at any point.

**P4 Outward-facing actions stay visible.** `git push`, tag pushes, `gh pr create`/`merge`, release publishing, and anything else that leaves the machine are **never** moved behind a generic CLI. The agent runs the literal command, so the `PreToolUse` Bash guard (`validate_command.sh`, the constitution's NEVER enforcement) and the permission rules see it. Where such a call already sits inside a script today (`publish_release_notes.py`), it stays as it is: no new hiding.

**P5 No state where it does not belong.** A converted CLI writes only what the skill writes today. Read-only skills (`grade`, FR-01.18; `security` on a foreign repository, FR-01.07) write nothing into the target tree; an L1 test asserts the tree is byte-identical afterwards.

**P6 Today's decision semantics are preserved exactly.** Every question the skill asks today, and every place it skips one (`autonomy`, mode), is written down as a **mode × autonomy truth table** (data, in the plugin brief), approved by the operator at stop 1, and pinned by L2 tests. The table describes the code **as it is when the campaign starts**: where run campaign B5 has already catalogued a plugin's questions (gate id, catalog default, `unattended` behaving at least as `autonomous`), those cells are part of today's semantics and are reproduced as they are. A conversion never moves a further question into `gate_policy` (which keys on run mode, not autonomy); that is a separate, explicit change, after run campaign U has defined the gate-pending shape (U2).

**P7 Behaviour traces, stated honestly.** Today the "before" behaviour is a model reading prose, so no run of it is deterministic. The trace is therefore an **operator-approved oracle** of today's behaviour, built from two sources: a **reference replay** (a test helper that runs the command sequence the current prose prescribes, each command citing its line) and **real-model runs** of the unchanged skill (at least three per scenario group, operator procedure). Differences between them are listed and decided by the operator, never picked by the runner. What the trace records (`shared/testkit/golden_trace.py`, standard library only, ADR-044):
- per commit: `git diff-tree --name-status` against the parent and the normalized content of the changed blobs; commit subjects in order;
- refs: tag → target commit (by subject or ordinal, not SHA), branch heads, the refs of a local bare `origin`;
- the final `git status --porcelain` and the normalized working-tree files the skill writes (including `shipwright_run_config.json` and generated compliance documents);
- the **values** of a whitelist of semantic output fields (`status`, reason prefixes, `section_action`, `changelog_updated`, `version`, pathspec lists), exit codes, and the ordered argv log of every stubbed external binary;
- judgement output (release-note prose, condensed summaries) is **masked** by an explicit rule in the normalizer's contract;
- timestamps, SHAs, run and session ids and absolute paths are normalized.
- **One scenario, several drivers.** A scenario calls a per-step driver interface. The **replay driver** (today's prose) is frozen with the traces; each extraction unit adds the **CLI driver** for the steps it moves, in its own touch set, and must produce the same trace. The inverse coverage check (P8b) runs against a copy of the prose pinned by hash at stop 2, not the live `SKILL.md`.

**P7a Isolation of everything a scenario spawns.** T0 lists, mechanically, every subprocess and network call on each scenario path (binaries, `uv run --with` resolutions, audits, model calls). Each one is either stubbed through a seam, proven to run offline, or listed as a reason the scenario cannot exist. Scenarios build their environment explicitly (no inherited keys; a fake GitHub owner/repo; `GIT_ALLOW_PROTOCOL=file`); nothing imports a module that loads `.env.local` from the developer's checkout. Real-model runs (stops 2 and 3) load the plugin **from a directory at a recorded commit** (hash in the report), never from the installed cache, so the seams are present and real `gh`/GitHub is unreachable.

**P8 Coverage is checked mechanically, in both directions.** (a) Every inventory entry of class `mechanic`, `ask` or `judgement` names at least one scenario that exercises it, or carries `not_exercised` with a reason the operator approves. (b) Every fenced command and every conditional in the prose maps to a replay step or a `not_replayed` entry. (c) Every AC of the plugin is asserted by at least one scenario's oracle, or is listed as judgement-only. AC coverage alone is not enough: one AC hides several branches.

**P9 Frozen baselines.** After the operator stop that approves the traces, the golden files and `golden_trace.py` are frozen by content hash in a lock file. A later diff to either fails CI unless it matches `approved_deltas.json` (scenario, field, before, after, approver, date), which is written only at an operator stop. Because a conversion is 1:1 (P17), the deltas are rare: a place where the replay and the real-model runs disagree about today's behaviour, decided at stop 2. The freeze is enforced by a test in the plugin's own test root (CI already runs it). The lock file and `approved_deltas.json` reach `main` through an iterate opened right after the stop.

**P10 The inventory is a migration tool.** `skills/<skill>/inventory.json` lists every section of `SKILL.md` and every reference file (anchor = file + heading path + content hash) with a class (`judgement`, `ask`, `mechanic`, `rationale`, `method`, `reference`, `runtime-input`) and a target (`cli:<subcommand>`, `keep`, `adr`, `delete`, `pack:<name>`). A file that code reads at runtime (`references/release-notes-prompt.md`) is `runtime-input` + `keep`. It reconciles with the AC-evidence ledger in both directions: rows that claim `enforced` must point at code the skill actually runs. The inventory, its checker and the coverage checks are **retired at the definition of done**; what stays is the ratchet (P12).

**P11 Prose-pin tests are moved, never dropped.** The list of tests that read a skill's prose is produced mechanically (a grep for skill and reference paths across every test root and `shared/scripts`), not by hand. Each pin either follows its text or is replaced by a behaviour test in the same diff, with its own FR (for example the canon-marker inventory is bound to FR-01.01, not to the plugin's FR). A pin that encodes a recorded decision (e.g. req3-06 D7: opening the PR stays `prompt-only (judgement)`) is changed only with the operator's sign-off at stop 1 and a ledger update.

**P12 A ratchet keeps converted skills converted.** Registry `shared/config/converted_skills.json`; `shared/scripts/tools/check_prompt_mechanics.py` fails, for registered skills only, on a fenced shell block with more than one command or an `&&`/`|` chain; an inline escape exists and is itself ratcheted. It runs as a `(gate)` step in the `python-checks` job of `ci.yml` and in `verify_local.LOCAL_GATES` (the drift test `test_verify_local_ci_drift.py` keeps the two equal).

**P13 Three test levels.**

| Level | Proves | Model | When |
|---|---|---|---|
| L1 | each CLI subcommand, in process with an injected runner (subprocess-only tests show 0 % diff coverage, and below 80 % merge is blocked) | no | every PR |
| L2 | scenarios against the frozen traces; the truth table; placed in the **plugin's** test root (with `shared/testkit` on `sys.path`, as the run tests do), never in `shared/tests` where `cross_plugin` tests are not collected | no | every PR, within a time budget per plugin; no nightly workflow exists, so nothing is deferred to one |
| L3 | real-model behaviour, the seeded regressions | yes | operator procedure only (§4); never a CI check |

Every seeded regression must be caught by L1 or L2 after conversion; L3 is evidence, not the safety net. New tests carry `pytest.mark.covers` with FR/AC minted by the producers.

**P14 Cache discipline, checked.** A campaign runs on the installed plugin cache, i.e. on the old version of what it rebuilds. Its start and stop conditions check the cache state (`check_plugin_cache_sync.py`); nobody syncs mid-campaign. After the definition of done: a canary in a throwaway repository with a private remote, then the cache sync, then the first real use.

**P15 Docs and decisions in the same diff.** A unit that changes what a plugin reads or writes updates `docs/hooks-and-pipeline.md` in that diff. Guide, glossary (cap test: replace, not only add), `architecture.md`, `conventions.md` in the unit that changes them. ADRs only as decision drops.

**P16 Import boundaries.** A plugin CLI's own modules live in the plugin's `scripts/lib/`; shared modules are imported flat, the way `setup-changelog.py` does, never as `lib.<x>` (ADR-045: two `lib` packages collide). Each CLI gets a boundary test. A sibling plugin's script (e.g. run's `orchestrator.py`) is reached through one constant with an L1 test across the repo and cache layouts (`test_phase_gate_cache_layouts.py` precedent); no general helper exists for it.

**P17 Convert 1:1, report everything else.** A plugin campaign changes **how** the plugin works, never **what** it does: today's behaviour, including what looks wrong, is reproduced exactly. Alongside, the campaign checks whether the plugin does what is expected of it and writes every gap into a **findings report** (`.shipwright/planning/campaigns/<campaign>-FINDINGS.md`), which becomes the brief of a separate follow-up campaign. Sources of "expected": the plugin's FRs and ACs, its `docs/guide.md` chapter, the operator's answers at stop 1, and what the real-model runs show. A finding records: what happens today (evidence: file and line, scenario, or L3 transcript), what was expected and by whom, the affected FR/AC, a severity (`ac-violation`, `contradiction`, `gap`, `missing-ac`, `test-gap`, `model-improvised`, `docs`), and a proposed fix. It is written from T0 onwards and closed at stop 3. **No unit of the campaign fixes a finding.** The operator alone may pull a finding out as a standalone iterate (the AC04 precedent), and only before stop 2 (the traces then characterize the fixed state) or after stop 3, never between them, where the plugin's files belong to the campaign.

## 2. Start conditions for every plugin campaign

1. **BP merged and flipped to blocking** (brief `2026-10-27-baseline-protection-BRIEF.md`, unit BL6), checked against named artifacts, not a name: the `Baseline` CI job in `--mode block` and required; the `shipwright/finalization-verifier` commit status required, and `deliver_pr.py` and campaign step 3g refusing a head without it; R3 (`spec_impact: none` with a normative spec change) an error. The plugin campaign brief lists its FRs as `scope_frs`, so a unit that touches an FR outside them is held for the operator; tests a conversion only moves are recognized as "moved" (re-anchor, operator decision 2026-10-27, variant A, made mechanical in BP).
2. **No overlap with active campaigns:** no open unit of run campaign B or U, or of the announced campaign that fixes the plugins found faulty in the automated run (project, plan, design and others; operator note 2026-10-27), names a file in the touch set. The pilot additionally waits for **B5** (it edits the changelog asks in `gate_catalog.json` and the `autonomy` lines of `changelog/SKILL.md`); iterate and run wait for **U** fully merged.
3. **The briefs are committed** to `main` through an iterate (a campaign worktree cannot read an untracked file), including any edit made to fill in start-condition data (e.g. the gate ids B5 catalogued).
4. **Budgets and models written down:** L3 runs and spend, wall-clock, the L2 time budget. Models (operator decision 2026-10-27, "build with Sonnet, validate with Opus"): the campaign loop resolves `--finalization-model sonnet` (the unit runners that build) and `--review-model opus --plan-review-model opus` (every reviewer); L3 runs at stops 2 and 3 on Opus, at least three per scenario group and more where the samples disagree, with no fixed cap; at stop 3 one additional Sonnet sample per group, informative only, its differences going into the findings report (P17).
5. **The L3 tool is verified live:** `claude plugin eval --help` lists `--ablation` (checked 2026-10-25); it is still unproven that it can load a plugin from a worktree path and run a scenario with a stub on `PATH` and a scrubbed environment. If it cannot, the fallback is `claude -p --output-format stream-json` in a sandbox, with an operator-chosen permission mode.

## 3. Shared pieces and where they are built

| Piece | Built in | Generalized in |
|---|---|---|
| Inventory + coverage checks (P8, P10) | pilot | retired per plugin at its DoD |
| `golden_trace.py`, scenario helpers on `minimal_valid_project`, bare-remote and stub helpers with a fidelity contract | pilot | iterate |
| Prompt-mechanics ratchet (P12) | pilot | stable |
| Conversion checker `check_plugin_conversion.py` | pilot | stable |
| Seeded-regression cases | pilot (3), every campaign adds at least 3 for its FRs | grows |
| Engine decision, method packs per model class (an explicit `--model-class` argument with a documented default, since `inherit` and local models carry no class) | iterate | flow-control plugins |

## 4. Operator stops (every plugin campaign has exactly three)

1. **Stop 1, after T0:** inventory, truth table, pin list, the findings so far, and the operator's expectations where FRs, ACs and the guide are silent (asked in plain language: "should the plugin do X here?"; the answers are findings, never changes).
2. **Stop 2, after T1:** real-model runs (operator procedure), the reconciliation list (which behaviour is today's where replay and model disagree), `approved_deltas.json`, the trace freeze.
3. **Stop 3, after Tz:** the conversion report, L3 on the **worktree** plugin (resolved plugin root and `SKILL.md` hash recorded; the checker refuses a report whose hash equals the T1 hash), the canary, and the closed findings report (P17), handed over as the input of a follow-up campaign.

Between the stops the campaign is autonomous. A runner never answers a stop's question itself; anything that needs one between stops is a STRICT-STOP.

## 5. The per-plugin campaign template

`branch_strategy: serial` with `depends_on` edges; one PR per unit; the standard review cascade.

| id | Unit | Leaves when |
|---|---|---|
| **T0** | Inventory, truth table, mechanical pin list; findings report opened (P17); ledger reconciled both ways | checks green → **stop 1** |
| **Ts** | Test seams that the scenarios need (e.g. an injectable binary path or a fixture model), behaviour-neutral when unset, each with an L1 test proving the default is unchanged | only if T0 finds a need |
| **T1** | Trace harness, scenarios, reference replay, coverage checks (P8) green on the unchanged skill | → operator procedure → **stop 2** (freeze) |
| **T2..Tn** | Extraction into the plugin's CLI, one coherent block per unit, with L1 tests; the prose replaced by one call; traces unchanged; docs rows in the same diff | traces equal; touch sets disjoint |
| **Tw** | Thin `SKILL.md` (contract below); pins moved (P11) | L2 green |
| **Tr** | Ratchet registration, guide/glossary/architecture, bloat entry lowered last | gates green |
| **Tz** | Conversion check: inventory complete, no `mechanic` left in prose, traces equal apart from approved deltas, P8 coverage, every seeded regression caught by L1/L2, Codex bundle builds and resolves the CLI (`build_codex_plugin.py`, `verify_codex_plugin_bundle`), `verify_local.py` green | → operator procedure → **stop 3** |

**Stop conditions:** a unit red twice is released with its dependents; T1 red stops the campaign; a trace change not in `approved_deltas.json` stops the unit.

**Thin `SKILL.md` contract:** purpose and trigger (the description stays word for word: routing depends on it); the judgement it asks for; how mode is resolved (pass `--phase-task-id` when handed one: the integration pin stays on `SKILL.md`); one line per CLI call and per literal outward command; the questions from the truth table; references. No shell choreography, no rationale history.

## 6. Plugin groups and order

| Group | Plugins | What becomes code |
|---|---|---|
| Mostly mechanics | changelog, preview, grade, compliance, deploy, security | almost everything, as one CLI per plugin |
| Flow control | iterate, build, test, plan, run | flow, gates, recording; writing code and tests, reviews and root-cause work stay judgement |
| Conversation | project, design, adopt | little; the interview stays judgement |

Order: changelog (pilot) → the rest of the mechanics group → iterate (engine decision) → build, test, plan, then run → conversation group, or not at all where the inventory shows little mechanics. Each campaign starts after the previous one's stop 3, the cache sync and one real use. **Stopping after the mechanics group is an acceptable outcome**: it carries most of the value at the least risk.

## 7. Shipped guidance

- **Constitution** (operator wish: the shipped constitution states the principle). Because `shared/constitution.md` is read from the working tree by every concurrent iterate and by every target project, it lands **after the pilot's stop 3**, as its own small iterate with the wording approved by the operator. Proposed text, written so it cannot loosen other rules: "ALWAYS: enforce a rule that can be checked mechanically with code, a test or a gate rather than with an instruction. The agent stays free in how it reaches the goal; ASK FIRST and NEVER apply regardless." Reviewer objection recorded (§10): it is a maintainer principle and could pull against "no features beyond the spec"; the operator decides.
- **ADR** (decision drop, in the pilot's first extraction unit): "Deterministic-first skills" with P1-P15.
- **Conventions:** the thin `SKILL.md` contract and the CLI shape.
- **Stack profiles:** the pilot's T0 lists every key in `shared/profiles/*.json` that carries a rule or a gate. A profile changes only if it carries a rule this programme moves.

## 8. Risks

- New code is new bug surface (about 44 % of commits since July are fixes, many in this machinery). Code defects reproduce; that is the trade.
- Traces cover only their scenarios: P8 makes the gaps visible and the operator approves each one.
- The model samples are few: they inform stop 2; they never decide alone.
- Calendar: serial campaigns behind BP, B and U. The end date is set when the pilot's actual duration is known.
- Codex and local models stay "untested" until L3 has actually run on them.

## 9. Open decisions for the operator

1. ~~Re-anchor in BP~~: decided 2026-10-27, yes (variant A, §2.1).
2. ~~L3 budget and model~~: decided 2026-10-27 (§2.4).
3. The constitution wording (§7).

## 10. Review log

Rev 1 reviewed by: internal Opus plan review (revise; 4 blockers), internal architecture review (revise; 2 blockers), internal doubt review (15 doubts, 9 high), external plan review GPT + GLM (both revise), external architecture review GPT + GLM (both revise). Integrated in rev 2:
- The step engine is removed from the pilot and the mechanics group; the engine question moves to the iterate campaign, framed against `autonomous_loop` (all architecture reviewers).
- Outward-facing actions stay literal commands (P4: they would otherwise bypass `validate_command.sh`).
- No state in read-only targets (P5).
- Today's ask/autonomy semantics frozen as a truth table instead of routed through `gate_policy` (P6).
- The trace definition widened to values, commit content, tag targets, remote refs, `git status`, stub argv, judgement masking (P7).
- Two-directional coverage checks (P8), frozen baselines with `approved_deltas.json` (P9), the inventory as a migration tool with `runtime-input` (P10), a mechanical pin list (P11), the CI job named correctly (P12), in-process L1 for diff coverage (P13), cache check and throwaway canary (P14), same-diff docs (P15).
- "Campaign A" renamed BP with artifact-based conditions; three explicit operator stops; L3 on the worktree plugin with a hash check; defect 1 split out as a standalone iterate; defect 2 reclassified as an operator decision; AC11 added as a candidate; the constitution line moved after the pilot.

Rev 2 reviewed by a second Opus plan review (revise: 7 of 11 first-round blockers closed; 4 new blockers, all in the test harness). Integrated in rev 3: real-model runs load the plugin from a recorded commit, not the cache (P7a); deviation "after" oracles approved at stop 2 so `Tdev` needs no stop (P9); per-step drivers, replay frozen, CLI drivers added per unit, P8b against pinned prose (P7); mechanical isolation of every spawned process and of `.env.local` (P7a); the truth table describes the code after B5 (P6); L2 in the plugin's test root, no nightly deferral (P13); freeze enforced by a test and committed by an iterate (P9); import boundaries (P16).

Rev 4, operator decisions of 2026-10-27 (not reviewed separately; they remove scope): conversions are strictly 1:1 and every gap goes into a findings report that seeds a follow-up campaign (P17), so the `Tdev` unit and the deviation replay variants are gone; build with Sonnet, validate with Opus, L3 runs uncapped where samples disagree (§2.4); re-anchor yes, variant A (§2.1); the announced fix campaign for the run plugins joins the overlap check (§2.2).

Not taken: moving the principle out of the constitution (operator's explicit wish; kept with a safer wording and its own approval). Not taken: "no inventory at all": kept, but as a migration tool retired at the definition of done.
