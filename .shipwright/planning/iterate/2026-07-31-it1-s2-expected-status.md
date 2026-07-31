# Iterate — IT-1 / S2: `expected_status` under the lock

**Run ID:** `iterate-2026-07-31-it1-s2-expected-status`
**Intent:** CHANGE · **Complexity:** medium · **Spec Impact:** MODIFY (FR-01.14)
**Anchor:** `trg-4ebc928e` · closes `trg-93ceb2b0` + audit finding 19
**Brief:** `.shipwright/planning/iterate/iterate-2026-07-30-it1-triage-store-BRIEF.md`
**Board:** `.shipwright/planning/iterate/2026-07-28-triage-consolidation.md` → IT-1

---

## The problem, measured at the source

A person dismisses a triage entry with a reason. Minutes later a background
producer — the drift detector, the compliance rollup, the GitHub importer —
finishes a scan it started *before* that decision, sees the entry as open in the
snapshot it read, and writes its own `dismissed` event with its own machine
reason. The store resolves status by `(ts, file-order)` with `ts` primary
(`triage.read_all_items` Pass 2, comment: *"makes the chronologically-later flip
win regardless of source file"*), so the later automatic write wins. The person's
reason is gone, and the producer reports success.

Two independent defects make that possible, and both are in the write path:

1. **`mark_status` offers no "flip only if still open".** Every automatic
   resolver runs `read_all_items()` **outside** any lock, filters
   `status == "triage"`, then flips each hit under its own separate lock
   acquisition. Between the read and each write the item's status is unowned.
2. **`mark_status` returns `None`.** A write that should not have happened, and
   a write that did, are indistinguishable to the caller. The resolvers all do
   `resolved += 1` unconditionally after the call, so the count is a claim about
   the loop, not about the store.

The operator-facing CLI already has the *shape* of the protection — on
2026-07-28 a `triage_cli` dismiss refused cleanly with *"has status='dismissed';
only `triage` is dismissable"* while the WebUI flipped the same card. But that
check is itself a read-then-write with no lock spanning the two, so it protects
by luck, not by construction. `mark_status` — the one place every surface goes
through — has no such check at all.

### Correction to the brief's research

The brief names four call sites and one of them is not a call site. Measured in
this worktree at `dd2c3019`:

| Brief says | Measured |
|---|---|
| `tools/suite_race_triage.py:103` is a caller | **It never calls `mark_status`.** `:103` is `read_all_items` inside `_open_ids`, a display-only lookup. Nothing to change |
| four callers | **Nine automatic flip sites across six files**, plus two operator-CLI sites. The brief missed `hooks/check_drift.py:361` and all three `shipwright-compliance` producers, which call through the alias `mark_status_fn` and so do not match a `mark_status(` grep |

Full measured set (`grep` for both `mark_status(` and `mark_status_fn(`,
excluding tests):

| File | Flip sites | Kind |
|---|---|---|
| `shared/scripts/github_triage/resolve.py` | `:76` `:121` `:190` | automatic |
| `shared/scripts/hooks/check_drift.py` | `:361` | automatic |
| `shared/scripts/lib/phase_quality/_triage_bundle.py` | `:254` | automatic |
| `shared/scripts/tools/accepted_risks_converge.py` | `:149` | automatic |
| `plugins/shipwright-compliance/scripts/audit/triage_bundle.py` | `:171` | automatic |
| `plugins/shipwright-compliance/scripts/lib/test_evidence.py` | `:891` | automatic |
| `plugins/shipwright-compliance/scripts/lib/sbom_generator.py` | `:503` | automatic |
| `shared/scripts/tools/triage_promote.py` | `:149` `:195` | operator CLI |

All nine automatic sites share one shape: read the union unlocked, filter
`status == "triage"`, flip. The defect is not in any of them individually.

### Why not fix the resolver instead

`read_all_items` Pass 2 being `ts`-primary is *deliberate* and load-bearing: it
is what makes a status flip in the outbox and one in the tracked store resolve
consistently across the union (two external-review findings are encoded in that
function's comments). Making the resolver prefer human writers would need it to
know who wrote what, and would still let the automatic event sit in the log
looking authoritative. Refusing the write is the smaller and truer fix: the
event that should not exist never gets written, and the resolver keeps its one
job.

---

## Acceptance Criteria

- **AC-1** — `triage.mark_status` accepts a keyword-only `expected_status`
  (one status, or several) and checks the item's currently-resolved status
  against it **inside the file lock it already holds for the write**. No second
  lock, no widened lock scope, no new lock file.
- **AC-2** — when the precondition does not hold, **no status event is written**
  and `triage.StatusPreconditionError` is raised, carrying the item id, what was
  expected, and what the store actually holds. A caller cannot mistake the miss
  for success: the failure is an exception, not a falsy return that a caller can
  drop on the floor.
- **AC-3** — `mark_status` returns **the status the store held immediately
  before the append** (it returned `None` before), so a real transition is
  distinguishable from a re-flip of an already-decided item. Callers that
  ignore the return are unaffected. Deliberately *not* claimed: that the
  appended event wins resolution. Pass 2 is `ts`-primary against a wall clock,
  so a pre-existing event with a future `ts` — a clock step, a skewed foreign
  writer — can out-sort the new one. That is pre-existing behaviour of the
  resolver, out of scope here (see below), and the wording is narrowed rather
  than left to imply more than the code delivers.
- **AC-4** — every automatic resolver passes `expected_status="triage"`, and a
  precondition miss is reported as **kept**: never counted as resolved, and
  never escalated into a failure that could turn an otherwise-healthy background
  run noisy. All nine sites in the table above.
- **AC-5** — the operator CLI (`triage_promote.promote` / `dismiss` / `defer`)
  passes the precondition through to the store, closing the gap between its own
  unlocked pre-check and the write. Its exit codes and error text are unchanged,
  so the CLI contract does not move.
- **AC-6** — **integration coverage** (`cross_component` fires on
  `shared/scripts/hooks/check_drift.py`): a real interleaving proves the pieces
  compose — the drift hook's resolve pass reads an item as open, an operator
  decides it in between, the resolve pass then runs, and the store still
  resolves to the operator's decision *and their reason*.
- **AC-7** — round-trip at the store boundary: a status event written under a
  satisfied precondition reads back through `read_all_items` with the same
  status, actor and reason; a **refused** write leaves the JSONL file
  byte-identical.

## Out of scope (deliberate)

- The `ts`-primary resolution order in `read_all_items` — see above.
- The WebUI's `proper-lockfile`, which does not compose with the Python byte
  lock. Cross-repo; the S3 wrap-up files a card for it.
- S3's un-park command, which will be the first caller to pass a non-`triage`
  `expected_status` (`("snoozed",)`). The parameter is shaped for it; the
  command is not built here.

## Risk flags

| Flag | Source | Enforces |
|---|---|---|
| `cross_component` | **recomputed from the planned diff**, not from the message: `shared/scripts/hooks/check_drift.py` matches `CROSS_COMPONENT_FILE_PATTERNS` → `(^|/)hooks/.+\.py$` | integration coverage (AC-6, non-dodgeable — F11 `check_integration_coverage` recomputes it) + full test suite + medium floor |

`touches_io_boundary` does **not** fire: the detector is path-based
(`.env`, `hooks.json`, `settings.json`, `*_config.json`, `*_state.json`) and this
diff touches none of them; its AST-pair half is documented as deferred. AC-7 runs
a round-trip probe anyway because the subject *is* a cross-process file store —
recorded as a chosen probe, not as a fired flag.

## Complexity — why medium, on positive evidence

Stage 1 returned `small` with `prior_source: history`, i.e. the fall-through
median, which carries no information about this change. Stage 2 upgrades on
evidence that exists: the diff-driven `cross_component` detector fires, which is
a `medium` floor by the risk taxonomy, and `mark_status` is a public API with
eleven call sites across `shared/` and two plugins.

## Bloat — every baselined file this diff touches sat exactly on its ceiling

Measured at `dd2c3019`; every one of these needs a deliberate bump in this
commit, because the anti-ratchet blocks a touch that adds a line to an entry
already at `current`:

| File | Baseline at `dd2c3019` | After | State |
|---|---:|---:|---|
| `shared/scripts/triage.py` | 701 | **837** | `exception` (ADR-100) |
| `plugins/shipwright-compliance/scripts/lib/test_evidence.py` | 907 | 931 | grandfathered |
| `plugins/shipwright-compliance/scripts/lib/sbom_generator.py` | 523 | 548 | grandfathered |
| `shared/scripts/hooks/check_drift.py` | 432 | 446 | grandfathered |
| `shared/scripts/lib/phase_quality/_triage_bundle.py` | 308 | 325 | grandfathered |
| `shared/scripts/tools/triage_promote.py` | 304 | 324 | grandfathered |
| `plugins/shipwright-compliance/tests/test_sbom_generator.py` | 845 | 847 | `exception` (ADR-098) |
| `plugins/shipwright-compliance/tests/test_test_evidence.py` | 575 | 577 | grandfathered |

**Every number above was re-measured against the committed
`shipwright_bloat_baseline.json` after the last review round.** An earlier
version of this table was stale by one round in four rows — the baseline was
correct and the *evidence table* was not, which the doubt review caught. That
is the failure this document exists to prevent, so it is recorded rather than
silently corrected.

**Eight entries raised, none lowered** — each new `current` is compared against
`origin/main`, not against an intermediate value from within this run, because
lowering an entry a concurrent PR then restores is what blocked a merge in
#490 vs #492.

`triage.py` **+136** is the one that deserves a sentence rather than a row. The
large majority is contract rather than logic: the exception class with its
`kept_note` shape and its `ascii()` hardening, the `expected_status`
normalizer, and the docstring — including the limitation external review asked
to be written down (the guarantee covers writers that cooperate with this lock,
and the Command Center does not). The in-lock check itself is about a dozen
lines. It is a large bump on an already-excepted file, and is recorded as a
deliberate one rather than absorbed quietly.

Not baselined and comfortably under 300: `github_triage/resolve.py` (203),
`accepted_risks_converge.py` (158), `shipwright-compliance/audit/triage_bundle.py`
(218). New tests go in a **new** file rather than into the six triage test files
that are all grandfathered at their current size.

`triage.py` is deliberately **not** split in this run. Its two-pass resolver is
the most carefully ordered function in the store — two external-review findings
are encoded in its comments — and moving it in the same PR that changes write
semantics would mix a risky refactor into a correctness fix. ADR-100 already
grants the file an exception; this bump extends it, as S1's 696 → 701 did.

## Spec Impact — MODIFY, FR-01.14 (Triage Inbox)

FOLD, not MINT: this completes an existing guarantee rather than adding a
capability. Two acceptance criteria are appended to FR-01.14; the table row's
description, `Basis` and `Layers` cells are untouched (`Layers` stays
`unit (inferred)` — advisory).

## External plan review — findings and resolutions

Provider `openrouter`, mode `iterate`. **GPT answered `revise`; Gemini truncated
(`finish_reason=length`) on both attempts and is recorded `degraded`, NOT
counted as a pass** — its partial text independently raised the same
`str`-is-iterable footgun, which is why that one is treated as the
highest-confidence finding of the set.

**Provenance, stated precisely.** The review was invoked twice. Only the second
invocation was persisted, and that artifact —
`iterate-2026-07-31-it1-s2-expected-status/external_plan_review.json` — carries
**seven** numbered GPT findings, which are rows 1–7 below.

`reviews.json` records `findings_count: 8` for the `plan` pass, and the eight
break down as **1 Gemini + 7 GPT**: entry 1 is the one finding recoverable from
Gemini's truncated reply (the `str`-is-iterable substring hazard, `severity:
high`), entries 2–8 are GPT's seven. The closing summary is not a ninth entry —
it was concatenated into entry 8's `suggestion` field, which is why the parse
ends `SHIPWRIGHT_VERDICT: revise`. Gemini's *verdict* remains `unavailable` and
its pass is **not** counted; that one salvaged finding being in the record is
not the same as the reviewer having answered.

**Rows 8–11 came from the first invocation, whose output was not written to
disk.** They are therefore marked *self-raised*: they are acted on, but no
artifact in this repo evidences an external reviewer having raised them, and
they must not be counted as external-review findings.

Every row is accepted; none rejected.

| # | Finding | Resolution |
|---|---|---|
| 1 | `expected_status` "one status or several" is underspecified — a bare `str` is iterable, so `previous not in expected_status` becomes a substring test | Normalize at the boundary: `str` → one-element tuple; validate every member against `STATUSES`; reject an empty collection with `ValueError`. The normalized tuple is carried on the exception. Tested for single, multiple, invalid member, empty, and wrong type |
| 2 | Protection holds only among writers that cooperate with the Python byte lock — the WebUI's `proper-lockfile` can still interleave | Stated in the `mark_status` docstring and in AC-6's scope. The change notes say *cooperating writers*, never "the race is fixed" |
| 3 | `StatusPreconditionError` is a new cross-package error contract; alias imports (`mark_status_fn`) may bind a **different `triage` module object**, so `except` would not catch | The lazy `_triage_api()` loaders return the exception class **from the same import that produced `mark_status`**, so class identity is guaranteed by construction rather than by import luck. Covered by an execution-level test on an alias-based compliance producer |
| 4 | "Reported as kept" needs one operational contract across all nine producers | Every arm leaves the item out of the resolved count and reports through ONE shape — `StatusPreconditionError.kept_note`, defined on the exception so nine sites cannot drift into nine wordings. It carries item id + actual + expected and nothing else. Pinned by a source-level test that every arm uses it. `accepted_risks_converge` prints to stdout rather than stderr, because that command's whole report — including the `dismissed` line beside it — is stdout |
| 5 | An item that resolves to *no* status, or carries malformed legacy status data, is undefined for both the return value and the comparison | `None` is the explicit representation in the return type and in `.actual`; `expected_status="triage"` refuses such an item rather than writing. Tested with a legacy append line that carries no `status` key |
| 6 | Calling `read_all_items` under the lock is safe **only** while it stays lock-free — a future refactor could self-deadlock on the non-reentrant lock | Documented at the call site as a prerequisite, and pinned by a test that counts lock acquisitions during one `mark_status` call and asserts exactly one |
| 7 | The new diagnostic path must not widen what gets logged | Messages carry item id and status values only — never `reason` text, never the item payload |
| 8 (self-raised) | Changing the return from `None` to a status is source-compatible but not behaviour-compatible for any consumer asserting `is None` | Repo-wide sweep of every `mark_status` consumer, alias, wrapper and mock — including tests — before the change is called done |
| 9 (self-raised) | The CLI's documented error text must survive the **race** path, not just its own pre-check | `StatusPreconditionError` is caught at the CLI boundary ahead of any generic `ValueError` handler and reformatted to the existing wording. A test forces the decision to land *between* the pre-check and the write, then asserts stdout/stderr and exit code are unchanged |
| 10 (self-raised) | A sequential integration test would not prove AC-6 — it could run the operator decision before the hook's snapshot was even taken | The test installs a deterministic barrier: the operator's transition lands through the real store API **after** the hook has its open-item snapshot and **before** its real `mark_status` call |
| 11 (self-raised) | The byte-identity probe must cover the whole union, for an item resident in each store | Both `triage.jsonl` and `triage.outbox.jsonl` are byte-snapshotted around a refused write, run once per residence |

## Review cascade — Stage 2 (code-reviewer)

**No high-severity findings.** The reviewer independently re-verified the
load-bearing claims rather than taking them from the spec: that
`read_all_items` takes no lock on any path (so the in-lock read cannot
self-deadlock), that `StatusPreconditionError` subclassing `ValueError`
creates no swallow-hazard in any existing `except ValueError` (it checked both
CLI entry points), that all nine arms exclude a refusal from both the resolved
count and the error list, that `_not_triage_error` reproduces both prior CLI
messages character-for-character, and that all eight baseline entries measure
to their recorded value.

Eleven lower findings; **ten accepted and fixed, one declined with reason.**

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | med | `item_id` interpolated raw into the exception message and `kept_note`. It is read from a git-tracked JSONL any producer appends to and is only checked to be a `str`, so a crafted id puts ANSI/CR on six producers' stderr; and `repr()` does not escape non-ASCII, so a foreign `actual` raises `UnicodeEncodeError` on a cp1252 console **inside a diagnostic path** | **fixed** — `ascii()` on both store-supplied values, which closes the injection and the encoding vector in one step. The ASCII test now builds the exception from hostile input (`\x1b[2K`, `\r\n`, `ß`) instead of from ASCII, so it tests the interpolated value rather than the format string |
| 2 | med | Both AST pins only matched `ast.Name`, so `import triage; triage.mark_status(...)` escaped **both** directions — and the forward pin accepted `expected_status=None`, the documented unconditional flip | **fixed** — `_called_name` matches `ast.Attribute` too, and the forward pin now rejects a `None` or non-literal value. "A tenth producer fails the reverse test" is now true |
| 3 | low | The reverse pin filtered on **absolute** path components, so a checkout under any directory named `tests` skips the whole tree and reports every entry stale; and one unparseable file anywhere would ERROR this unrelated test | **fixed** — relative parts, and `SyntaxError` skips that file |
| 4 | low | The new `sys.stderr.write` sits inside an `except` in two `_dismiss` helpers that are called from inside a `sum(...)` and promise total swallowing — a broken pipe would abort the remaining dismisses and the append after them | **fixed** — the diagnostic write is guarded at both sites |
| 5 | low | Adding the exception to the `from triage import (...)` list widened what an `ImportError` disables: under the documented plugin-cache skew the whole compliance producer would go silent, where before it merely lacked the precondition | **fixed** — all names now come off one `import triage` module object (a *stronger* identity guarantee than the named import), with the exception read via `getattr` and a never-raised `_NoPrecondition` fallback |
| 6 | low | AC-5 and the ledger claim "same message **and exit code**", but the test called the library function and asserted neither an exit code nor a stream | **fixed** — added `test_cli_race_path_keeps_its_exit_code`, which drives `triage_promote.main` (the real process boundary) through the race and asserts exit 2 |
| 7 | low | Three test names promised more than they asserted | **fixed** — the ASCII test now uses hostile input (see 1); `…_and_nothing_else` renamed to `…_only` with the structural argument stated; the CLI test now actually calls `promote` and asserts on the promoted item rather than on an append set no decision path touches |
| 8 | low | Unguarded `sys.path.insert` repeated in three test bodies, unlike the sibling files' module-scope idiom | **fixed** — module scope, guarded, once |
| 9 | low | The annotation understates the accepted types, and `-> str \| None` is wrong for a legacy line whose `status` is a non-`str` | **fixed** — a non-`str` resolved status now collapses to `None`, which makes the annotation true AND makes such an item refuse under any precondition instead of being compared as some other type |
| 10 | low | The lock section parses each store twice (`_append_ids_at`, then `read_all_items`), doubling lock hold time in O(N) sweep loops | **declined, with reason** — the fix means restructuring the resolution path, and this run deliberately does not touch `read_all_items` (mini-plan, "Alternative considered"; Stage 1 approved that boundary). Mixing a refactor of the store's most carefully ordered function into a concurrency fix is the trade this run already decided against. The cost is bounded and measured — one extra parse of a ~1000-line file per flip, inside a lock held for an `fsync` anyway. Recorded here so the next toucher inherits the measurement, not a silence |
| 11 | low | `_dismiss_if_open` was spliced between two halves of the module's constants block | **fixed** — moved below `_LEGACY_MIGRATIONS` |

## Review cascade — Stage 3 (doubt-reviewer, fresh context, biased to disprove)

**The core guarantee survived a deliberate attempt to break it.** What was
tried and failed: defeating it through the outbox/tracked union (the
precondition reads the union inside the same lock every cooperating writer
takes, so a sibling's event is visible wherever it landed); through the
`ts`-primary Pass-2 tiebreak (the refusal is a set-membership test on the
resolved status, not an ordering claim — Windows' ~15.6 ms clock granularity
makes equal-`ts` common and it still holds); through the GC / sweep /
reconcile rewrite paths (`triage_gc.is_machine_churn` requires both a machine
`statusBy` *and* an exact machine `statusReason`, so an operator decision is
structurally undroppable and cannot be resurrected into a re-closable state);
and by trying to make the refusal itself lose data or fail to converge (every
producer filters `status == "triage"` first, so a refused item leaves its own
scan next run — no retry, no loop, no un-closeable item).

Six doubts, three of them medium. **All six accepted and fixed.**

| # | Sev | Doubt | Disposition |
|---|---|---|---|
| 1 | med | **AC-1's central property had no test.** Hoisting the residence probe and the precondition *above* the `with` — the natural "don't take the lock just to find it's a no-op" optimisation — leaves every one of the 36 ledger rows green and fully reopens the race. Every barrier in the run is single-threaded, so nothing observed that the read happens while the lock is held | **fixed** — `test_the_precondition_is_evaluated_while_the_lock_is_held` wraps (does not stub) `read_all_items` and subclasses the real lock to record held-depth, asserting the read ran inside. Verified by emulating the hoist: the test goes red, the rest stay green |
| 2 | med | **The `_NoPrecondition` fallback did not defend the skew it named.** Under a `triage` predating `expected_status`, `getattr` yields the placeholder but the call site still passes the kwarg — so the old `mark_status` raises `TypeError` on *every* flip, the refusal arm never matches, and the whole dismiss path dies silently with `dismissed: 0` and no error. Strictly worse than what its own docstring claimed | **fixed by deletion** — a guard that does not guard is worse than none. All names now resolve inside one `try`, and `AttributeError` joins `ImportError` so a skewed store disables the producer **cleanly and totally, rather than half-working**. Stated precisely, because the Stage-2 re-check caught the overstatement: the disable is *not* visible — the loader returns all-`None` and the caller returns zeros with no `error` key and no stderr line. That silence is unchanged pre-existing behaviour of the `ImportError` path and is not fixed here. What the change buys is that the append half can no longer keep working while the dismiss half is dead, which is the state an operator would read as healthy |
| 3 | med | **Four of eight rows in the bloat table contradicted the committed baseline** (818/317/540/923 vs the real 830/325/545/927), and the Stage-2 record certified them as re-verified | **fixed** — table re-measured against the committed JSON, the `+117` narrative corrected to `+129`, and the staleness recorded rather than silently patched |
| 4 | low | The exit-code test passed for a reason other than the one it stated: `StatusPreconditionError` *is* a `ValueError`, which `main` already maps to 2, so deleting the conversion would still exit 2 | **fixed** — the docstring now says what it actually pins, and the test asserts the CLI's stderr wording, which is the genuinely load-bearing half |
| 5 | low | AC-3 claimed more than the code delivers: `previous` is a pre-write read and the function never checks the appended event wins resolution — a pre-existing event with a future `ts` can out-sort it | **fixed** — AC-3 narrowed to "the status the store held immediately before the append", with the limitation named and attributed to the pre-existing resolver |
| 6 | low | Stage-2's finding 4 was only half-fixed: two of four new diagnostic writes were guarded, two more sat unguarded in swallow-everything paths (`resolve.py`, `check_drift.py`) | **fixed** — both guarded; `resolve.py` gained a `_report` helper. `accepted_risks_converge`'s unguarded `print` is left as-is *deliberately*, matching the success line beside it, and that is now stated rather than implied |

## External code review (post-cascade)

Provider `openrouter`, mode `code`, full 2166-line code diff (not a slice —
narrow slices produced false "AC-X not implemented" findings in S1). Artifact:
`iterate-2026-07-31-it1-s2-expected-status/external_code_review.json`.

**Both providers answered this time**, unlike the plan review. GPT: `revise`
with three findings. **Gemini: `revise` with an empty body** — it emitted only
the verdict token and no findings. It is recorded `success` by the tool because
it did not truncate, but it contributed nothing reviewable, and it is not
counted as a substantive second opinion.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| 1 | med | `sbom_generator.py` — the refusal arm's `sys.stderr.write` is unguarded, so a broken stderr turns a benign "kept" into a producer failure, violating AC-4 | **fixed** — guarded. This is the same class the doubt review raised as doubt 6, at two sites I had missed when fixing it: I guarded four arms and left these two |
| 2 | med | `test_evidence.py` — same arm, same gap | **fixed** — guarded |
| 3 | low | `_normalize_expected` does not check members are strings before the membership test, so `(["triage"],)` could raise `TypeError` from a validator whose contract is `ValueError` | **mechanism did not reproduce; hardened anyway.** Probed directly: `STATUSES` is a **tuple**, so membership compares by equality and never hashes — `(["triage"],)`, `(b"x",)` and `(1,)` all already raise the documented `ValueError`. The finding is a false positive as stated. But the guarantee is a property of `STATUSES` being a sequence rather than of this function, so an explicit `isinstance` check now makes it local, with the non-reproduction recorded at the line so nobody "re-fixes" it |

That two independent passes (doubt 6, external 1–2) found the *same* unguarded
diagnostic writes at *different* sites is the useful signal here: the first fix
was applied by inspection and inspection missed two of six.

## Self-Review (Step 7)

| # | Item | Verdict |
|---|---|---|
| 1 | Spec compliance | **pass** — all seven ACs implemented; no capability added beyond them. The tuple form of `expected_status` is the one forward-looking piece, and it exists because S3's un-park is a named, imminent caller, not a hypothetical |
| 2 | Error handling | **pass** — the new failure mode is an explicit exception at every boundary; each of the nine producers has a dedicated arm ahead of its generic handler, so a refusal can neither be swallowed nor mislabelled as a crash |
| 3 | Security basics | **pass** — no user input, no new external surface. The one widened output is the diagnostic line, deliberately narrowed to ids and statuses so a stored `reason` cannot leak into a producer log (external finding #7) |
| 4 | Test quality | **pass** — every load-bearing test was run with the precondition reverted and observed RED (counts below). Assertions are on store state and producer counts, not internals |
| 5 | Performance basics | **pass** — one extra pass over a ~1000-line file, inside a lock already held across an `fsync`. No new I/O outside the critical section, no loop of writes added |
| 6 | Naming & structure | **pass with one deliberate exception** — every changed file stays under its cap except the six already-baselined ones, each raised explicitly above. `triage.py` at 818 is the exception this run consciously extends rather than hides |
| 7 | Affected boundaries | **pass** — producer/consumer pair identified (`mark_status` writes the JSONL; `read_all_items` and the WebUI's TypeScript reader consume it). Round-trip probe exists (AC-7) and passes, in both residences, including byte-identity on refusal |
| 8 | Test hygiene probe | **pass** — `scan_test_hygiene.py` over all five changed/new test files: *no findings* |

## Confidence Calibration

- **Boundaries touched:** the `.shipwright/triage.jsonl` + `triage.outbox.jsonl`
  append-log pair (cross-process, byte-locked, with a known non-cooperating
  third writer); the `mark_status` public API consumed by `shared/` and by
  `shipwright-compliance`; the SessionStart drift hook.

- **Empirical probes run** — each is a thing I did not know before running it:

  | Probe | Finding |
  |---|---|
  | Enumerate every `mark_status` **and** `mark_status_fn` call outside tests | The brief's caller list was wrong in both directions: `suite_race_triage.py:103` is a *read*, not a flip, and four automatic producers were missing. Nine automatic sites across six files, plus two CLI sites |
  | Run `risk_detectors` against the planned file list | `cross_component` **fires** (`check_drift.py` matches `hooks/.+\.py$`) — the medium floor and the integration-coverage requirement are recomputed facts, not a judgement call. `touches_io_boundary` does **not** fire |
  | Grep every consumer of `mark_status`'s return value | Zero — no caller, wrapper, mock or test assigns it or asserts `is None`. Changing `None` → `str \| None` is safe (external finding #8) |
  | Read the call graph of `read_all_items`, then read `FileLock` | It is lock-free today, and `FileLock` is **non-reentrant with no timeout**: a future read-side acquisition would not raise, it would HANG (Windows spins on `msvcrt.locking`, POSIX blocks in `flock`). The hazard is a hang, not an error — which is why a lock-acquisition *count* is the pin |
  | Run the compliance plugin suite in a fresh worktree | 30 failures that are **not** mine — `ModuleNotFoundError: yaml` from an unsynced plugin venv (`pyyaml` is already a declared dependency). Verified identical on the base commit before attributing |
  | Run every affected root under `CI=true` | Green, except 4 pre-existing Windows symlink-privilege failures in `test_security_gate_symlinks.py`. `$CI` changes producer routing in this repo, so a local-only pass would have proved nothing |
  | Revert the precondition and re-run | 14 test cases go RED across five files — see the ledger's RED column |
  | **Hoist** the precondition out of the lock (leave it otherwise intact) | Before the doubt review: **everything stayed green**. AC-1's central property was untested and the race was fully reopened by a plausible refactor. After: exactly one test goes red, and it is the one that names the property |
  | Feed the exception hostile input (`\x1b[2K`, `\r\n`, a non-ASCII status) | Both producer-facing strings stay pure ASCII with no raw escapes — `ascii()`, not `repr()`, because `repr` passes non-ASCII through and a cp1252 stderr would raise inside a path that is only reporting a benign outcome |

- **Test Completeness Ledger** — 7 ACs, **41 behaviours enumerated, 41 tested,
  0 testable-but-untested.** "RED" = observed failing with the fix reverted,
  i.e. bound to the production line rather than to its neighbourhood.
  **58 test cases across 7 files; 14 go red when the precondition is disabled,
  and one more goes red when the precondition is merely moved OUTSIDE the lock**
  (probed separately — row 12).

  | # | Behaviour | Status | Evidence | RED |
  |---|---|---|---|---|
  | 1 | A flip is refused when the resolved status differs | tested | `test_precondition_refuses_a_decided_item` | yes |
  | 2 | A flip is allowed when the status matches | tested | `test_precondition_allows_a_still_open_item` | — positive path |
  | 3 | Omitting `expected_status` keeps the old unconditional flip | tested | `test_without_expected_status_prior_behaviour_is_unchanged` | — back-compat |
  | 4 | A refused write leaves **both** stores byte-identical, item tracked | tested | `test_refused_write_leaves_both_stores_byte_identical[tracked]` | yes |
  | 5 | …and item resident in the outbox | tested | `…[outbox]` | yes |
  | 6 | An allowed write round-trips status/actor/reason | tested | `test_allowed_write_round_trips_through_the_reader` | — |
  | 7 | `mark_status` returns the status it replaced | tested | `test_mark_status_returns_the_status_it_replaced` | — |
  | 8 | A bare `str` is normalized, never iterated character-wise | tested | `test_a_single_string_is_normalized_not_iterated` | yes |
  | 9 | Several expected statuses accepted (S3's un-park shape) | tested | `test_several_expected_statuses_are_accepted` | — |
  | 10 | Empty / unknown / non-iterable rejected before any I/O | tested | `test_invalid_expected_status_is_rejected` ×5 | — own guard |
  | 11 | An item with no resolvable status is refused, `actual is None` | tested | `test_item_without_a_status_field_is_refused_not_written` | yes |
  | 12 | **The precondition is evaluated while the lock is HELD** | tested | `test_the_precondition_is_evaluated_while_the_lock_is_held` | yes — red under the *hoist* probe, which every other row survives |
  | 13 | `mark_status` acquires the canonical lock exactly once | tested | `test_mark_status_acquires_the_canonical_lock_exactly_once` | — hazard pin |
  | 14 | `read_all_items` acquires no lock (else the read side HANGS) | tested | `test_read_all_items_takes_no_lock` | — hazard pin |
  | 15 | An unknown `new_status` still raises first, unchanged | tested | `test_unknown_new_status_still_raises_before_the_precondition` | — |
  | 16 | An unknown id still raises `KeyError` | tested | `test_unknown_id_still_raises_keyerror` | — |
  | 17 | `StatusPreconditionError` is a `ValueError` | tested | `test_status_precondition_error_is_a_valueerror` | — contract pin |
  | 18 | Every registered flip passes a REAL `expected_status` — not `None`, not a non-literal | tested | `test_every_registered_flip_passes_a_real_expected_status` ×8 | — forward drift |
  | 19 | No unregistered module flips status — bare *or* attribute call | tested | `test_no_unregistered_module_flips_status` | — reverse drift |
  | 20 | Every automatic arm reports through the one shape | tested | `test_every_automatic_arm_reports_through_the_one_shape` ×7 | — forward drift |
  | 21 | `kept_note` carries id + actual + expected, incl. multi-expected and `None` | tested | `test_kept_note_carries_id_actual_and_expected_only` | — |
  | 22 | Store-supplied values cannot reach the console unescaped (ANSI / CR / non-ASCII) | tested | `test_store_supplied_values_cannot_reach_the_console_unescaped` | — hazard pin, hostile input |
  | 23 | GitHub resolver keeps a decided item and does not count it | tested | `test_github_resolver_keeps_a_decided_item_and_does_not_count_it` | yes |
  | 24 | GitHub resolver still counts a landed dismiss | tested | `test_github_resolver_still_counts_a_landed_dismiss` | — negative control |
  | 25 | Phase-quality dismiss keeps a decided item | tested | `test_phase_quality_dismiss_keeps_a_decided_item` | yes |
  | 26 | Converger keeps a decided item, reports on **stdout**, counts no failure | tested | `test_converger_keeps_a_decided_item_and_reports_no_failure` | yes |
  | 27 | Converger still dismisses an untouched item | tested | `test_converger_still_dismisses_an_untouched_item` | — negative control |
  | 28 | Converger still counts a genuine store failure | tested | `test_a_real_failure_is_still_counted` | — |
  | 29 | The audit-bundle loader yields the store's own exception class | tested | `test_audit_bundle_loader_yields_the_stores_own_exception` | — identity pin |
  | 30 | …and so does the sbom loader | tested | `test_lib_loaders_yield_the_stores_own_exception[sbom_generator]` | — identity pin |
  | 31 | …and the test-evidence loader | tested | `test_lib_loaders_yield_the_stores_own_exception[test_evidence]` | — identity pin |
  | 32 | Each loader yields the SAME module's `mark_status` alongside it | tested | `test_the_loaders_also_yield_the_stores_own_mark_status` | — identity pin |
  | 33 | sbom producer's own arm runs; a refusal is not an `error` | tested | `test_a_refusal_runs_the_producers_own_arm_and_is_not_an_error` | yes |
  | 34 | compliance-backlog producer's own arm runs | tested | `test_compliance_backlog_arm_runs_and_is_not_an_error` | yes |
  | 35 | test-evidence producer's own arm runs | tested | `test_test_evidence_arm_runs_and_is_not_an_error` | yes |
  | 36 | CLI race path reports the CLI's own wording, not the store's | tested | `test_cli_race_path_reports_the_same_message_and_exit_code` | yes |
  | 37 | CLI race path reaches the operator as exit 2 + that wording, not a crash | tested | `test_cli_race_path_keeps_its_exit_code` | — scope stated per Stage-3 doubt 4 |
  | 38 | CLI pre-check and race path share one wording | tested | `test_cli_pre_check_and_race_path_share_one_wording` | — |
  | 39 | CLI still promotes AND defers a still-open item | tested | `test_cli_still_promotes_and_defers_a_still_open_item` | — negative control |
  | 40 | **integration** — an operator's dismiss survives a concurrent drift sweep, and no automatic event is written at all | tested (`category: integration`) | `test_operator_dismiss_wins_against_a_concurrent_drift_sweep` | yes |
  | 41 | **integration** — the sweep still resolves an item nobody touched | tested (`category: integration`) | `test_the_sweep_still_resolves_an_item_nobody_touched` | — negative control |

  Several rows exist only because a check refused to accept a claim, and they
  are recorded rather than quietly folded in. Row 25 originally decided the item
  *before* the producer ran, which filtered it out of the producer's own scan —
  `_dismiss` was never called, so the row would have read "tested" about a line
  no test executed; the RED counter-check exposed it. Rows 26/34/35 did not
  exist until the ledger was written: three of the nine arms had only structural
  coverage, and "testable ⇒ tested" made writing them a work item, not a note.
  Row 12 did not exist until the doubt review observed that AC-1's *central*
  property — that the check happens inside the lock — was the one thing nothing
  tested; hoisting it out left all other rows green.

- **Confidence-pattern check:**
  - *Asymptote (depth):* the deepest question here is "can the check itself
    deadlock or lie?". Both were probed to their floor rather than argued —
    lock acquisitions are counted (12/13), the reverted-fix run names exactly
    which assertions depend on the change (12 RED), and the refusal is proven
    by **byte identity** of both files rather than by a re-read that the same
    bug could satisfy.
  - *Breadth (coverage):* all eleven flip sites are covered, and the AST tests
    make that set self-maintaining in both directions — a tenth producer fails
    the reverse test, a dropped kwarg fails the forward one. The three producers
    I would otherwise have trusted by inspection are exactly the three the
    Stage-1 review caught reporting less than the rest, which is the argument
    against inspection.
  - *Integration composition:* `cross_component` fired, so a real interleaving
    (35) proves hook + store + operator CLI compose, with a negative control
    (36) so a refuse-everything implementation cannot pass.
  - *Where confidence is deliberately NOT claimed:* the Command Center writes
    through `proper-lockfile`, which does not compose with this byte lock. No
    test here claims that interleaving, the `mark_status` docstring says so, and
    it is listed out of scope rather than left to be assumed.

## Review Record

_(closed via `record_review_pass.py` — spec · self · plan · code · doubt ·
external_code)_
