# Dormant per-run event drops layout, bare-origin harness and standing replay gate

Run: `iterate-2026-11-05-s0-harness-dormant-writer` (campaign `events-drop-files`, unit S0; issue 978).
Binding sources: `.shipwright/planning/campaigns/2026-11-04-events-drop-files-BRIEF.md` and `-DESIGN.md` (section 10 overrides).

## What was decided
- The drops layout (`shipwright_events.d/<key>--<wt8>--<nonce8>.jsonl`) lands as a DORMANT path in a new module `lib/events_layout.py`, wired into `record_event` (path chosen under the existing lock) and `lib.config.read_events_result` (assembled read: legacy in file order, then archive and drops by parsed instant and id). Default stays legacy; the env var `SHIPWRIGHT_EVENTS_LAYOUT` is honoured only with `SHIPWRIGHT_EVENTS_LAYOUT_TEST=1`; the `events_layout` config key is read at runtime. Legacy bytes, the lock file and the legacy resolver are unchanged.
- Rotate-on-commit probe uses `ls-tree` plus the index (a staged drop is closed: DESIGN 10.2), never `git status`; a failed probe starts a fresh file.
- The replay gate (`tools/events_replay_gate.py`, CI step, ratcheted `events_replay_known_failing.json` split by owning unit S2/S3 readers vs S4 writers) replays every event-related test file of every root, one pytest process per root, under the test-only override. It fails closed (crashes, timeouts, unparsable runs, collection errors), a known entry that now passes fails with `--strict-stale`, the set may only shrink against the merge-base copy, and the stated time budget (`budget_seconds`, Windows-measured; Linux CI confirmation is a follow-up) cannot be disabled.

## Architecture Review
Both external reviewers ran over a brief that listed the options without reasons (A drops layout, B rebase on main moves, C stop tracking the log, D do nothing).
- Verdicts: `glm: reject`, `openai: revise`; internal `architecture-internal-reviewer`: approve.
- **GLM reject (Option C, stop tracking the log) - reconciled, plan kept.** The alternative was already decided against by the operator: DESIGN line 16 (2026-05-29 decision: untracked main-tree events were wiped once; F11 requires the event in the committed blob; WebUI rebuilds campaigns from `origin/main`). The brief withholds rejection reasons on purpose, so this is a known decision, not new evidence. Reconciled by the orchestrator on that basis.
- **OpenAI revise (make the replay gate migration-only, retire at cutover; name a campaign owner) - declined.** BRIEF section 3 S0 mandates the standing, ratcheted, shrink-only gate; the retirement point is the campaign's own S9c. A named owner is not needed (the operator owns the campaign).

## External-Plan-Review-Findings
| Finding | Disposition |
|---|---|
| Precedence of config key vs env var vs test flag must be an explicit test (both) | accepted-and-fixed: `test_layout_precedence_matrix` |
| Legacy path must be a strict pass-through; test legacy output equals pre-change | accepted-and-fixed: `test_legacy_mode_bytes_are_exactly_todays`, `test_legacy_target_is_the_events_log_resolver` |
| Specify rotation and concurrent-append recovery; test exactly-once | accepted-and-fixed: docstring sequence + `test_drops_writes_survive_rotation_and_concurrency_exactly_once` |
| Harness must assert merged contents, not only conflict status | accepted-and-fixed: merged tree bytes asserted per pair |
| Resolved known entries must fail the gate | accepted-and-fixed: CI runs `--strict-stale` |
| S2/S3/S4 entries are projections to re-validate | accepted: unit tags are hand-reviewed, editable |

## External-Code-Review-Findings
| Finding | Disposition |
|---|---|
| glm high: legacy path may differ from `resolve_events_path` | rejected-with-reason for behaviour (identity join, pinned by test); accepted for the SSoT shape: events_layout now goes through `resolve_events_path` |
| glm medium: TimeoutExpired uncaught | accepted-and-fixed (`<pytest-timeout>` sentinel) |
| glm medium: crash misattributed as drops-only | rejected-with-reason: fail closed is intended; collection errors are never excused |
| openai high: exit 1 with unparsed ids / ids with spaces pass silently | accepted-and-fixed |
| openai high: collection errors excused as baseline | accepted-and-fixed |
| openai high: ratchet fails open without a base | accepted-and-fixed (fails in CI, notes locally; absent at base = introduction) |
| glm low: budget measured on Windows, CI differs | accepted: jobs aligned (3), follow-up to confirm on Linux |

## Internal review notes
- plan reviewer (opus): revise -> mini-plan items fixed (tri-state merge-tree + union attribute in harness, fail-safe rotation probe, plugin addopts preserved, subset-of-base ratchet, gate unit tests, template guard test); deferred: gate in its own CI job, legacy `ensure_current` baseline in harness, junit-based parsing, non-monotone fixture pair.
- code-reviewer: round 1 request changes (SSoT bypass; stale-check/baseline; budget zeroing; fail-open exit codes) -> fixed, round 2 approve.
- doubt-reviewer: staged drop reuse (fixed), budget ratchet needing a reason (fixed), canary preflight (added), config key unsupported before S9a (documented); assembled in-file ordering deferred to S2.

## Confidence Calibration
Boundaries: (1) `shipwright_sync_config.json` (human-edited JSON): probes for BOM (found: read with `utf-8` silently fell back to legacy -> fixed with `utf-8-sig`), CRLF, non-ASCII neighbours, empty value; re-probe clean. (2) producer -> drop file -> consumer: bare-origin harness (real `record_event`, `merge-tree` without union, merged bytes equal the branch files), concurrency and rotation exactly-once test, split-fixture read equals the unsplit read. Two consecutive no-finding probes after the BOM fix: asymptote reached. Not probed: Linux runtime of the gate (budget confirmation owed), real `ensure_current` on drops (explicitly S3).

## Consequences
Nothing changes for consumers (default legacy). The repo gains a required CI step with a ratcheted known set (about 100 entries) owned by the later units; they must shrink it. Setting `events_layout: drops` in a real repo is unsupported until S9a.
