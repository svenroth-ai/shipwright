# Mini-Plan: f0-race-triage

- **Run ID:** iterate-2026-07-27-f0-race-triage
- **Spec:** `.shipwright/planning/iterate/2026-07-27-f0-race-triage.md`

## Problem

`shared/scripts/tools/run_test_suite.py` (the F0 parallel test-gate runner) re-runs a
unit that failed under concurrency **alone**, and takes that verdict as authoritative.
Correct — the re-run exists so a race cannot false-STOP the gate. The consequence is
that red-in-parallel + green-alone leaves the gate GREEN and produces only a printed
warning ending in *"triage it"* (`_retry_note`, line ~262).

No code creates that entry. Grep confirms `run_test_suite.py` imports no triage API
and writes no file other than the per-unit JUnit reports in a `TemporaryDirectory`.
So the warning lives exactly as long as the console does. The observation the runner
paid for — it ran the unit twice, in two shapes, to produce it — is discarded.

This is the same shape as the other non-blocking checks closed recently: **what warns
and does not stop must leave a tracked follow-up that outlives the run.** The
complement is already enforced in the opposite direction: `test_f0_5_no_triage_emit.py`
pins that F0.5, which *does* STOP, must file **nothing** (the run's own blocked work
belongs on the board, not in the backlog — `shared/constitution.md`). F0's race path
is the other half of that rule, and it is currently unimplemented.

## Approach (chosen): a producer module, called from the CLI path

1. **`shared/scripts/tools/suite_race_triage.py`** (new, < 300 LOC) — the single home
   for everything said *and* recorded about a raced unit:
   - `RETRY_SERIAL_KIND` — drift-pinned copy of `run_test_suite.RETRY_SERIAL`.
   - `race_note(res, xdist_ids)` — the operator sentence (moved verbatim out of
     `run_test_suite._retry_note`, so the console text and the entry text cannot drift).
   - `entry_title(...)` / `entry_detail(...)` / `launch_payload(...)` — the body.
     Measured facts only; **no captured pytest output** (the tracked log is public).
   - `emit_race_followups(project_root, races, xdist_ids, *, run_id, commit)` →
     `RaceFollowupReport(recorded: dict[unit_id, trg_id], failed: dict[unit_id, str])`.
     Appends via `triage.append_triage_item_idempotent(..., to_outbox=False)`, then
     **reads the store back** with `read_all_items` and resolves the open id per
     dedup key. A unit with no resolvable open entry lands in `failed`.
   - `render(report, races, xdist_ids)` → the loud console block.
2. **`run_test_suite.py`** — minimal, non-invasive edits:
   - `unrecorded_races(result)` — the one-line predicate (`res.race and
     res.retry_kind == RETRY_SERIAL`), living next to the constant that defines it.
   - `_report(result, report=None)` — delegates the retry-warning block to `render`.
   - `main()` — new optional `--run-id`; best-effort `git rev-parse HEAD`; calls
     `emit_race_followups`; returns **3** when `report.failed` is non-empty.
   - `run_suite()` is untouched — no side effects in the engine, so every existing
     test and caller is unaffected.
3. **Tests** — `shared/scripts/tools/tests/test_suite_race_triage.py`, all against
   `tmp_path` (never a tracked fixture dir: a runner pointed at a tracked root leaks
   `.shipwright/triage.jsonl` into version control — conventions, 2026-07-15).
4. **Docs** — `references/F0.md`, `docs/hooks-and-pipeline.md` (F0 runner section +
   both triage artifact-write matrix rows), FR-01.14 acceptance criterion.

### Entry shape

| field | value |
|---|---|
| `source` | `f0-suite` |
| `severity` | `high` (→ P1) |
| `kind` | `bug` |
| `dedupKey` | `f0-race:<unit-id>` (`match_commit=False`, `window_seconds=None`) |
| `title` | `[f0] <unit-id> failed in parallel and passed alone - race or flaky test` |
| `detail` | unit id · both exit codes · xdist-allowlisted yes/no · the explicit statement that the cause is undetermined · what to do. No test output. |
| `launchPayload` | `/shipwright-iterate --type bug` + the two reproduce commands |
| `runId` / `commit` | from `--run-id` / best-effort HEAD |
| auto-dismiss | **never** |

`severity=high` is deliberate: the gate declined to stop, so this entry is the *only*
record that anything was observed. A P2 in a long backlog is precisely "skimmed past",
which is the failure mode the operator named.

## Alternative considered (and rejected)

**Record it as an event, or in `shipwright_test_results.json.degraded[]`.**
Cheaper — `degraded[]` is already written at F5 and needs no new module, and the event
log already carries per-run facts.

Rejected because neither survives the thing it must survive. `degraded[]` is per-run
state that the *next* run overwrites, so the observation would die one run later
instead of one session later — a strictly smaller version of the same bug. The event
log is the "what happened" record, not the "what is still open" record; nothing
prompts an operator to work through it, there is no dismiss/defer decision on it, and
it is not the surface the Command Center renders. `read_all_items` over
`.shipwright/triage.jsonl` is the answer to "what is still open here?" (FR-01.14), it
is rendered into `triage_inbox.md` by the Stop aggregator, and F6 already carries it
into the PR. The extra module is the price of the entry actually being found.

A second alternative — instruct the agent in `F0.md` to file it — is today's failure
mode with more words. `_retry_note` already says "triage it".

## External Review — findings & dispositions (GPT + Gemini via OpenRouter, Branch A)

Both reviewers returned on both runs (`reviews_succeeded: 2`, `degraded: false`); the
raw payload is `.shipwright/runs/<run_id>/external_plan_review.json`. Findings are the
union of the two runs. Three load-bearing premises were **probed against the real
triage API** rather than argued (`P1`/`P2`/`P3` below). None dropped.

| # | Reviewer / sev | Finding | Disposition |
|---|---|---|---|
| R1 | Gemini **high→med** (both runs) | The read-back is over-production and couples F0 to unrelated damage: a malformed record elsewhere in the store would exit 3 for a reason that has nothing to do with this suite. | **ACCEPTED in substance, mechanism kept.** The append — not the read-back — is now the authority on whether the record exists (it fsyncs inside the triage lock). The read-back survives only to resolve the id of an already-**open** entry for the console line, and a read-back failure alone never reddens the gate (AC8). Probe **P3**: `read_all_items` is already tolerant — a `{not json` line yields a warning and the other records, not an exception — so the parse-error path Gemini describes is not reachable; the OSError path is what the redesign closes. |
| R2 | OpenAI **high** (both runs) | Does idempotent-append reuse a **closed** entry? If so, a race re-observed after the operator dismissed it would be silently dropped — violating AC3/AC8. | **VERIFIED CORRECT, no change; now pinned.** Probe **P1**: an OPEN duplicate suppresses (returns `None`); after `mark_status(dismissed)` the next append creates a **new** id. That is exactly the wanted semantics. Added to the ledger as a test rather than left as an assumption. |
| R3 | OpenAI **high** (both runs) | `res.race and res.retry_kind == RETRY_SERIAL` may not actually mean "genuine pytest test failure, then authoritative alone pass" — collection errors, usage errors, rc 5, timeouts could leak in. | **VERIFIED CORRECT, no change; now pinned.** In `run_suite`, `race` is set only inside the retry block and `retry_kind = RETRY_INFRA if outcome == INFRA else RETRY_SERIAL`; every non-test-failure class (rc 2/3/4/5, timeout 124, spawn 126, rc 1 without a JUnit report) classifies INFRA. So `RETRY_SERIAL` ⟺ rc 1 + JUnit report in parallel, PASS alone. Negative tests added for INFRA, rc 5, timeout, and serial-retry-still-red. |
| R4 | OpenAI **high** | Exit-code precedence is undefined when the suite is **also** red and a race could not be recorded. (Run 1 suggested preserving the suite code; run 2 suggested 3 overriding.) | **ACCEPTED, decided explicitly.** Exit 3 only when the suite would otherwise be GREEN; a red suite keeps 1. Exit 3 exists so a *green* run cannot pass with nothing written down — a red run already STOPs, and relabelling it 3 would misdescribe its dominant fact. Both are non-zero, so F0 STOPs either way. Documented in AC8 and tested. |
| R5 | OpenAI high / med | Verify the triage API's routing + concurrency contract instead of assuming it: does `to_outbox=False` really target `<project_root>/.shipwright/triage.jsonl`, and are concurrent writers serialised? | **VERIFIED, no change.** Probe **P2**: the tracked file appears under the passed root and no outbox is created; `_triage_path` derives from the argument, never cwd or env. Concurrency: `append_triage_item_idempotent` performs the dedup scan **and** the append inside one `FileLock` (ADR-046). No independent JSONL write path is introduced. An end-to-end `main()` test runs with cwd elsewhere and asserts only `tmp_path`'s store is touched. |
| R6 | OpenAI med / Gemini low | `RETRY_SERIAL_KIND` in the producer is a second owner of runner policy and can silently diverge. | **ACCEPTED — copy dropped.** Classification stays solely in `run_test_suite.unrecorded_races()`; the producer receives already-confirmed races and never sees the constant. The drift test it would have needed disappears with it. |
| R7 | OpenAI med | Ordering: the retry warning must be rendered **after** persistence, once per unit, carrying either `tracked as trg-…` or an explicit recording failure. | **ACCEPTED.** `main()` = run suite → identify races → persist → `_report(result, report)` → choose exit code. |
| R8 | Gemini med / OpenAI med | Shell-safety: interpolating identifiers into copy-paste commands. | **ACCEPTED** (AC14). `shlex.quote`/`shlex.join`, control characters stripped, length-capped. Repo-derived unit ids are not actually attacker-controlled, but FR-01.14 already requires this of any entry text the project does not author, and it is nearly free. |
| R9 | OpenAI med | Enforce the title/detail caps **inside** the producer and build the detail from an allowlist of scalars — otherwise a future edit can leak captured pytest output into the tracked log. | **ACCEPTED** (AC13 + AC5). Test: a result whose `output` carries a distinctive marker must leave no trace in `triage.jsonl`. |
| R10 | OpenAI med | The reproduce commands are underspecified — a generic command that differs from F0's real invocation is an attractive but unreliable CTA. | **ACCEPTED** (AC6). The alone-run command is now the actual argv from `build_command(unit, None)`, captured on the result during the retry, `shlex.join`-quoted. Nothing is rebuilt from guesswork. |
| R11 | Gemini low / OpenAI low | `git rev-parse` must not crash on a missing binary / non-repo root; run it with `cwd=project_root`, no shell, bounded timeout. | **ACCEPTED** (AC12), including the non-git-root test. |
| R12 | Gemini low | The new module must not re-parse `shipwright_test_config.json` to learn the xdist allowlist. | **ACCEPTED** — `xdist_ids` is passed down from `SuiteResult`; the producer reads no config. |
| R13 | Gemini low | Console I/O should stay with the orchestrator; only content should move. | **ACCEPTED** — `render()` returns `list[str]`; `run_test_suite._report` prints. |
| R14 | Gemini low | Concurrent appends to a tracked JSONL across branches will cause merge conflicts. | **VERIFIED ALREADY HANDLED, no change.** `.shipwright/triage.jsonl` is `merge=union` via `.gitattributes` plus an unconditional `resolve_churn_conflicts._reconcile_triage` (exact-line dedup + header/JSON validation) — `docs/hooks-and-pipeline.md` churn table. |
| R15 | OpenAI low | The proposed split exports more than it needs. | **ACCEPTED** — with R6 applied the module is narrowly: build facts → render → persist → resolve. |

## Risks

| Risk | Mitigation |
|---|---|
| Fail-closed (exit 3) turns a green gate red on a triage-write problem | Scoped strictly to *a race was observed AND no open entry is resolvable*. Zero races → the producer never runs and the exit code is untouched. Read-back means a successful dedup-suppressed append also counts as recorded. |
| Entry noise from ordinary infra flakiness | `RETRY_INFRA` is explicitly excluded (AC9) and pinned by a test. |
| Dedup lets a *second, different* race in the same unit go unnoticed | Accepted: one open entry per unit is the point (a unit is the actionable object). The entry is never auto-closed, so it stays open until the unit is actually fixed. |
| Public repo leak via the tracked log | AC5: no captured output, no file:line, aggregated facts only. |
| `run_test_suite.py` growing past the 300-line limit | `_retry_note` moves out; measured before commit. |
