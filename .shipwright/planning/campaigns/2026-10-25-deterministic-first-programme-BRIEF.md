# Deterministic-first plugins: the programme for all 14 plugins

**Stand:** 2026-11-09, rev 5 final (rev 1 → internal Opus plan, architecture and doubt review + external GPT + GLM plan and architecture review; rev 2 → second Opus plan review; rev 4 → operator decisions of 2026-10-27; rev 5 → BP replaced, test baseline added, operator conversations 2026-11-06, -07 and -09, Opus plan, architecture and doubt review integrated; §10) · **Origin:** operator conversation 2026-10-25 ("everything that can be code becomes code; the prompt keeps only what needs an AI")
**What this is:** not a campaign. It fixes the principle, the binding decisions, the per-plugin campaign template (§5), the order and the start conditions. Each plugin gets its own brief instantiated from §5. The first is the pilot `2026-10-25-dfp-pilot-changelog-BRIEF.md`.
**Prerequisite:** the **ac-at-start** campaign (brief `2026-11-01-ac-at-start-BRIEF.md`) is merged first (§2.1); Q1 merged 2026-11-07 (#1014), Q2 phase 1 on 2026-11-08 (#1022, #1023). It replaces the baseline-protection campaign (BP), which was stopped on 2026-10-29 after BL0b: inferring the touched FRs from a diff gave too much noise and too little recall to gate on. The goal BP served stays; this programme reaches it differently: the AC a change keeps or adds is written down **before** the build (ac-at-start), and each converted plugin gets a frozen set of promise tests (P18-P21).

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

The motivating risk: change 199 must never alter change 78's business logic unnoticed. The `baseline-package` brief (2026-10-31) measured how far today's record is from that: of 17 PRs that added behaviour, 11 would be lost in a rebuild from the catalog, all recorded `spec_impact: none`, while the Control Grade read A. And the traceability snapshot of 2026-10-09 binds 980 tests to ACs, every row `executed: not_run`: a binding says a test *claims* an AC, not that it ran green. This programme moves mechanics out of prose **under** promise tests written and frozen against the unchanged plugin (P19) and under behaviour traces, so the move itself cannot regress silently, and it fixes the test-to-AC binding of each plugin as it goes.

**Outside the programme, done:** item 1 was a live AC violation and was fixed as a standalone iterate (#937: the setup returns `suggest_version_bump`'s proposal and Step 3 uses it, with an AC04-bound test). Items 2 and 3 are not fixed by the pilot: they go into its findings report (P17).

**Also outside the programme, now (rev 5).** The programme alone does not deliver two of the operator's goals:
- **Run evidence for AC bindings, in every repo (proposal, operator decision open, §9.7).** Inside a PR the evidence already works in this repo: `ci.yml` regenerates the manifest from the run's JUnit and the keystone AC gate reads that fresh copy. A consumer repo has no such step: the shipped CI templates (`shared/templates/github-actions/`) neither read JUnit nor regenerate the manifest, and Shipwright does not ship a CI for it. A fix that depends on CI therefore helps only this repo. Without CI, F5 stages each run's JUnit into `.shipwright/compliance/evidence/`, but the next run clears that folder, so the release regeneration (the only time the manifest is committed, decided 2026-07-30) sees at most one run and writes `not_run` for the rest. Confirmed by release v0.35.0 (#1016): its regenerated manifest has 1,628 AC links, every one `not_run`. Proposal, in the pattern of `events-drop-files`: each iterate adds one small per-run result file (FR/AC-bound tests only: test id, pass/fail, commit, date). Each PR only adds its own file, so parallel PRs never conflict. The release assembles the newest result per test, marks old ones with their age instead of as a pass, and folds the files. CI in this repo may cross-check, but nothing depends on it. Trust level: local runs, the same as today's F11 evidence; not tamper-proof. Its own brief. It can be designed now. The build waits until the `events-drop-files` S4/S6 follow-ups and Q1 have settled, because all three touch F6 staging, F11 and the derived-file classifiers. The programme does not depend on it: promise tests are run green inside each unit (P19), not read from the manifest.
- **CI time: done outside the programme.** #1002 runs the test tiers as two parallel jobs; CI takes about 12 minutes. Locally F0 already runs the roots in parallel, with xdist on `shared/tests` for the roots on its allowlist. The 23 minutes in MEASURE §3 are a deliberately serial one-process run, not what an iterate pays. Conversion barely moves test time: all changelog-related tests take about 18 s. Its gain is clarity about which test protects which promise.

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

**P10 The inventory is a migration tool.** `inventory.json` (kept with the campaign reports, not under `plugins/*/skills/`, which the PR-review sensitive-path rule blocks for new data) lists every section of `SKILL.md` and every reference file (anchor = file + heading path + content hash) with a class (`judgement`, `ask`, `mechanic`, `rationale`, `method`, `reference`, `runtime-input`) and a target (`cli:<subcommand>`, `keep`, `adr`, `delete`, `pack:<name>`). A file that code reads at runtime (`references/release-notes-prompt.md`) is `runtime-input` + `keep`. It reconciles with the AC-evidence ledger in both directions: rows that claim `enforced` must point at code the skill actually runs. The inventory, its checker and the coverage checks are **retired at the definition of done**; what stays is the ratchet (P12).

**P11 Prose-pin tests are moved, never dropped.** The list of tests that read a skill's prose is produced mechanically, not by hand: every test root is run once with the plugin's `SKILL.md` and references replaced by a placeholder, and every test that fails is a pin (rev 5; the earlier grep for skill and reference paths only seeds the list). For changelog that found 24 tests in 11 files on 2026-11-07 and 30 tests in 13 files on 2026-11-09 (MEASURE §2, §7.3); the list grows with every change to the skill, so P0 measures it on its own starting tree. Guards that check **every** phase skill (canon marker, mode resolution, gate discipline, event-log reference) are not pins to move: they are constraints the thin `SKILL.md` must keep satisfying. Each pin either follows its text or is replaced by a behaviour test in the same diff, with its own FR (for example the canon-marker inventory is bound to FR-01.01, not to the plugin's FR). A pin that encodes a recorded decision (e.g. req3-06 D7: opening the PR stays `prompt-only (judgement)`) is changed only with the operator's sign-off at stop 1 and a ledger update.

**P12 A ratchet keeps converted skills converted.** Registry `shared/config/converted_skills.json`; `shared/scripts/tools/check_prompt_mechanics.py` fails, for registered skills only, on a fenced shell block with more than one command or an `&&`/`|` chain; an inline escape exists and is itself ratcheted. It runs as a `(gate)` step in the `python-checks` job of `ci.yml` and in `verify_local.LOCAL_GATES` (the drift test `test_verify_local_ci_drift.py` keeps the two equal).

**P13 Three test levels.**

| Level | Proves | Model | When |
|---|---|---|---|
| L1 | each CLI subcommand, in process with an injected runner (subprocess-only tests show 0 % diff coverage, and below 80 % merge is blocked) | no | every PR |
| L2 | scenarios against the frozen traces; the truth table; placed in the **plugin's** test root (with `shared/testkit` on `sys.path`, as the run tests do), never in `shared/tests` where `cross_plugin` tests are not collected | no | every PR, within a time budget per plugin; no nightly workflow exists, so nothing is deferred to one |
| L3 | real-model behaviour, the seeded regressions | yes | operator procedure only (§4); never a CI check |

Every seeded regression must be caught by L1 or L2 after conversion; L3 is evidence, not the safety net. New tests carry the anchor of their class (P18): a promise test `pytest.mark.covers` with the FR/AC minted by the producers, a rule test its rule, a module test nothing beyond its location.

**P14 Cache discipline, checked.** A campaign runs on the installed plugin cache, i.e. on the old version of what it rebuilds. Its start and stop conditions check the cache state (`check_plugin_cache_sync.py`); nobody syncs mid-campaign. After the definition of done: a canary in a throwaway repository with a private remote, then the cache sync, then the first real use.

**P15 Docs and decisions in the same diff.** A unit that changes what a plugin reads or writes updates `docs/hooks-and-pipeline.md` in that diff. Guide, glossary (cap test: replace, not only add), `architecture.md`, `conventions.md` in the unit that changes them. ADRs only as decision drops.

**P16 Import boundaries.** A plugin CLI's own modules live in the plugin's `scripts/lib/`; shared modules are imported flat, the way `setup-changelog.py` does, never as `lib.<x>` (ADR-045: two `lib` packages collide). Each CLI gets a boundary test. A sibling plugin's script (e.g. run's `orchestrator.py`) is reached through one constant with an L1 test across the repo and cache layouts (`test_phase_gate_cache_layouts.py` precedent); no general helper exists for it.

**P17 Convert 1:1, report everything else.** A plugin campaign changes **how** the plugin works, never **what** it does: today's behaviour, including what looks wrong, is reproduced exactly. Alongside, the campaign checks whether the plugin does what is expected of it and writes every gap into a **findings report** (`.shipwright/planning/campaigns/<campaign>-FINDINGS.md`), which becomes the brief of a separate follow-up campaign. Sources of "expected": the plugin's FRs and ACs, its `docs/guide.md` chapter, the operator's answers at stop 1, and what the real-model runs show. A finding records: what happens today (evidence: file and line, scenario, or L3 transcript), what was expected and by whom, the affected FR/AC, a severity (`ac-violation`, `contradiction`, `gap`, `missing-ac`, `test-gap`, `model-improvised`, `docs`), and a proposed fix. It is written from T0 onwards and closed at stop 3. **No unit of the campaign fixes a finding.** The operator alone may pull a finding out as a standalone iterate (the AC04 precedent), and only before stop 2 (the traces then characterize the fixed state) or after stop 3, never between them, where the plugin's files belong to the campaign.

**P18 Only promise tests are bound to ACs; every other test keeps its location as its anchor.** The traceability snapshot of 2026-10-09 (`.shipwright/compliance/test-traceability.json`, stale; regenerate before use) lists 16,709 untagged tests against 2,111 FR-tagged ones (about 89 % untagged), and 980 AC-test pairs (967 distinct tests; 254 ACs, 109 of them with exactly one test). Every `executed` field is `not_run` because the local regeneration was not fed JUnit results, so the file shows which test claims which AC, not that it ran. Forcing every test onto an AC would produce ritual tags. Two lasting classes:

| Class | Anchored to | Under change control (P21) |
|---|---|---|
| `promise` | one AC (`pytest.mark.covers`), listed in the plugin's promise list | yes, locked per test |
| everything else | the module it exercises, computed from its location and imports on demand | no |

Two worklists sit beside them; neither is a lasting class:
- **Prose pins.** These are found by breaking the prose (pilot P0.3), not by grep, and moved or replaced at Tw (P11).
- **Orphans.** An orphan is a test whose module no longer exists. Nothing else counts as an orphan: duplicate detection has no tool in this repo. Orphans are removed in Tz from a per-test list the operator approves at stop 3.

No coverage-based "nothing lost" claim is made. Per-test coverage contexts are not configured, subprocess tests show 0 %, and coverage would have to be combined across roots. **A test that already carries `covers` is a promise candidate, whatever it reads.** Example: `plugins/shipwright-changelog/tests/test_skill_event_blocks_behaviour.py` reads `SKILL.md` and is still deterministic AC01 evidence. At stop 1 it is listed as "promise, rebinds to the CLI", never as a pin to remove.

**Scope:** the plugin's own test root plus every test the pin search finds in other roots. Tests outside that scope are not reclassified: there is no repo-wide retagging.

**P19 Promise tests first, against the unchanged plugin, through a driver.** Changing code and its tests in the same step protects nothing. Per plugin:
1. Write the promise tests for the plugin's ACs. They call the per-step **driver interface** of P7, never a module path or a `SKILL.md` block directly. Run them green against the **unchanged** plugin through the replay driver.
2. Freeze them with the traces at stop 2.
3. Convert. The CLI driver is added per unit; the promise tests stay untouched and must stay green through it.
4. Pins move at Tw (P11). Only orphans and leftovers are removed in Tz.

Where today's behaviour lives only in prose that a model reads, the replay driver is the oracle for that AC. It is recorded as `oracle: trace` in the promise list. P0 counts the plugin's ACs by class. If fewer than half get a green driver-level promise test against the unchanged plugin, that is reported at stop 1. The lock then protects little, and the operator decides whether to proceed.

**P20 An AI prose-rule map, tried once in the pilot.** P8b already forces every fenced command and every conditional onto a replay step or an approved `not_replayed` entry. P10 gives every section a target. The open question is whether an AI that maps each moved instruction to its new home (function, test, or `dropped: <reason>`) finds gaps that P8 misses. Code would check the map: every rule listed, every named function and test exists. The pilot runs the map **once**, on P3, as an experiment. Its result goes into the findings report. The programme keeps it only if it found a gap P8 missed. It never blocks a PR. It differs from the parked AI gap check of `baseline-package` (its P4, 63-66 % disagreement): there the AI made an open judgement, here every claim can be checked against code.

**P21 Change control is a lock per test, not an inference.** BP failed because it inferred touched FRs from code. Instead, at stop 2 the plugin's lock file next to the traces (P9) records, per promise test, its id → AC and a hash of its **normalized body**: the AST of the test function and of the fixtures it uses, so formatting and import order do not count.

A later diff that changes, removes or re-anchors a locked test fails the plugin's freeze test, which runs in that test's own root. The diff passes only when an entry in `approved_deltas.json` covers it. An entry is written:
- at an operator stop;
- after stop 3, by a recorded ac-at-start `change` or `remove` item for that AC in the same diff. A change that changes the promise authorizes the matching test change.

An FR split (atomic-frs U2, `fr_split`) keeps each criterion's number and changes only its FR part (`FR-01.11/AC21` becomes `FR-01.22/AC21`), records the move in the spec's `## AC-Move-Map` and rewrites the binding tags. Without an exception, every split would trip the lock of the plugin whose FR was cut. The exception is narrow, because a hand-added map row would otherwise move a locked test onto a different promise with no approval:
- The lock stores the AC id separately and leaves the `covers(...)` id out of the body hash, so a re-anchor is visible as an id change, never as a body change.
- A re-anchor passes only when all of these hold: the move-map row is at the base or is added in the same diff by `fr_split`; it keeps the AC number; the old id is gone from the old FR; the catalog text at the new id equals the text at the base; the body hash is unchanged. Chains of moves are followed to the end.
- Anything else trips the lock: any other row, a body change in the same diff, or a map the lock cannot parse.

The map format is pinned once atomic-frs U2 merges; until then this rule is the specification the lock is built to. AC ids are written `FR-01.11/AC21` in prose and `FR-01.11.AC21` in Q1 records and the catalog; both name the same criterion.

Adding a promise test is free, wherever it goes. **This lock does hold a PR when it trips.** That is deliberate, deterministic and narrow: it trips only on a locked test, never on an inference from the diff. Nothing else in this programme holds a PR.

Files that other plugins' producers write are masked in the traces, so that another plugin's format change cannot turn this plugin's freeze test red.

**P22 Cross-cutting themes are cut once, before the pilot.** Review, stack profile and visual consistency have no FR home today (ac-at-start operator sheet, cases 8 and 9). The rule: a theme that **produces an output** (a review record, a resolved stack profile) becomes a cross-cutting FR with ACs and one named owner, normally a module in `shared/`. A change elsewhere does not count as a change to it. A theme that is a **rule or a quality** (visual consistency, "never delete without asking") goes into the constitution or a gate, and its tests are not promise tests. This matches the existing boundary "an FR is a phase output". The cut is a small operator decision before the pilot (§2.6), expected to be a handful of FRs, not a catalog rework. Q1's measurement (2026-11-07) shows that FR assignment is right in about 60 % of cases on this repo and the WebUI, against 86-96 % on a freshly cut catalog, because a few broad FRs absorb most files. Atomic FRs for new projects, and splitting the broadest FRs in old ones, belong to the **atomic-frs** campaign (brief `2026-11-08-atomic-frs-BRIEF.md`): the scope rule "can this FR still be split" (`shared/fr-authoring.md` §3c), code-found seams (`fr_cluster_report.py`, audit check I10, U1 #1025) and the cut tool `fr_split` (U2, #1027). P22 uses its rules and does not build a second track; it stays limited to the themes the plugin touches. Two consequences for the order:
- A plugin campaign whose FRs the cluster report flags waits until they are split, because a split moves ACs between FRs and so changes `scope_frs` and the promise list. On 2026-11-08 the report flagged FR-01.11 (iterate, the first split), FR-01.03, FR-01.06 and FR-01.07. Changelog's FR-01.09 and FR-01.01 were not flagged.
- While a plugin campaign runs, no split touches its `scope_frs` (overlap, §2.2).

**P23 E2E direction (built outside this programme).** The `integration-tests/e2e-webui` harness builds a fixture app with a real agent. Its checks B01-B46 test the **fixture app's** fit criteria, not Shipwright's ACs. The full run of 2026-11-03 took 389 minutes (operator run data, report `e2e-report/2026-11-03…` in the local `autorune2e` folder, not in the repo), about 80 % of it in five plan+build loops. The target shape:

| Level | What | Where | When |
|---|---|---|---|
| E1 pipeline, no model | the phase chain driven with recorded model answers (the replay of P7 across phases) | `integration-tests/` | PRs that touch a phase it covers (path filter) |
| E2 phase with model | one phase started from a frozen checkpoint of a good run | `integration-tests/e2e-webui` | operator procedure when a phase changes |
| E3 full run | autonomy rehearsal on the fixture app | `integration-tests/e2e-webui` | on request, before a release; not a test and not in CI |

E1 and E2 assert a short list of Shipwright ACs that are observable in a real run (for example "a brief yields requirements with ACs"). B01-B46 keep checking the fixture app and are not relabelled. The model-free `npm run recheck` already re-checks a built app.

This is **its own brief**, not a start condition here. A plugin campaign contributes only what it already produces: its frozen traces are the material E1 replays. E2 matters first for the flow-control group, where one phase consumes the previous phase's output.

**E2 now has a tool** (merged 2026-11-09, #1026): `integration-tests/e2e-webui/fork/fork_run.py --from <run> --at <phase>[:<split>] --repo <checkout>` resets an earlier run's project to the first commit at which that phase could start and continues it with the plugins of `--repo` (identified by the git trees of `plugins/` and `shared/`; it refuses uncommitted changes there). `SHIPWRIGHT_E2E_STOP_AFTER` ends the run after that phase; the app checklist is then not evaluated, so the comparison reads the project's commits, tags and files. For a plugin campaign this gives a same-input comparison: forks from the same run and boundary, once with `--repo` at the commit that closes stop 2 (the plugin is unchanged; only `tests/` and lock files differ from T0) and once at the commit that closes stop 3 (the converted plugin). Rules:
- **Nothing leaves the machine.** The fork's project uses a local bare remote and the `gh` stub, never a real remote or real `gh`.
- **Only normalized output is compared:** tag names and the content they point to, the `CHANGELOG.md` text, event fields without timestamps or hashes, the order of commit subjects.
- **One sample per side is noisy**, so a difference is logged as a finding only if it repeats on a second fork.

It complements L3 at stops 2 and 3 and never replaces it, because it runs one fixture app, not the scenarios. For changelog it needs a run that reached the changelog phase.

**P24 The conversion reports what it saved.** Tz records, for the plugin's test roots:
- the test count and wall-clock before T0 and after Tz (from JUnit durations, one root per process);
- the pins replaced and the orphans removed;
- the prompt lines removed.

The operator's aim: fewer tests that run without anyone knowing what they protect, and shorter CI runs (`shared/tests` measured 1,234 s in the fleet against 273 s alone in the iterate-duration measurement of 2026-10-01; operator notes, not in the repo). Conversion alone will not reach that aim soon: L2 adds tests, and the large pin sets (iterate: 126 files) come last. CI time was handled outside this programme (#1002, §0). No target is set before the pilot has measured one plugin.

## 2. Start conditions for every plugin campaign

1. **ac-at-start Q1 merged** (#1014), checked against artifacts, not a name: `shared/scripts/tools/verifiers/pre_build_ac_check.py` runs at F11 on `main`, and the AC record (`.shipwright/planning/iterate/<run_id>/ac-record.jsonl`, `shared/scripts/lib/ac_record.py`) is written before the build. The record check is **advisory**: it warns at F11 and holds nothing ("nothing holds a PR on this check", `pre_build_ac_check.py`). A 1:1 conversion edits plugin files, so Q1 computes every unit as observable. The answer for a conversion unit is Q1's kind `unchanged`: an existing AC id plus the observable files (`shared/scripts/lib/ac_decision.py`). It is decided without an operator question.

The programme asked Q1 for three adjustments, and #1014 built them:
- (a) An `unchanged` AC passes when a test in the diff names it on an added line **or** when a test that already exists at the base names it (`named_in_base_tests`). Promise tests stay untouched during a conversion (P19), so this is what keeps a unit from warning once per kept AC.
- (b) Each item's `files` must equal *all* the observable files of the diff; every item lists the full set.
- (c) Three modes, ask, auto and off; `auto` is the default under `--autonomous`, so a conversion unit never stops for an AC question. An item Shipwright assigned itself records `mode: auto-assigned`, `unconfirmed: true`, `decided_by` and `confirmed`, and the run ends with the list of unconfirmed items.
- The source check stays: `pre_build_ac_check.py` skips every event whose `source` is not `iterate`.

**What the record can and cannot prove.** The runner declares each item's `kind` itself, and Q1 checks its form, not its truth (§2.7). An `unchanged` item never goes through Q1's assignment step, so it is stamped `decided_by: code`, `confirmed: false` and is never `unconfirmed`. A runner that labels a real add as `unchanged`, with the right files, passes the record, the STRICT-STOP and F11. "Zero warnings" also means only that a test at the base *mentions* the AC id (a comment or a fixture counts), not that a test checks it. Therefore:
- The STRICT-STOP reads the record: any kind other than `unchanged` stops the unit, and so does any `exempt` item that is not a mechanic the plugin brief lists by name (pilot D1). It catches what the runner *declared*.
- What catches a mislabelled unit is the trace freeze (P9) and the promise lock (P21). A unit counts as `unchanged` only when its traces are equal and its lock is unchanged; both are checked in the same diff.
- Coverage of each AC comes from the promise list (P19), never from Q1's mention check.

Mechanics that no AC covers (pilot D1, `update-step`) are recorded as an exemption plus a `missing-ac` finding. The exemption's warning is expected and is named in the PR.

**The F11 dry run is done** (2026-11-09, MEASURE §7.1). It ran the F11 check itself on a real extraction diff in a throwaway branch that was never merged: a squashed unit with one `unchanged` item passes with zero warnings. Three notes:
- The event was written by hand with `--source iterate --adr-id <run_id>`. The check finds the event by `adr_id == run_id` and skips silently otherwise. That a campaign unit runner's event carries both fields is **not yet shown**: the pilot's first unit checks it (pilot start condition 1), and the STRICT-STOP reads the record, not the check.
- Q1's order check ("record before the first code commit") had an empty-line bug that warned falsely on any branch whose record was not in its first commit (fixed by #1029, which also keeps code merged in from `main` and a record the branch leaves untouched out of the check). On a squashed unit the check is vacuous: record and code are the same commit. Record-before-code is therefore checked only on the unit's unsquashed branch.
- Q2 phase 1 is merged (#1022, #1023): the spec-reviewer checks each added or changed AC against the built code, as a warning only (measured 2026-11-07: 5 of 5 altered ACs caught, no false alarm). A conversion unit records only `unchanged` items, so Q2 has nothing to check there; it matters for the follow-up campaigns that change behaviour (§9.4).

The plugin campaign brief lists its FRs as `scope_frs`; a unit that records an AC outside them is a STRICT-STOP for the operator, decided from the record, not inferred from the diff. (BP's start condition, the blocking `Baseline` job, is void: BP was stopped on 2026-10-29.)
2. **No overlap with active campaigns:** no open unit of run campaign B or U, or of the announced campaign that fixes the plugins found faulty in the automated run (project, plan, design and others; operator note 2026-10-27), names a file in the touch set. The pilot additionally waited for **B5** (merged, #926); iterate and run wait for **U** fully merged. Two further campaigns are checked the same way:
- **events-drop-files** changed the changelog's event recording (#1004, #1005, #1013, #1015: Step 7 now stages `shipwright_events.d` too) and has one step left that changes it again, the flip of the layout (S9a). Operator decision 2026-11-09: the operator flips, and the pilot starts right after the flip merges, without the observation period, so T0 and T1 both see the skill after the flip. The flip changes the default for this repo only. The layout is set per project (`events_layout` in `shipwright_sync_config.json`; no setting means `legacy`), and an environment variable can force it. So:
- the trace scenarios pin `events_layout` in their fixture config and run both `legacy` and `drops`;
- the replay and L3 unset `SHIPWRIGHT_EVENTS_LAYOUT` and `SHIPWRIGHT_EVENTS_LAYOUT_TEST`.
- **atomic-frs**: no split names a pilot `scope_frs` while the pilot runs (P22).
3. **The briefs are committed** to `main` through an iterate (a campaign worktree cannot read an untracked file), including any edit made to fill in start-condition data (e.g. the gate ids B5 catalogued).
4. **Budgets and models written down:** L3 runs and spend, wall-clock, the L2 time budget. Models (operator decision 2026-10-27, "build with Sonnet, validate with Opus"): the campaign loop resolves `--finalization-model sonnet` (the unit runners that build) and `--review-model opus --plan-review-model opus` (every reviewer); L3 runs at stops 2 and 3 on Opus, at least three per scenario group and more where the samples disagree, with no fixed cap; at stop 3 one additional Sonnet sample per group, informative only, its differences going into the findings report (P17).
5. **The L3 tool is verified live:** `claude plugin eval --help` lists `--ablation` (checked 2026-10-25); it is still unproven that it can load a plugin from a worktree path and run a scenario with a stub on `PATH` and a scrubbed environment. If it cannot, the fallback is `claude -p --output-format stream-json` in a sandbox, with an operator-chosen permission mode. **Checked 2026-11-09** (MEASURE §7.2): `plugin eval` loads a path, but its cases cannot put a stub on `PATH` or scrub the environment (`EVAL_*` keys only). The fallback works: `claude -p --setting-sources project --plugin-dir <checkout>/plugins/<plugin>` loads only the worktree plugin, and a stub `gh` on `PATH` is used. Without `--setting-sources project` the child loads the operator's settings, plugins and hooks and acts on them, so that flag is mandatory for L3. One probe does not prove isolation. Every L3 run therefore:
- unsets the inherited `SHIPWRIGHT_*` and `CLAUDE_PLUGIN_ROOT` variables (an inherited `SHIPWRIGHT_LOOP_UNIT_ID` makes a run unattended, an inherited `SHIPWRIGHT_SESSION_ID` changes which session it belongs to) and the API keys;
- checks its own init event and aborts unless the plugins are the worktree plugin plus built-ins, the MCP servers are none, and no hook comes from outside that plugin.

The loaded plugin's own hooks fire by design. It reaches `shared/` as `../../shared`, so it is loaded from a full checkout.
6. **The cross-cutting cut is decided** (P22), **only for the themes this plugin touches**: the cross-cutting FRs with their owners, and the themes that go to the constitution or a gate, approved by the operator and committed. It never grows into a catalog rework.
7. **The code-versus-AI convention exists as a file:** `docs/building-skills-plugins-agents.md`, merged 2026-11-09 (#1030). It states the operator decision of 2026-11-02:
   - checks and comparisons in code;
   - interpretation and wording by the AI;
   - code validates every AI output;
   - a fallback when the AI fails.

   The operator sharpened it on 2026-11-09, so that "as deterministic as possible" cannot turn into false determinism:
   - **The deciding question:** can the answer be checked without understanding language? Then code. If not, the AI. A code heuristic that guesses meaning is wrong reliably and looks trustworthy because it is code. atomic-frs is the pattern: code finds the seams, the AI judges whether a sentence states one capability.
   - **Code checks form and rules, not truth.** It can check that every AC appears once, that an id exists, that a file was touched. Whether a wording is right needs a second judge: a review (Q2 is the pattern) or the operator. "Checked by code" never reads as "correct".
   - **The fallback is chosen per AI step, not left to chance:** stop where a wrong answer does harm (a wrong cut, a wrong version), continue with a warning where it is cosmetic. STRICT-STOP and Q2's warning are today's two examples.

   It also links Anthropic's skill guidance (scripts for fragile, exact operations; prose for judgement); the Shipwright rule wins on conflict. It is written as its own small iterate before the pilot starts. The pilot brief points its runners at it. Wiring it into Plan, Build and Iterate edits skills that campaigns B and U own (§2.2), so that waits until after the pilot's stop 3, next to the constitution iterate (§7). It lives in `docs/`, not `shared/prompts/`: it is guidance for authors, not a prompt loaded at runtime, and Q1's surface check treats `shared/prompts/` as runtime.

## 3. Shared pieces and where they are built

| Piece | Built in | Generalized in |
|---|---|---|
| Inventory + coverage checks (P8, P10) | pilot | retired per plugin at its DoD |
| `golden_trace.py`, scenario helpers on `minimal_valid_project`, bare-remote and stub helpers with a fidelity contract | pilot | iterate |
| Prompt-mechanics ratchet (P12) | pilot | stable |
| Conversion checker `check_plugin_conversion.py` | pilot | stable |
| Seeded-regression cases | pilot (3), every campaign adds at least 3 for its FRs | grows |
| Promise list with candidates from existing `covers` tests; orphan list (P18) | pilot | stable |
| Promise lock per test (normalized body) and freeze test (P21), extending the trace lock of P9 | pilot | stable |
| Prose-rule map (P20) | pilot, once, as an experiment | only if it found a gap P8 missed |
| Saving report (P24) | pilot | stable |
| Engine decision, method packs per model class (an explicit `--model-class` argument with a documented default, since `inherit` and local models carry no class) | iterate | flow-control plugins |

## 4. Operator stops (every plugin campaign has exactly three)

1. **Stop 1, after T0:** inventory, truth table, pin list, the proposed promise list read as the plugin's ACs in plain language, with the count of ACs that get a green driver-level test against the unchanged plugin (P18, P19), the findings so far, and the operator's expectations where FRs, ACs and the guide are silent (asked in plain language: "should the plugin do X here?"; the answers are findings, never changes).
2. **Stop 2, after T1:** real-model runs (operator procedure), the reconciliation list (which behaviour is today's where replay and model disagree), `approved_deltas.json`, the trace freeze and the promise lock (P21).
3. **Stop 3, after Tz:** the conversion report, L3 on the **worktree** plugin (resolved plugin root and `SKILL.md` hash recorded; the checker refuses a report whose hash equals the T1 hash), the canary, and the closed findings report (P17), handed over as the input of a follow-up campaign.

Between the stops the campaign is autonomous. A runner never answers a stop's question itself; anything that needs one between stops is a STRICT-STOP.

## 5. The per-plugin campaign template

`branch_strategy: serial` with `depends_on` edges; one PR per unit; the standard review cascade.

| id | Unit | Leaves when |
|---|---|---|
| **T0** | Inventory, truth table, pin list (by breaking the prose); promise list and candidates (P18); findings report opened (P17); ledger reconciled both ways; P24 "before" measurement | checks green → **stop 1** |
| **Ts** | Test seams that the scenarios need (e.g. an injectable binary path or a fixture model), behaviour-neutral when unset, each with an L1 test proving the default is unchanged | only if T0 finds a need |
| **T1** | Trace harness, driver interface, scenarios, reference replay, coverage checks (P8) green on the unchanged skill | green |
| **Tp** | Promise tests for the approved promise list, through T1's driver interface, green against the unchanged plugin; ACs whose only oracle is the replay are marked `oracle: trace` (P19) | green → operator procedure → **stop 2** (traces and promise lock frozen) |
| **T2..Tn** | Extraction into the plugin's CLI, one coherent block per unit, with L1 tests; the prose replaced by one call; traces unchanged; locked promise tests untouched and green through the CLI driver; an `oracle: trace` AC may gain a new promise test here (adding is free); AC record `unchanged` per kept AC, each listing every observable file (§2.1); docs rows in the same diff | traces equal; promise lock unchanged; touch sets disjoint |
| **Tw** | Thin `SKILL.md` (contract below); pins moved (P11) | L2 green |
| **Tr** | Ratchet registration, guide/glossary/architecture, bloat entry lowered last | gates green |
| **Tz** | Conversion check: inventory complete, no `mechanic` left in prose, traces equal apart from approved deltas, P8 coverage, every seeded regression caught by L1/L2, every promise test ran green at this commit and every `oracle: trace` AC is listed as such, the orphan list approved by the operator and removed (P18), the P24 saving report, Codex bundle builds and resolves the CLI (`build_codex_plugin.py`, `verify_codex_plugin_bundle`), `verify_local.py` green | → operator procedure → **stop 3** |

**Stop conditions:** a unit red twice is released with its dependents; T1 or Tp red stops the campaign (stop 2 never runs without a lock); a trace change not in `approved_deltas.json` stops the unit.

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
- **ADR** (decision drop, in the pilot's first extraction unit): "Deterministic-first skills" with P1-P24.
- **Conventions:** the thin `SKILL.md` contract and the CLI shape.
- **Stack profiles:** the pilot's T0 lists every key in `shared/profiles/*.json` that carries a rule or a gate. A profile changes only if it carries a rule this programme moves.

## 8. Risks

- New code is new bug surface (about 44 % of commits since July are fixes, many in this machinery). Code defects reproduce; that is the trade.
- Traces cover only their scenarios: P8 makes the gaps visible and the operator approves each one.
- The model samples are few: they inform stop 2; they never decide alone.
- Calendar: serial campaigns behind ac-at-start, B and U. The end date is set when the pilot's actual duration is known.
- Promise tests written by the same model that converts can share its blind spots. They are written against the unchanged plugin (P19), and the operator reads the promise list at stop 1.
- Most changelog behaviour lives in prose, so many ACs may be `oracle: trace` and the lock may protect little. P0 counts this, and the operator decides at stop 1 (P19).
- The promise lock holds a PR when it trips (P21). Locking per test body and authorizing deltas through a recorded AC change keep it narrow; if it still trips on non-changes in the pilot, the normalization is fixed before the next plugin.
- Existing user projects are not migrated. A 1:1 conversion leaves their artifacts and behaviour as they are; if a conversion would change an artifact format, that is a finding (P17), not part of the conversion.
- Codex and local models stay "untested" until L3 has actually run on them.

## 9. Open decisions for the operator

1. ~~Re-anchor in BP~~: decided 2026-10-27, yes (variant A). Void with BP; a moved or re-anchored promise test is now an `approved_deltas.json` entry under the promise lock (P21).
2. ~~L3 budget and model~~: decided 2026-10-27 (§2.4).
3. The constitution wording (§7).
4. ~~Q2 before the pilot~~: resolved 2026-11-08, Q2 phase 1 is merged as a warning (#1022, #1023; §2.1).
5. The cross-cutting cut (P22, §2.6), using the atomic-frs rules. For changelog the expected answer is "no theme to cut"; the operator confirms it.
6. ~~Control Grade~~: decided 2026-11-06, not part of this programme's start. A grade measure "n of the ACs have a promise test that ran green at this commit" is step 2, after the pilot has produced the first frozen promise list. Until then the grade stays as it is.
7. Run evidence per run (§0): whether to write its own brief now. Recommendation: design now; build after `events-drop-files` S4/S6 follow-ups and Q1 have settled.
8. ~~Pilot and the events flip~~: decided 2026-11-09, the pilot starts right after the flip merges (§2.2).
9. ~~Code-versus-AI convention~~: decided 2026-11-09, a file with the three sharpenings of §2.7, written as its own iterate before the pilot.

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

Rev 5 draft, operator conversation 2026-11-06, after BP was stopped on 2026-10-29 and after the E2E run-findings campaign:
- BP is replaced by ac-at-start Q1 (§2.1).
- Added: four test classes, promise tests first, a hash lock, an AI prose-rule map, a cross-cutting cut, three E2E levels and a saving report.
- Added start conditions: the cut, the convention and the E2 checkpoint.

Reviewed by Opus: plan review (revise; 5 high), architecture review (proceed with changes; 2 high), doubt review (3 high). Integrated in rev 5:
- **Q1 fit (§2.1).** Two F11 rules of `ac_record` conflict with untouched promise tests and with per-AC files: a Q1 adjustment before the pilot. The record check is advisory, not refusing. Mechanics no AC covers are recorded as an exemption plus a finding. The dry run runs the F11 verifier and confirms `source: iterate`. All three reviewers; verified on the Q1 branch.
- **Test classes (P18).** Four classes reduced to `promise` plus "everything else". `rule` was circular. Pins and orphans are worklists. Orphans are limited to tests of a removed module and approved per test, because this repo cannot measure "no coverage lost". Existing `covers` tests are promise candidates, so that `test_skill_event_blocks_behaviour.py` is not deleted.
- **Promise tests (P19).** They go through the P7 driver interface so they survive the move. Tp runs after Ts and T1. Pins move at Tw, not Tz. P0 counts how many ACs can be protected at all.
- **Lock (P21).** Per test body (AST), not per file. Deltas after stop 3 are authorized by a recorded AC change. The brief now states that a tripped lock does hold a PR. Other plugins' files are masked in traces.
- **Prose-rule map (P20).** Reduced to a one-time experiment in the pilot; P8b and P10 already cover most of it.
- **E2E (P23).** Moved to its own brief; the E2 checkpoint is no longer a start condition. E3 is out of CI; E1 is path-filtered.
- **Convention (§2.7).** Exists as a file before the pilot; its wiring into Plan, Build and Iterate waits until after stop 3 because of the B/U overlap.
- **Outside the programme (§0).** Two tracks added: the JUnit → `covers` evidence join, and CI time.
- **Facts.** The `shared/prompts` listing is corrected. AC-test pairs are re-derived (980 pairs, 967 tests, 254 ACs). Sources are given for 389 min and 1,234 s. The ADR covers P1-P24.

Rev 5 update, operator conversation 2026-11-07:
- CI time was solved outside the programme (#1002, about 12 min).
- Run evidence is reframed: CI-independent, one result file per run, assembled at release. The earlier "upload the CI artifact regardless of drift" helps only this repo, because Shipwright ships no CI for it.
- Q1's three modes are added, with point (c): auto-decided items are machine-readable and read by STRICT-STOP. The Q1 session has taken these points.
- P22 defers to the project-plugin brief on atomic FRs.

Rev 5 final, operator conversation 2026-11-09:
- Q1 (#1014) and Q2 phase 1 (#1022, #1023) are merged; §2.1 states what Q1 actually built; §9.4 is resolved.
- §0 item 1 (AC04) is done (#937). Run evidence: v0.35.0 confirms 1,628 of 1,628 links `not_run`.
- P22 points at the atomic-frs campaign; a campaign whose FRs are flagged waits for their split. P21 resolves AC ids through the `## AC-Move-Map`.
- P23: E2 has a tool (`fork_run.py`, merged as #1026); a plugin campaign may compare a fork at its phase with the unchanged and the converted plugin.
- §2.2: the pilot starts right after the events flip; no split touches a running campaign's `scope_frs`.
- §2.7: the convention gets three sharpenings (deciding question, form not truth, chosen fallback) and its own iterate before the pilot.
- Reviewed by Opus (plan review and doubt review of the delta).
  - §2.1 now states that the record proves only what the runner declared; a unit counts as `unchanged` only with equal traces and an unchanged lock; an unlisted `exempt` stops the unit; "zero warnings" is a mention, not coverage; that runner events carry `source` and `adr_id` is not yet shown.
  - P21: the move-map exception is narrowed to rows written by `fr_split` that keep the AC number and the text; the `covers` id is outside the body hash.
  - §2.2: the scenarios pin both event layouts.
  - §2.5: L3 unsets the inherited variables and checks its init event.
  - P23: the fork uses a local remote and the `gh` stub, compares normalized output, and logs only repeated differences.
  - §5: Tp red stops the campaign.

Not taken from review: dropping the cross-cutting cut (kept, limited to the plugin's own themes); dropping P20 entirely (kept as one experiment, because the operator asked for an approach-level check next to result traces).

Not taken: moving the principle out of the constitution (operator's explicit wish; kept with a safer wording and its own approval). Not taken: "no inventory at all": kept, but as a migration tool retired at the definition of done.

Status update 2026-11-09, after rev 5 merged (#1028): the fork tool (#1026), the convention file (#1030, in `docs/` instead of `shared/prompts/`) and the fix of Q1's order check (#1029) are merged; atomic-frs U2 (`fr_split`) is merged as #1027.
