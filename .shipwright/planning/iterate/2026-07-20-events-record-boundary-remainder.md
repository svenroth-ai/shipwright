# Iterate: Close the event-log record-boundary reader remainder (part 2)

- **Run ID:** iterate-2026-07-20-events-record-boundary-remainder
- **Intent:** BUG (Path C) — defect repair
- **Complexity:** medium
- **Risk flags:** `touches_io_boundary`, `cross_component` (diff-driven — `churn_merge.py`)
- **Spec Impact:** NONE (defect repair; no requirement changes)
- **Predecessor:** iterate-2026-07-19-events-record-boundary-readers (PR #… — 11 sites), which fixed the compliance/verifier/traceability read path and filed the remainder as `trg-360e494f`.

## Problem

The predecessor converted **11** event-log read sites to the record-boundary SSoT
`lib/jsonl_records` (partial-recovery reader that survives two records sharing one
physical line — the artefact a `merge=union` merge propagates into `main`). It
**deliberately did not close the defect class**: it filed the remaining sites as
`trg-360e494f` with exact locations, rather than leave them implied-fixed.

This iterate closes that remainder for every reader that treats
`shipwright_events.jsonl` (the tracked, union-merged log) as **authority**, and
fixes the one validator that reports a false failure on a concatenated line.

The defect class is unchanged: a bare `json.loads(line)` under an
`except json.JSONDecodeError` (or `except (ValueError, …)`) that skips the **whole
physical line** discards *every* record on it. On an append-only audit trail a
dropped record makes a step that happened read as one that never did. The most
operator-facing form is **inverted**: when the record a check is looking for
(`adopted`, `work_completed`, the newest `work_completed`) is the SECOND record on
a concatenated line, the reader reports its absence — so a correctly-recorded run
reads as broken.

## Root cause

Same as the predecessor: the record-boundary contract was centralised in
`lib/jsonl_records` (#405 / the 11-site iterate), but each reader open-codes
"one line == one record", so the fix reaches only the call sites rewritten to
delegate.

## Reachability (unchanged from the predecessor — cited, not re-derived)

The predecessor pinned in BOTH directions that git's `merge=union` does **not
create** a concatenated line (it reconciles the "\ No newline at end of file"
diff property) but **propagates** an existing one verbatim into `main`
(`integration-tests/test_events_record_boundary_merge_integration.py`, AC7). A
single unguarded write anywhere in the fleet — an interrupted write, an external
writer, an operator edit, or any record already on disk from before the writer
fix — therefore reaches every downstream reader of the merged log. The reader
half is load-bearing for that reason.

## Sites — the four authority readers converted here

All four read the tracked, union-merged `shipwright_events.jsonl` per physical
line and share the inverted-failure class. Line numbers are as filed in
`trg-360e494f`; the parsing loop had drifted a few lines in one case (noted).

| # | Site | Function | Current failure |
|---|---|---|---|
| 1 | `shared/scripts/lib/phase_quality/_resolution.py` | `resolve_run_id` | the `run_started` scan drops both records on a concatenated line → run-id resolution falls through to the next fallback (loop-id / session-id), silently mis-attributing audit rows |
| 2 | `shared/scripts/tools/verifiers/adopt_compliance.py` | `check_a7_adopted_event` | the single `adopted` event second on a concatenated line reads as **absent** → A7 FAILs a correctly-adopted repo (inverted) |
| 3 | `plugins/shipwright-adopt/scripts/checks/validate_adoption.py` | `_validate_events` (loop at ~L102, filed as :90) | identical inverted `adopted`-count failure on the adopt-side soft check |
| 4 | `plugins/shipwright-grade/scripts/lib/routing.py` | `_newest_work_commit` | the newest `work_completed` second on a concatenated line is missed → grade routing either false-flags **stale** (an older commit wins) or declines to judge; authoritative-vs-heuristic verdict corrupted |

Sites 3 and 4 sit in plugins that **ship their own `scripts/lib`**, so a bare
`from lib.jsonl_records import …` resolves to the *plugin-local* `lib` (the ADR-045
barrier). They load the shared leaf **by file location under a module-private
sentinel**, mirroring `validate_adoption`'s existing `_discovery()` helper —
registered in `sys.modules` **before** `exec_module` because `jsonl_records`
defines `@dataclass` types and stdlib `dataclasses` resolves `cls.__module__`
through `sys.modules` at class-creation time. Sites 1 and 2 are Tier A
(`shared/scripts` already on `sys.path`, `lib.` prefix) and import directly, as
`common.py` (site 3 of the predecessor) does.

## The validator fixed here

`churn_merge.validate_events_text` (`churn_merge.py:~232`) parses one physical
line at a time. If a run's `work_completed` is the SECOND record on a concatenated
line, `require_run_id` never matches → a **false** `check_events_has_commit`
failure during `integrate_main`, AND the concatenated line is reported as
"not valid JSON". It fails **closed** (the line is appended before the parse, so
no data is lost), which is why the predecessor filed rather than fixed it. Fixed
here via `split_records` per physical line: a fully-recoverable concatenated line
of two valid records is no longer flagged, and a genuinely unrecoverable fragment
(non-empty `remainder`) still is — check (a) is preserved.

## Deliberate scope decisions (the "what is still relevant" assessment)

### Declined — `shipwright-run` `single_session/observability.py::load_events`

Filed in `trg-360e494f` as the **lowest priority** of the five, because it reads a
**different** file: `.shipwright/run_loop_events.jsonl`, which self-documents as
*"Telemetry, not authority."* Converting it delivers **zero recovery benefit**,
so it is declined (not deferred — there is nothing to defer):

1. The file is **gitignored** (`git check-ignore` confirms) and has **no
   `.gitattributes merge=union` entry**. The AC7 propagation mechanism — a
   concatenated line reaching `main` via union merge — cannot apply to it.
2. It is **single-writer** (the one `/shipwright-run` master, serially) and every
   emit is `fh.write(json.dumps(event) + "\n")` + `flush` + `fsync`. Two
   **complete** records sharing one physical line (the `{good1}{good2}` case the
   SSoT recovers) is therefore **unreachable** — every complete write ends in `\n`.
3. The only unterminated tail it can produce is a **torn partial** from a crash
   mid-`write` (garbage, not a complete record). `split_records` cannot recover a
   record that FOLLOWS the first undecodable byte (partial recovery stops at the
   bad byte), so the SSoT would not recover it either — and the module already
   documents dropping "at most the final in-flight event" as correct.

Converting it would add a cross-plugin by-path loader to a module that currently
imports nothing shared, for no behaviour change — churn against this iterate's
governing invariant. This mirrors the predecessor's principled exclusion of
`validate_event_log.py`. Recorded so the decision is not silently re-opened.

### Kept excluded — `validate_event_log.py:47`

Per-line strictness is its contract (the predecessor's exclusion stands);
`verifiers/common.py` explicitly points callers needing strict validation at it.
Converting it would erase the distinction it exists to draw.

### Out of scope (carried, not introduced here)

- The adopt `_ends_without_newline` writer-side duplicate has no parity test
  (predecessor's Out-of-scope item; unchanged).
- `finalized_run_ids` corrupt-policy `None`-on-any-fragment question
  (predecessor's open policy follow-up; a drift-gate policy call, not a defect).
- Audit groups have no native corruption-reporting channel (predecessor item).

## Governing invariant (inherited from the predecessor)

**Behaviour-preserving except for record recovery.** Every site keeps its existing
corruption-*reporting* contract — silent stays silent — and only what it
*recovers* changes. The one intended exception, enumerated as its own AC:

* **AC-CM2** — `validate_events_text` no longer reports a fully-recoverable
  concatenated line of two valid records as "not valid JSON". That is the point of
  the fix (a recoverable union artefact is not corruption), and it is an observable
  change, so it is pinned rather than assumed. A genuinely unrecoverable fragment
  is still reported. **Enumerated sub-exception (external review, OpenAI #3):** a
  lone non-object line (a bare scalar such as `5`) — which the pre-fix per-line
  `json.loads` accepted silently because a scalar *is* valid JSON — is now reported
  as corrupt, because the object-only SSoT treats it as a fragment. This is a
  reporting *widening* consistent with the predecessor's AC12 (`change_history`
  warns for a bare scalar) and unreachable on a real event log (every writer emits
  `json.dumps(dict)`), so it cannot manufacture a false `integrate_main` failure.
  Pinned by `test_validate_events_text_flags_a_bare_scalar_line_as_corrupt`.
* **Edge-behaviour note (external review / internal review LOW-1):** the three
  file-reading converters move from `errors="ignore"` to the SSoT's
  `errors="surrogateescape"` (invalid UTF-8 no longer silently dropped byte-wise;
  a structurally-corrupt line degrades to a recoverable fragment instead). This is
  inherited verbatim from the 11-site predecessor's SSoT and moves strictly in the
  recovery direction; noted rather than assumed. `routing` is unaffected — it
  parses text already read by `_read_tail` (`errors="replace"`), so its I/O is
  byte-for-byte unchanged.

## Acceptance criteria

- **AC1** — `_resolution.resolve_run_id` recovers `run_started` records from a
  concatenated line and returns the run-id of the LATEST one (wire order
  preserved). Absent/empty log still falls through to the documented fallbacks.
- **AC2** — `adopt_compliance.check_a7_adopted_event` counts the `adopted` event
  when it is the SECOND record on a concatenated line → PASS for a correctly
  adopted repo (the inverted failure is fixed). A genuinely-absent event still
  FAILs; two `adopted` events still FAIL as "found 2".
- **AC3** — `validate_adoption._validate_events` recovers the `adopted` count from
  a concatenated line identically (adopt-side parity with AC2).
- **AC4** — `routing._newest_work_commit` returns the newest `work_completed`
  when it is the SECOND record on a concatenated line (so `_staleness_reason`
  keys on the true newest event). A leading partial line from the bounded TAIL
  read is still skipped (unchanged); a commit-less newest event still declines to
  judge stale.
- **AC5** — Recovery stays **partial, never all-or-nothing** at every converted
  site: a valid record followed by an unrecoverable fragment yields the valid
  record. (All-or-nothing recovery would reproduce the bug.)
- **AC6** — Every converted reader returns **only JSON objects**; a bare scalar
  line is treated as a fragment and skipped, not surfaced as a record (the SSoT's
  `isinstance(obj, dict)` guard), and no converted site crashes on one.
- **AC-CM1** — `churn_merge.validate_events_text(require_run_id=R)` returns no
  error when `R`'s `work_completed` is the SECOND record on a concatenated line
  (the false `check_events_has_commit` failure during `integrate_main` is fixed).
- **AC-CM2** — the reporting-widening pinned above (fully-recoverable concatenated
  line no longer flagged "not valid JSON"); an unrecoverable fragment still is.
- **AC7 (INTEGRATION, `cross_component`)** — a real `merge=union` merge of two
  divergent branches propagates a concatenated line into the merged tree, and
  afterwards BOTH `churn_merge.validate_events_text` (validator) AND a converted
  authority reader observe the run — the validator + reader compose over the same
  merged log.

## Mini-plan

**Tier A (import directly, `lib.` prefix):**
1. `_resolution.py` — `from lib.jsonl_records import read_jsonl_records`; iterate
   `read_jsonl_records(events_path).records`, keep the existing
   `try/except OSError` wrapper and the `run_started`/latest-wins logic.
2. `adopt_compliance.py` — `from lib.jsonl_records import read_jsonl_records` (via
   the existing `_SHARED_SCRIPTS` bootstrap, as `common.py` does); iterate
   `.records` counting `adopted`. Let `OSError` propagate as the pre-fix
   `read_text` did (behaviour-preserving; no new swallow).

**Tier B (ADR-045 barrier — by-path sentinel load):**
3. `validate_adoption.py` — add `_jsonl_records()` mirroring `_discovery()`
   (sentinel `_shipwright_jsonl_records`, registered in `sys.modules` before
   `exec_module`); `_validate_events` iterates `.records`.
4. `routing.py` — add the same by-path helper; `_newest_work_commit` flattens each
   physical line via `split_records` into an ordered record list, then iterates in
   reverse for the newest `work_completed` (preserving the bounded-tail +
   leading-partial-skip behaviour).

**Validator:**
5. `churn_merge.py` — `validate_events_text` splits each physical line via
   `split_records`; iterate recovered records for the `require_run_id` match;
   report the "not valid JSON" error only when `remainder` is non-empty.
   `churn_merge` is Tier A (`shared/scripts/lib`), so `from .jsonl_records import
   split_records` (same package).

**Integration:** extend the predecessor's merge integration test (or a sibling)
with a case that asserts the validator + a converted reader both see the run after
a real union merge (AC7 / `cross_component`).

### Alternative considered — reuse `common.read_events_jsonl` in `adopt_compliance`

`adopt_compliance` and `common` are the same `verifiers` package and `common`
already exposes a converted `read_events_jsonl(project_root)`. Rejected as the
primary mechanism to keep the diff a straight one-line delegation matching the
predecessor's pattern and avoid a new intra-package dependency; the direct SSoT
import is the "same one-line remedy" the triage item describes.

## External plan review (GPT-5.4 + Gemini 3.1 Pro via OpenRouter, 2/2 succeeded, not degraded)

**Accepted — changed the code:**

1. **(MED, OpenAI #2) Sentinel collision.** The two by-path loaders shared one
   `sys.modules` key (`_shipwright_jsonl_records`); in a multi-checkout process the
   first-loaded copy would win for both. Renamed to consumer-specific sentinels
   (`_shipwright_adopt_jsonl_records`, `_shipwright_grade_jsonl_records`).

**Verified and dismissed (the concern did not apply to the shipped code):**

1. **(HIGH, Gemini #3 / OpenAI #1) routing double-reversal / bounded-tail
   fragment.** The implementation reads physical lines FORWARD, flattens
   `split_records` output into wire order, then reverses the FULL list — so the
   true newest wins even when it is second on a concatenated line. Pinned by
   `test_newest_work_commit_recovers_the_newest_from_a_concatenated_line`
   (`{mid}{new}` → `new`) and a leading-partial-fragment guard.
2. **(MED, Gemini #4) remainder whitespace → false error.** `split_records`
   consumes trailing JSON whitespace and the caller passes `stripped` input, so a
   clean line yields `remainder == ""`. Pinned by
   `test_validate_events_text_does_not_flag_a_recoverable_concatenated_line`.
3. **(MED, OpenAI #4) relative-import fragility.** The SSoT is imported absolutely
   (`from lib.jsonl_records import split_records`), matching `churn_merge`'s own
   `from lib.triage_validate import` idiom; the full suite exercises every
   `integrate_main` / resolver entry point.
4. **(MED, OpenAI #5) SSoT edge behaviour.** Verified equivalent for missing file,
   OSError/directory, and blank lines; the one delta (`surrogateescape`) is noted
   under AC-CM2's edge-behaviour note.

**Declined, with reasoning:**

1. **(MED, Gemini #1) Reuse `common.read_events_jsonl` in `adopt_compliance`.**
   Declined: the sibling `common.py` itself imports the SSoT directly rather than
   delegating, so a straight `from lib.jsonl_records import read_jsonl_records` is
   the consistent, minimal remedy and avoids a new intra-package dependency. See
   "Alternative considered" above.
2. **(LOW, Gemini #2) Abstract the duplicated `_jsonl_records()` loader.** Declined:
   the two loaders live in DIFFERENT plugins separated by the ADR-045 barrier, so a
   shared abstraction would itself need to cross that barrier (the very problem the
   by-path load solves). Per-plugin duplication is the repo's sanctioned pattern —
   `validate_adoption`'s pre-existing `_discovery()` does exactly this. OpenAI #6
   independently recommended mirroring the established helper rather than
   introducing a cross-plugin abstraction.

## Confidence Calibration

- **Boundaries touched:** the `shipwright_events.jsonl` append-only log (read
  side, 4 authority readers across both import tiers); the `churn_merge` merge
  validator; the ADR-045 cross-plugin import boundary (sites 3-4). NOT touched:
  the gitignored `run_loop_events.jsonl` telemetry log (declined, with rationale).
- **Empirical probes run:**
  - All four authority readers reproduced the bug pre-fix and recover post-fix:
    the shared record-boundary suite had **6 red / 5 green** against the unfixed
    code (`resolve_run_id` → session-fallback, `check_a7` → FAIL + an
    `AttributeError` crash on a scalar line, `validate_events_text` → false
    "not valid JSON" + false absent-run) and **12/12 green** after; grade
    `_newest_work_commit` returned the OLDER commit (`aaaaaaaaaaaa`) pre-fix and
    the newest (`bbbbbbbbbbbb`) post-fix; adopt `_validate_events` reported
    "no adopted event found" pre-fix and `[]` post-fix.
  - The decline is evidence-based: `git check-ignore .shipwright/run_loop_events.jsonl`
    confirms it is gitignored, and `.gitattributes` has no `merge=union` entry for
    it — so the AC7 propagation mechanism cannot reach it; its writer is
    single-writer always-`\n`-terminated, so two complete records never share a line.
  - Full shared suite: **4713 passed / 11 skipped** with the fix (one unrelated
    cross-file ordering flake, `test_finalize_iterate::test_run_is_idempotent`,
    which passes in isolation and as its own file, 20/20 — recorded in `degraded[]`).
  - Regression on every direct consumer of the changed code green:
    `test_churn_merge` + `test_resolve_churn_conflicts` + `test_integrate_main` +
    `test_verifiers_adopt` + `test_audit_phase_quality` + `test_check_integration_coverage`
    = **120 passed / 2 skipped**.
  - The real `merge=union` composition (AC7) passes end-to-end: validator +
    `check_a7` reader both see the run after git merges a propagated concatenated line.
- **Test Completeness Ledger:** see `iterate_latest.test_completeness` in
  `shipwright_test_results.json`; 0 untested-testable.
- **Confidence-pattern check:**
  - *Asymptote (depth):* the fix is delegation to an already-proven leaf; depth
    risk is in preserving each site's local contract (Tier-B ADR-045 resolution,
    routing's bounded-tail + reverse-newest semantics, churn_merge's check-(a)
    reporting). Each is pinned by its own test.
  - *Coverage (breadth):* the predecessor's enumeration is now **exhaustively
    closed for authority readers** — 4 convert, 1 declined with evidence, 1 kept
    excluded by contract. Breadth is complete by construction (the triage item's
    own five-site list, minus the two the item itself flagged as non-authority /
    strict-by-contract).
  - *Integration composition (`cross_component`):* AC7 drives a real `merge=union`
    merge end-to-end into BOTH the validator and a converted reader — the pieces
    compose, not merely pass in isolation.

## Post-merge steps (NOT part of this PR)

Plugin-side change (`shared/scripts/**`, `plugins/**`) — does not reach the runtime
plugin cache on merge. After the PR is **merged and green**:

```bash
bash scripts/update-marketplace.sh
uv run scripts/check_plugin_cache_sync.py --strict
```

Deferred, not skipped — it tracks `origin/main` and mutates the one global cache a
live WebUI session runs from.
