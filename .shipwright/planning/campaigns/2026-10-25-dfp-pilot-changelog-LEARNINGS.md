# LEARNINGS: deterministic-first pilot of `/shipwright-changelog`

**Opened** by unit P0 on 2026-11-14 from the template of brief section 8 (fixed headings, so the reports of several plugins compare). Every unit appends what it learned while it is fresh; P7 closes it; stop 3 reads it with the findings report. Plain facts, measured where possible. It never blocks a PR.

## 1. Steps and effort

| Step | Unit | PR | Review rounds | Wall-clock | Tokens | What took longer than expected |
|---|---|---|---|---|---|---|
| Inventory, truth table, subprocess map, checker, findings, ledger reconcile, pin list, promise list, P24 before-measurement | P0 | (filled when the PR opens) | architecture review: 1 reject (overruled by the brief), plan review: revise x2 | started 2026-11-13 23:57 UTC; stop-1 hand-over time in the PR | not measured by the runner | the pin measurement: `shared/tests` alone ran about 30 minutes on a busy machine (MEASURE section 7.3: 1,802 s); the architecture review halted the unit once and needed an orchestrator answer |
| Seams and offline proof (one `gh` argv-prefix helper, fixture model for condensation, offline `--verify-commit --release-audit` proof) | P1 | (filled when the PR opens) | architecture review: approve x2 (internal and external); plan review: approve and revise (4 items, 3 taken); code cascade: see PR | one unit run 2026-11-17 | not measured by the runner | the reviews, not the code: the code was about 150 lines, three review calls and the cascade took most of the run; a backgrounded review call was killed when the shell call ended and had to be re-run in the foreground |
| Harness: scratch project, `gh` stub, trace recorder, driver interface, freeze check | P2a | (filled when the PR opens) | architecture review: approve x2 (external) and proceed (internal); plan review: revise x2 (findings taken: git config isolation, seeded-credential test, corrupt stub state, argv path normalization) | one unit run 2026-11-17 | not measured by the runner | the trace normalizer: three real differences between two identical scratches (compact run ids, Windows path separators, tracked files left dirty by the last phase) each needed a test-first fix |
| Replay driver, oracle, scenarios S1-S9 (S1t added), harness hardening from the P2a reviews | P2b1 | (filled when the PR opens) | see PR | one unit run 2026-11-17 | not measured by the runner | the scenarios, not the driver: running today's prose literally showed three ways the release cannot finish (D21-D23), each found by reading a refused exit, and the traces take about 25 KB each because the scratch's own history is in every one |
| Scenarios S10-S19 (S1d added, S16 split into six, S17 and S18 into two each), `close-phase`, coverage checks P8a-c, three seeded regressions, full-chain comparison of the frozen chains | P2b2 | (filled when the PR opens) | see PR | one unit run 2026-11-17 | not measured by the runner | finding what makes a refusal happen (an evidence refusal, a rejected push, a missing `gh`) took more time than writing the scenario: each needed one probe run, and two of three failed on a word the tool does not use (`manifest_missing` before `unsupported_format`, `content_floor`, not `failed`) |
| Promise tests, extraction, thin `SKILL.md`, ratchet, conversion check, operator procedures | P2b2-P7-op | not started | | | | |

## 2. Code or AI decisions

The deciding question of the convention (`docs/building-skills-plugins-agents.md`): can the answer be checked without understanding language? Inventory class of each moved instruction, first pass (P0):

| Instruction | Decision | Why |
|---|---|---|
| propose the next version from commit types (Step 3) | code | the rule is AC04; `suggest_version_bump` returns it; a test checks it |
| render the changelog section from the drops, number the ADRs (Step 4) | code | output compared byte for byte |
| commit by explicit pathspec, verify the commit, tag only on exit 0 (Step 6) | code | every step has an exit code and a postcondition in git |
| read each changed migration page and write the upgrade-note drop (Step 4, release-workflow) | AI | needs reading comprehension; code can only check that a drop exists |
| edit the previewed entry as the operator describes (Step 5) | AI | free-text instruction; the result is not checkable without understanding it |
| condense the release section for the release page (Step 7) | AI wrapped in code | the model writes, `validate_release_notes.py` checks the shape; already the target pattern |
| open the PR, merge it, push tags (Step 7) | neither: outward command | stays a literal command in the prompt (programme P4); not decided by judgement, but not safe to run from code without the operator's authority |
| accept or type another version (Step 3), accept or cancel the preview (Step 5) | ask | the operator's decision; the question is a row of the truth table |

Changed after review: nothing yet (P0 only).

## 3. Recurring patterns

- The AI judges and code validates: the release-page condensation and (proposed) the upgrade-notes drop.
- A mixed section is the normal case: Step 4 and Step 7 each carry five to eight instructions of three classes, so a section is not the unit of conversion; the instruction is. The inventory therefore lists `parts` for a `mixed` section.
- Where two sources disagree, the prose contradicts itself more often than it contradicts the code (D1, D8, D10, D11): the code is the safer oracle, and the real-model runs decide the rest.

## 4. Pitfalls

- **A green test on a function the skill never calls.** The AC02 `covers` tests exercise `lib/changelog.py`, which no step calls; the ledger rated AC02 `enforced, tested` for months. Found by tracing the skill's own path from `SKILL.md` to the tool it runs, not by reading test names (finding D13; ledger row 2). The AC04 iterate had found the same shape once before.
- **The brief's own numbers and line citations go stale.** "Seven references" (there are ten), three moved line citations, a pre-assessment table that missed the event fold and the upgrade-notes check. Re-measure from the tree the unit starts on, and let a checker hold the citations.
- **A checker test on the real tree is a CI pin.** A first version of the checker's tests also ran it on the real skill; the spec reviewer pointed out that CI runs that test root, so every prose edit would red CI and the ADR's claim "out of CI" would be false. The tests now use throwaway skills only; the pilot's units run the CLI on the real one. The same review caught a `covers` mark on that test (a ritual tag, the D13 mistake).
- **A review can reject what the operator approved.** The architecture review rejected the inventory checker that the brief and programme P10 mandate; the unit halted until the orchestrator overruled the reject by pointing at the brief. Brief the reviewers with the approved scope, or expect one halt per unit that builds a mandated mechanism.
- **Data a conversion tool needs does not belong under `plugins/*/skills/`.** The three inventory data files were first filed next to `SKILL.md`; the PR-review sensitive-path rule blocks new content there even though nothing reads it at runtime, which cost one PR-review round and a move. File such data with the campaign reports.
- **A seam that can publish needs a second, independent guard (P1).** The first guard keyed only on a marker sentence in the notes; both external plan reviewers and the internal architecture reviewer pointed out that a lost or quoted marker is then the only defence. The guard now also refuses whenever the fixture-model variable is set without the `gh` seam, and the marker is a hard-to-collide token.
- **"Offline" has to be proven with the network actually blocked (P1).** The scratch-project proof sets `UV_OFFLINE=1`, a dead proxy and no keys; a test that merely runs on a warm machine proves nothing. Its one soft spot is the pyyaml fetch of `uv run --with pyyaml`, so the test warms uv's cache first and skips only when that fails.
- **A `.cmd` shim cannot be a `gh` stand-in on Windows (P1).** `gh` is spawned as `["gh", ...]`; the seam is an argv prefix read from a JSON array (shell-style splitting mangles backslash paths), and a malformed value is refused instead of falling back to the real `gh`.
- **Two identical scratch projects still differ (P2a).** Run the same build twice in two directories and diff the traces before trusting a recorder: the first diff showed compact timestamps in run ids (`project-20261117-125101955883`), Windows backslashes after a path label (so a Windows trace would never equal a Linux one) and files the last phase rewrites after its own commit (an unclean start tree). The byte-identical-twice test is the cheapest guard a normalizer can have.
- **An environment allowlist is not enough on its own (P2a).** Both plan reviewers asked for the same three extras: a seeded credential VALUE must not survive (not only the name), the user's git config and hooks must not reach the scratch (a hostile global config with a failing `pre-commit` and `commit.gpgsign` is a test), and the parent process environment must stay untouched. `minimal_valid_project` runs git under the process environment, so the builder swaps HOME for the duration of its calls.
- **A freeze test cannot tell an unstarted freeze from a deleted lock (P2a).** No lock file reads as unfrozen, so the stop-2 iterate must be reviewed for the lock's existence; the check itself (changed, missing, unlocked trace, delta that does not name exactly the change) is tested on synthetic trees.
- **Do not tag a harness test with a requirement it does not exercise (P2a).** Only the test that runs the real release script against the stub carries `covers FR-01.09/AC14`; the other harness tests carry none (the ritual-tag mistake of P0).
- **Run the prose literally and the findings appear (P2b1).** The first full replay of Step 6 failed three ways before any scenario asserted anything: a pathspec naming a directory the project has no tracked file in (D21), a tracked drop whose deletion the pathspec leaves out (D22), and an event recorded by Step 5.5 that nothing commits (D23), each ending at the audit's "dirty working tree" refusal. Prose that works for a model that improvises does not work for a replay; the replay records the refusal as today's behaviour and the findings file carries the decision to the operator.
- **A trace that must be equal on two operating systems needs a short list of fields (P2b1).** Step output keeps only whitelisted facts; error text, absolute paths and tool output stay out of the trace and are asserted in the scenario instead. Both layouts of the events log are separate traces only where they differ (S1, S2); the rest have one.
- **Citations are data, the lines are checked (P2b1).** `CITES` maps each replayed command to its `SKILL.md` line and a needle; a test fails when the live line no longer holds it, and a second test keeps the table and the driver's command keys equal. P5 (thin `SKILL.md`) will red the first test on purpose: it must point at the pinned prose copy of stop 2 by then.
- **Check `git status` through a function that does not strip (P2b1).** `strip()` turned ` D path` into `D path` and a wrong expected value took three runs to find.
- **Make the oracle prove that a scenario used it (P2b2).** `Scenario.acs` lists the ACs a scenario is tagged with and `verify` fails when the oracle never judged one of them (`oracle.ASSERTED`). The first run of that rule caught S1 asserting its version outside the oracle. A scenario check that compares a literal is not the oracle, however it is named.
- **A refusal is judged by its kind, not by its exit code (P2b2).** Every refusal scenario names the tool's own word (`verify_mismatch`, `content_floor`, `unsupported_format`, the audit's dirty-tree sentence), read from the tool's JSON where it has one. A message that an operating system words (a missing program) is asserted by exit code only.
- **Seed the regression into the instrument, not into the product (P2b2).** The three seeded regressions swap one frozen command or one step of the replay and run the scenario that must notice (`test_seeded_regressions.py`); each asserts the oracle's own message, so a crash further down cannot pass for a catch.
- **A coverage check needs a table that fails when it goes stale (P2b2).** P8a-c are three small functions over the inventory, the prose and the scenarios; each test has a twin that feeds it a broken input and expects red, because a check that cannot go red is not yet a check.
- **Typed heredocs corrupt files with quotes and backticks** (a Python script with an apostrophe in a string ended the heredoc early): write scripts with the Write tool.

## 5. Tools

| Tool | Class | What a generic version would need |
|---|---|---|
| break-the-prose measure (replace the prompt files with a placeholder, run every test root once, list what fails) | generic | a list of the prompt files and the repo's test roots; one process per root |
| `check_skill_inventory.py` (anchors by heading path and content hash, class/target vocabulary, truth-table and subprocess-map line checks) | generic in method, written against this repo's skill layout (`SKILL.md` + `references/`) | the skill folder convention and a class vocabulary |
| truth table `{context} x {autonomy} x {question}` with a citation per cell | generic | the list of modes and questions |
| subprocess map with a needle per line | generic | none |
| AC ledger reconcile and `measure_ac_evidence_ledger.py` | Shipwright-specific | FR/AC ids, `covers` marks, the ledger |
| `ac_decision.py` record (`unchanged`, `--ac-mode auto`) | Shipwright-specific | the FR catalog |
| `fr_cluster_report.py`, the AC-Move-Map | Shipwright-specific | atomic FR splits |
| `release_seams.py` (env-var seams read in one place, argv prefix for `gh`, fixture model, publish guard) | generic in method (any CLI wrapper that must run offline), Shipwright-specific in the variable names | the list of external binaries and model calls on the path (the subprocess map) |
| one-place scan test (no file but the seam module names a seam variable; no literal `["gh"` argv in the wrapped scripts) | generic | the seam names |
| golden trace (`golden_trace.py`: collect, normalize, mask, driver interface, freeze check), scratch builder (`release_scratch.py`), `gh` stub (`gh_stub.py`) | generic in method (any skill that ends in git and one outward CLI), stdlib only; the step list in `tests/golden/conftest.py` and the `SHIPWRIGHT_TEST_*` names are Shipwright-specific | the list of steps, the outward binary and its contract, the normalization labels |
| fork tool, L3 harness | not used yet (P2-op onward) | |

## 6. Doable by a stranger?

| Step | Verdict |
|---|---|
| inventory (sections, classes, targets) | yes, with the tools of item 5 |
| truth table and subprocess map | yes: read the prose and the code, cite lines |
| pin list by breaking the prose | yes, with the break-the-prose measure; the machine time is the cost (about 30 minutes for the biggest root here) |
| ledger reconcile against the path the skill takes | no without Shipwright knowledge: it needs the FR/AC ledger and the `covers` convention |
| promise list in plain language | yes with a repo that has acceptance criteria; for a repo without them this step needs a lighter mode (writing the promises first) |
| operator questions in plain language | yes |

**Convention file** (`docs/building-skills-plugins-agents.md`): the migration showed one gap so far. It has no class for an *outward command* (a literal command that is neither judgement nor safe to move into code, e.g. `gh pr merge`); P0 recorded them as `mechanic` with target `keep` and a note.


## 7. Ideas from outside, to test against the pilot (added 2026-11-16, not decisions)

Source: a read of NVIDIA NeMo Guardrails and its Colang 2.0 runtime (github.com/NVIDIA-NeMo/Guardrails, develop branch; flow parser, `runtime/flows.py`, `runtime/statemachine.py`, `tests/utils.py`, `nemoguardrails/testing/chat_harness.py`). Colang guards a chat between a user and a bot at run time; it is not our guardrail problem and we do not adopt it. Three of its design ideas fit the CLI steps of P3 and P4. The pilot should say at the end (section 2 or 3 of this report) whether each one held.

1. **A process as data.** Colang parses a flow into plain data (dataclasses with a `_type`), lowers it to a flat list of steps with labels and jumps, and can dump that list as JSON before anything runs. For us: the step order and allowed transitions of a skill as a JSON step list. Question for the pilot: does `release.py` end up with a step list that a validator can check without running it? Colang's weakness to avoid: a misspelled flow name fails silently, and there is no separate validator. We validate in Python before anything runs.
2. **Paired lifecycle events.** Every action has a command (`Start`, `Change`, `Stop`) and results (`Started`, `Updated`, `Finished`, `Failed`), a uid, and an explicit status (initialized, starting, started, stopping, finished). For us: each CLI step reports started and finished (or failed) with a step id, so a checker can name the step a run skipped. Question for the pilot: can the golden traces of P2a be written as these pairs, and does that make the "skipped step" failure readable? The CLI as a pure function (state plus event in, new state plus events out) is what makes the trace replayable.
3. **The model only at declared seams.** Event matching, lifecycle and priorities are plain Python; the LLM is used only through opt-in steps, and its output must come back as a typed event the engine validates. An event nobody handles is emitted explicitly. For us: this is the line between the CLI and the questions in the thin `SKILL.md` (P5). Question for the pilot: does every answer the model gives come back through a typed value the CLI checks?

Also noted from their tests, for P2a and P2b: they compare event lists as an ordered subset with exact length, drop volatile keys (uids, timestamps), and feed scripted model answers in order. Our golden files are recorded, theirs are written by hand, so ours is a step further. Colang 2.0 is documented as beta, and open issues name rails that fail open on missing globals. That is another reason not to depend on it.

Older workflow tools (state machines, BPMN, job schedulers) have the same shape, so none of this is new. The pilot is the cheap test of whether it pays for skills.
