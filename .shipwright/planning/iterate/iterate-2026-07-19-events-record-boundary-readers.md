# Iterate: Event-log record-boundary recovery across the audit + traceability read path

- **Run ID:** iterate-2026-07-19-events-record-boundary-readers
- **Intent:** BUG (Path C)
- **Complexity:** medium
- **Risk flags:** `touches_io_boundary`, `cross_component` (diff-driven — `events_log.py`)
- **Spec Impact:** NONE (defect repair; no requirement changes)
- **Predecessor:** iterate-2026-07-18-events-jsonl-record-boundary (PR #405)

## Problem

PR #405 fixed the **writers** (`record_event.append_event` / `_idempotent`, the
adopt `event_seeder`) and **one** canonical reader (`lib/config.read_events`).
Further read sites still use the pre-fix idiom — bare `json.loads(line)` inside a
`try` whose `except json.JSONDecodeError` skips the **whole physical line**.

> **The brief's enumeration of "six sites" was incomplete.** The Stage-2 code
> review found a 7th and 8th and pointed at more in the verifier package; a
> final exhaustive sweep found the rest. **Eleven** are fixed here; five remain,
> enumerated under *Out of scope* (`trg-360e494f`) rather than
> left implied-fixed. **This iterate does not close the defect class** — it
> closes the compliance/verifier/traceability read path and makes the true
> surface visible. Claiming otherwise would reproduce this bug's own moral:
> silence read as completeness.

When two records share one physical line, that idiom discards **both**. The
records are present on disk; the reader reports their absence. On an append-only
audit trail, corruption must never read as absence: a dropped `work_completed`
makes a step that *happened* read as one that *never did*.

### Reachability — the briefed mechanism did not survive testing

The brief (and the predecessor's rationale) states that union merge *creates* the
concatenation: "an ordinary merge of two worktrees joins an unterminated blob
last line to the next side first line. No write-time lock can guard that."

**That is not reproducible, and this iterate corrects it.** Tested on git
2.54.0 with the builtin driver and no custom `merge.union.*` override, across
five scenarios (side-A unterminated, both sides unterminated, base unterminated,
A-unterminated against a two-line B append, and A-unterminated with B unchanged):
git's merge machinery tracks *"\\ No newline at end of file"* as a diff property
and **reconciles it**. Zero joined lines in every case. Git does not create this
corruption.

What *is* verified, and is enough:

1. **The writer path — the mechanism #405 actually documented and fixed.** A
   writer appending onto an already-unterminated file puts two records on one
   line. `test_events_newline_integrity.py::test_append_onto_unterminated_log_does_not_concatenate`
   pins exactly this. #405 guards *Shipwright's* writers — it cannot guard an
   interrupted write, an external writer, or an operator edit, which are the
   causes `jsonl_records`' own docstring lists.
2. **Union merge PROPAGATES an existing concatenated line verbatim** (verified —
   AC7). It merges it straight into `main` without conflict or repair, where
   every downstream reader meets it. So a single unguarded write anywhere in the
   fleet, or any record already on disk from before #405, reaches every consumer
   of the merged log.

The reader half therefore remains load-bearing — just for the reason in (2)
rather than the one briefed. The fix is unchanged; only the justification is
corrected, because an unverified mechanism in a spec becomes an unverified
mechanism in the ADR and in every future reader's mental model.

## Root cause

The record-boundary contract was never centralised. Each reader open-coded
"one line == one record", so the fix in `lib/jsonl_records` (#405) reached only
the call sites that were rewritten to use it.

## The eleven sites fixed here, by import tier

**Tier A — no import barrier** (`lib.jsonl_records` is directly importable):

| # | Site | Current failure |
|---|---|---|
| 1 | `shared/scripts/lib/events_log.py:172-174` (`latest_event_dt`) | returns `None` → dashboard "data as of" banner blank |
| 2 | `shared/scripts/lib/events_log.py:219-221` (`finalized_run_ids`) | returns **empty set**, not `None` → see severity note below |
| 3 | `shared/scripts/tools/verifiers/common.py:156-158` (`read_events_jsonl`) | F11 verifiers see a completed step as absent |

**Tier B — ADR-045 `sys.modules['lib']` barrier** (the plugin ships its own
`scripts/lib`, so a bare `from lib import jsonl_records` resolves *there*):

| # | Site | Current failure |
|---|---|---|
| 4 | `plugins/shipwright-compliance/scripts/lib/collectors/change_history.py:126-128` | compliance change-history loses the event; **also leaks the file handle** (no context manager) |
| 5 | `plugins/shipwright-compliance/scripts/audit/group_b.py:83-85` | silent `continue` — no warning at all |
| 6 | `plugins/shipwright-compliance/scripts/audit/group_d.py:74-76` | audit group reads a real run as never finalized |

**Found by the Stage-2 code review, not by the brief** (same defect class, no
import barrier):

| # | Site | Current failure |
|---|---|---|
| 7 | `shared/scripts/lib/backfill_scan.py:178` (`_load_events_fr_by_commit`) | drops both records' `affected_frs` → silently un-links an FR from the commit that covered it, on the **traceability** surface |
| 8 | `plugins/shipwright-test/scripts/tools/boundary_coverage_report.py:238` (`_load_events`) | same drop; also had no `isinstance` guard, so it carried the AC10 bare-scalar crash class |

**Also in the verifier package — the highest operator impact in the set.** These
sit in the SAME package as site 3 and serve the same F11 consumer; splitting one
package across two iterates would reproduce this bug's own root cause:

| # | Site | Current failure |
|---|---|---|
| 9 | `verifiers/iterate_checks.py:206` (`_committed_blob_has_event`) | the F11 `check_events_has_commit` **oracle**. Failure is INVERTED: a `work_completed` sitting second on a concatenated line read as absent, so **F11 failed finalization for a correctly-recorded run** |
| 10 | `verifiers/iterate_checks.py:859` (`_find_work_event_by_commit`) | same drop; no `isinstance` guard → `AttributeError` on a scalar line |
| 11 | `verifiers/iterate_checks.py:894` (`_find_work_event_by_run_id`) | **not named by the review** — adjacent and identical to site 10. Found by reading the file rather than the finding |

### Severity note — site 2 is worse than "returns nothing"

`finalized_run_ids` documents `None` as *ownership undeterminable → callers fail
open to whole-set checking*. A concatenated line does **not** produce `None`; it
produces an **empty set**, which reads as the confident claim *"this tree
finalized no runs"*. The gate then scopes itself to nothing and passes. This is a
fail-**open** drift gate masquerading as a conclusive answer — the one outcome
the docstring's fail-open design was written to avoid.

## Empirical probes

All six briefed sites reproduced against a line built exactly as union merge
builds it
(`json.dumps(A) + json.dumps(B) + "\n"`), both records valid, on one line:

```
Tier A:  events_log.latest_event_dt        0/2 recovered (returned None)
         events_log.finalized_run_ids      0/2 recovered (returned empty set)
         verifiers.common.read_events_jsonl 0/2 recovered
Tier B:  change_history._read_event_log    0/2  + ResourceWarning: unclosed file
         group_b._load_events              0/2  (silent — zero warnings)
         group_d._load_events              0/2
Reference (already fixed, #405):
         lib.config.read_events            2/2 recovered
```

**Probe 2 — the ADR-045 barrier is real for compliance too** (#405 verified it
only for *adopt*). `from lib import jsonl_records` with the compliance
`scripts/` dir on `sys.path` raises
`ImportError: cannot import name 'jsonl_records' from 'lib'
(…/plugins/shipwright-compliance/scripts/lib/__init__.py)`. Confirmed, not assumed.

**Probe 3 — the brief's proposed Tier B remedy is unnecessary.** The brief
proposed "the same documented-duplicate treatment" (the adopt precedent). It is
not needed: the compliance plugin already owns a **tested, pollution-free shared
loader**, and `group_d.py` already imports it. Verified both entry points return
the real shared module and recover 2/2, leaving the plugin-local `lib` intact:

```
lib/collectors/_lib_loader.load_shared_lib("jsonl_records") -> shared/scripts/lib/jsonl_records.py
audit/audit_adapters.load_shared_lib("jsonl_records")       -> shared/scripts/lib/jsonl_records.py
recovered: ['a', 'b']   plugin-local `lib` after load: intact
```

**Duplication is therefore rejected as the Tier B design.** Duplicating a
~70-line parser with a subtle partial-recovery contract into a second package —
where it would silently drift from the SSoT — would be strictly worse than the
one-line delegation the barrier was thought to forbid.

## Governing invariant (adopted after external review)

**Behaviour-preserving except for record recovery.** Every site keeps its
existing corruption-*reporting* contract — silent stays silent, warning stays
warning — and only what it *recovers* changes. This came out of the review
round (both reviewers independently flagged the warning change as unnecessary
risk) and it is what keeps a defect repair from smuggling in an observable
behaviour change.

The exceptions are all places the old code **crashed**, plus one reporting
widening. Enumerated exhaustively, each as its own AC — the list has now been
caught non-exhaustive twice, so it is stated by AC number rather than by prose:

* **AC8** — three uncaught crashes in `events_log`.
* **AC10** — the non-dict guard, at `group_b` / `group_d` / `change_history`
  (Tier B) **and** `boundary_coverage_report` (site 8, no import barrier).
* **AC17** — the same non-dict crash class at `iterate_checks` sites 10-11
  (verifier package).
* **AC12** — one widening of *what counts as* unrecoverable, at a site that
  already warns.

## Acceptance criteria

- **AC1** — `events_log.latest_event_dt` recovers all records from a
  concatenated line and returns the latest instant among them. Partial recovery
  is correct here (renderer banner; documented "skip corrupt silently").
- **AC2** — `events_log.finalized_run_ids` recovers all `adr_id`/`run_id` values
  from a concatenated line. Its **pre-existing corrupt policy is unchanged**: an
  unrecoverable fragment is skipped and the values that decoded are still
  returned; `None` stays reserved for absent-or-unreadable. See the
  corrupt-policy note below for why the stricter form was reverted.
- **AC3** — `verifiers.common.read_events_jsonl` recovers all records, **and
  both documented G5 properties are preserved**: it reads the LITERAL
  `project_root` path (no `resolve_events_path` worktree redirect) and stays
  SILENT (corruption surfaces as a `CheckResult`, never a warning).
- **AC4** — `change_history._read_event_log` recovers all records, keeps warning
  on a genuinely unrecoverable fragment, and **closes its file handle**.
- **AC5** — `group_b._load_events` and `group_d._load_events` recover all
  records, preserve `None`-on-absent / `None`-on-`OSError`, and **remain
  silent** (no new warnings — governing invariant).
- **AC6** — Recovery stays **partial, never all-or-nothing**: a valid record
  followed by an unrecoverable fragment yields the valid record *and* reports
  the fragment. (All-or-nothing recovery would reproduce the bug it fixes.)
- **AC7** — INTEGRATION (`cross_component`): a real `merge=union` merge of two
  divergent branches **propagates** an existing concatenated line into the merged
  tree (it does *not* create one — pinned in both directions), and the shared
  readers plus the compliance change-history collector and both Group B/D audit
  loaders all observe **every** run afterwards.
- **AC8** — Three **latent uncaught crashes** in `events_log`, found during the
  review round and fixed incidentally by the delegation, stay fixed:
  a bare JSON scalar line crashed `latest_event_dt` with `AttributeError`
  (`'int' object has no attribute 'get'`), and undecodable bytes crashed **both**
  functions with `UnicodeDecodeError` — which is a `ValueError`, so the existing
  `except OSError` never caught it. The latter directly violated
  `latest_event_dt`'s own docstring promise that corruption must not "brick
  every renderer".
- **AC9** — Group B / Group D resolve `jsonl_records` to the **shared**
  implementation when imported through their real audit entry points, not to a
  plugin-local module (import-mode smoke test).
- **AC10** — Every converted reader returns **only JSON objects**. `group_b` /
  `group_d` / `change_history` / `boundary_coverage_report` appended
  `json.loads(line)` with no `isinstance` guard, so a bare scalar entered the
  list as a non-dict and crashed the first downstream `.get()`; the verifiers'
  `read_events_jsonl` filtered non-dicts already and keeps doing so. This is the
  fourth crash-class the delegation fixes (AC8 covers the three in `events_log`)
  and is enumerated so the governing invariant's exception list stays exhaustive
  rather than being quietly exceeded.
- **AC11** — `load_events` returns `None` on `OSError`, not just on absence.
- **AC12** — `change_history` warns for a bare scalar line, which it previously
  accepted silently as a non-dict "event". Widening *what counts as*
  unrecoverable at a site that already warns is consistent with the invariant,
  but it is an observable change and is therefore pinned rather than assumed.
- **AC13** — `backfill_scan._load_events_fr_by_commit` (site 7) recovers the
  `commit → affected_frs` map from a concatenated line. Highest-consequence site
  in the set: a dropped record silently un-links an FR from the commit that
  covered it, on the **traceability** surface.
- **AC14** — `boundary_coverage_report._load_events` (site 8) recovers records
  from a concatenated line (AC10 covers only its non-dict guard).
- **AC15** — The `events_log` import chain is **contract-tested, not incidental**.
  This region has already produced two BLOCKER-class defects, so every part of it
  is claimed and pinned rather than merely present:
  - loads in **all three** contexts — package member, by-file-location under a
    sentinel, and **flat** (`shared/scripts/lib` on `sys.path`, live in
    production via `backfill_test_links` → `backfill_scan`);
  - loads when a **foreign plugin's `lib`** is already bound in `sys.modules`,
    and leaves that binding **untouched** (the pollution defect);
  - the sentinel cache is **keyed per copy** (digest of the resolved parent
    dir), so two copies in one process — worktree vs plugin cache — do not share
    one parser, which would re-open the drift the copy-local load prevents;
  - a **missing sibling** raises `ImportError`, not `OSError`.
    `spec_from_file_location` does not stat, so without an explicit `.is_file()`
    check a `FileNotFoundError` would sail through the `except ImportError`
    guards that callers such as `backfill_scan` rely on.
- **AC16** — `iterate_checks._committed_blob_has_event` (site 9) finds a
  `work_completed` that is the **second** record on a concatenated line. This is
  the F11 `check_events_has_commit` oracle, so here the defect is **inverted and
  operator-facing**: pre-fix it made F11 *fail finalization* for a run that had
  recorded everything correctly. Recovery must not make the gate vacuous — an
  absent event still reads as absent.
- **AC17** — `iterate_checks._find_work_event_by_commit` and
  `_find_work_event_by_run_id` (sites 10-11) recover a second record and no
  longer crash on a bare scalar (neither had an `isinstance` guard).

### Corrupt-policy per caller — every site keeps the policy it already had

| caller | on unrecoverable fragment | why |
|---|---|---|
| `latest_event_dt` | use what recovered | renderer banner; a stale-but-present timestamp beats a blank one, and the docstring already documents silent skipping |
| `finalized_run_ids` | use what recovered (skip the fragment) | pre-existing documented contract — `None` is reserved for absent-or-unreadable, and "one bad row must not take down the audit" is explicit. Pinned by `test_arch_drift_event_scope.test_finalized_run_ids_skips_corrupt_lines` |
| `read_events_jsonl` (verifiers) | use what recovered, stay silent | G5: corruption must surface as a `CheckResult`, not a warning |
| `change_history` | use what recovered, warn | already warns today; keep it |
| `group_b` / `group_d` | use what recovered, stay silent | already silent today; keep it |

#### Reverted mid-build: the `None`-on-any-fragment rule

Both reviewers flagged (HIGH, independently) that iterating `result.records`
would give `finalized_run_ids` a *confident partial* answer, and proposed
returning `None` on any fragment. It was adopted, implemented — and then
**reverted during build**, because it broke the full suite:

`shared/tests/test_arch_drift_event_scope.py::test_finalized_run_ids_skips_corrupt_lines`
already pins the opposite, and `finalized_run_ids`' own docstring already
documented *"corrupt/blank skipped"* with `None` reserved for
absent-or-unreadable. Neither reviewer had that contract in context.

Decisive point: **that is a policy change, not record recovery.** Pre-fix, a
corrupt line already produced a partial set — deliberately. Widening `None`
would therefore violate this iterate's own governing invariant, inside a defect
repair, on a gate whose failure mode is *stricter* checking (whole-set) and so
carries no urgency. The question is legitimate and is filed as follow-up; it
deserves its own iterate, not a drive-by.

## Mini-plan

**Tier A** — delegate to the SSoT, mirroring `config.read_events`:

1. `events_log.py` — **relative import, then a BY-PATH sentinel load** as the
   fallback. Both functions iterate `result.records`; corrupt fragments stay
   silent here (renderer-facing, already documented as skip-silently).

   The import form is the single most consequential decision in this iterate, so
   the plan of record is the shipped one, not the first guess. A plain
   module-level `from .jsonl_records import …` was the original plan and it
   **broke 15 compliance tests**: Group F loads this module by file location
   under a sentinel name, where a relative import has no parent package. Two
   fallbacks were then tried and both failed worse, each verified empirically:

   - `from lib.jsonl_records import …` binds `sys.modules['lib']` to *shared's*
     package during the sentinel exec. `audit_adapters.load_shared_lib` never
     restores that binding, so every later compliance-local
     `from lib.thresholds import …` resolves against shared and raises.
   - `from jsonl_records import …` needs `shared/scripts/lib` **itself** on
     `sys.path`; neither loader inserts it. With `lib` pre-bound to a plugin,
     *all* branches failed and the F5 arch-drift detective went dark.

   The shipped form loads the sibling by path off `Path(__file__).parent` under
   a module-private sentinel — touching no namespace and depending on no
   `sys.path` state — and registers it in `sys.modules` **before**
   `exec_module`, because `jsonl_records` defines `@dataclass` types and stdlib
   `dataclasses` resolves `cls.__module__` through `sys.modules` at
   class-creation time. See AC15.
2. `verifiers/common.py` — `from lib.jsonl_records import read_jsonl_records`
   via the existing `_SHARED_SCRIPTS` bootstrap already in that file. Discard
   `.corrupt` explicitly, with the G5 rationale restated at the call site.

**Tier B** — delegate via the plugin's existing pollution-free loader:

3. `change_history.py` — `from ._lib_loader import load_shared_lib` (sibling
   module in the same `collectors` package; already used by `test_links.py`,
   `_requirement_parse.py`, `_test_links_fold.py`). Update `_lib_loader`'s
   "the fixed set for THIS loader is three" comment to four, recording *why*
   `jsonl_records` is safe here (pure leaf, mutates no `sys.path`).
4. **New** `plugins/shipwright-compliance/scripts/audit/_events_read.py` (<300
   LOC) holding one `load_events(project_root)`. `group_b` and `group_d` both
   delegate to it. Uses `audit_adapters.load_shared_lib` per `_lib_loader`'s
   explicit instruction that audit-group shared modules belong there.

### Why a new module instead of consolidating into `audit_adapters.py`

`group_b._load_events` and `group_d._load_events` are today **byte-identical
duplicates**. Consolidating is the right fix, but `audit_adapters.py` sits at
349 LOC against a 349 baseline — adding to it **ratchets the bloat baseline and
the pre-commit hook blocks the commit**. A new small module removes the
duplicate, fixes the bug once, and *shrinks* both group files.

### Bloat-gate state (measured post-build, every touched file)

The `audit_adapters.py` / `group_b.py` zero-headroom finding drove the design
decision above, so it was genuinely measured before design. The table itself is
now regenerated from the **final** tree — it was wrong in two consecutive review
rounds while carrying a "verified" header, which is worse than carrying none.

| file | final LOC | baseline | state |
|---|---|---|---|
| `group_b.py` | 534 | **534** (was 545) | ratcheted DOWN |
| `group_d.py` | 449 | **449** (was 465) | ratcheted DOWN |
| `verifiers/common.py` | 768 | **768** (was 771) | ratcheted DOWN |
| `audit_adapters.py` | 349 | 349 (0 headroom) | untouched — the constraint that shaped the design |
| `boundary_coverage_report.py` | 640 | 640 | exactly at baseline, no ratchet |
| `events_log.py` | **300** | none (limit 300) | grew from 230 (by-path sentinel loader + rationale). **ZERO headroom — it is AT the cap.** The next added line mints a new Group-H crossing, so the next edit here must extract, not append. This row was wrong in three consecutive review rounds and the last time erred *permissively*; it is now measured, not recalled |
| `backfill_scan.py` | 247 | none (<300) | +~5 |
| `change_history.py` | 202 | none (<300) | +~14 |
| `_events_read.py` | 100 | none (new) | new module |
| `iterate_checks.py` | 1116 | **1116** (was 1121; `exception`, ADR-093) | ratcheted DOWN |
| `test_events_reader_record_boundary.py` | 220 | none (<300) | load-context cases split out to keep it under the cap |
| `test_events_log_load_contexts.py` | 219 | none (<300) | the AC15 module-load contract, split from the recovery tests; grew when the two hardening cases (per-copy digest key, missing-sibling `ImportError`) were added in round 5 |
| `test_iterate_checks_record_boundary.py` | 107 | none (new) | sites 9-11 |
| `test_boundary_coverage_event_log.py` | 58 | none (new) | site 8 cases. Split out at F6: appending them inline pushed `test_boundary_coverage_report.py` from 774 to 809 and the anti-ratchet pre-commit hook **BLOCKED the commit**. Resolved by extraction, not by bumping the baseline — the gate working exactly as designed |

The **four** ratchet-downs are a real outcome of this change: the shrink is
handed to the gate rather than kept as free headroom. (`iterate_checks.py` is an
ADR-093 exception entry; ratcheting its `current` tightens the anti-ratchet floor
without touching the documented exception itself.)

### Declined — inlining `_load_events = load_events`

The Stage-2 review flagged the alias in `group_b` / `group_d` as indirection with
no seam behind it: nothing patches either name, and the alias actually *removes*
a patch point, since patching `_events_read.load_events` no longer reaches either
group (both capture the object at import).

**Declined on scope, not on size.** The first rationale offered was that inlining
would pressure the bloat ceiling — that is wrong and the reviewer corrected it:
inlining touches 4 call sites and deletes 2 aliases plus ~6 comment lines, so it
makes both files *smaller*. The real reason is diff-minimisation inside a defect
repair governed by *behaviour-preserving except for record recovery*. Recorded
accurately because a wrong rationale in an ADR gets reused as precedent for a
case where it does not hold.

### Deliberate scope decision — sites 5/6 stay SILENT

The first draft had the shared `load_events` warn on an unrecoverable fragment,
mirroring `config.read_events` and site 4. **Dropped after external review.**
Both reviewers independently flagged it: the warning is not needed for record
recovery, and it is externally observable — it can contaminate audit output or
trip a fail-on-stderr CI step. Sites 5 and 6 are silent today and stay silent.

Reporting an unrecoverable fragment is still the right thing to do; it belongs
in the groups' own findings layer (a `Finding`, not a `warnings.warn` side
channel). Filed as follow-up under Out of scope.

### Alternative considered — duplicate `jsonl_records` into the compliance plugin

Rejected. See Probe 3: the loader already exists, is precedence-tested
(`test_lib_loader_precedence.py`), and is already used by `group_d`. Duplicating
a subtly-contracted parser to work around a barrier that a tested mechanism
already crosses would trade a real fix for a drift liability.

### Out of scope

- The adopt plugin's `_ends_without_newline` duplicate (#405) has **no parity
  test** pinning it to the shared leaf. Real, but a separate concern from the
  read sites — filed rather than folded in.
- **The remaining unconverted read sites** — tracked as triage `trg-360e494f`
  (exhaustive sweep, verified each
  actually parses the event log per physical line). Same defect class, same
  one-line remedy; held back because converting them spans four more plugins and
  their suites, which would make this diff unreviewable and risk the Tier-3
  review-truncation gate. Filed with exact locations so the next pass needs no
  rediscovery:
  - `plugins/shipwright-adopt/scripts/checks/validate_adoption.py:90`
  - `plugins/shipwright-grade/scripts/lib/routing.py:98`
  - `shared/scripts/lib/phase_quality/_resolution.py:170`
  - `shared/scripts/tools/verifiers/adopt_compliance.py:215`
  - `plugins/shipwright-run/scripts/lib/single_session/observability.py:100` —
    lowest priority of the five: it reads `.shipwright/run_loop_events.jsonl`, a
    DIFFERENT file that self-documents as "Telemetry, not authority"
  - *(`verifiers/iterate_checks.py` was on this list and has been PULLED IN as
    sites 9-11 — same package as site 3, same F11 consumer, and the inverted
    failure mode made deferring it indefensible)*
  - **Deliberately excluded:** `shared/scripts/tools/validate_event_log.py:47`
    is the *strict* validator — per-line strictness is its contract, and
    `verifiers/common.py` explicitly points callers needing strict validation at
    it. Converting it would erase the distinction it exists to draw.
- **`churn_merge.validate_events_text` false-negative** (`churn_merge.py:232`).
  It parses one physical line at a time, and AC7 pins that a concatenated line
  *does* reach `main`. If a run's `work_completed` is the SECOND record on such a
  line, `require_run_id` never matches → a false `check_events_has_commit`
  failure during `integrate_main`. It fails **closed** (the line is appended
  before the parse, so no data is lost), which is why it is filed rather than
  fixed here.
- **`finalized_run_ids` corrupt policy.** Should an unrecoverable fragment make
  ownership *undeterminable* (`None` → whole-set checking) rather than yielding a
  partial set? Both external reviewers argued yes; the pre-existing pinned
  contract says no. Genuinely open, but it is a policy question about a drift
  gate, not a record-loss defect — see "Reverted mid-build".
- **Audit groups have no native channel for reporting log corruption.** Group B
  and Group D swallow an unrecoverable fragment silently, and after this change
  they still do (governing invariant). The right fix is a `CheckResult`/finding
  in their own reporting layer — GPT's suggestion — not a `warnings.warn` side
  channel. Filed, not folded in.
- Any change to the writers or to `.gitattributes` union-merge semantics.

## Post-merge steps (NOT part of this PR)

This change is plugin-side (`shared/scripts/**`, `plugins/**`), so it does not
reach the runtime plugin cache on merge. After the PR is **merged and green**:

```bash
bash scripts/update-marketplace.sh
uv run scripts/check_plugin_cache_sync.py --strict
```

Deliberately deferred, not skipped. The marketplace clone tracks `origin/main`,
so running it from an unmerged iterate branch would either no-op or publish
unreviewed code. It also mutates ONE global directory
(`~/.claude/plugins/cache/shipwright/`) that a live Command-Center WebUI session
runs from, so it must be sequenced against any concurrent session rather than
fired mid-iterate.

## External plan review (GPT-5.4 + Gemini 3.1 Pro, 2/2 succeeded, not degraded)

**Accepted — changed the plan:**

1. **(MED, both) The new warnings at sites 5/6 are unnecessary risk.** GPT: they
   are "not necessary for record recovery itself" and may contaminate audit
   output; Gemini: CI may fail-on-stderr. Correct — dropped. Produced the
   *behaviour-preserving except for record recovery* invariant, which is a better
   governing rule than the case-by-case judgement I had. → AC5.
2. **(MED, GPT #4) Delegation changes behaviour for inputs beyond concatenation.**
   Investigated rather than assumed, and it found three real uncaught crashes.
   → AC8, and a decision to test them rather than leave them incidental.
3. **(MED, GPT #3) Import-mode risk for the new module.** → AC9 smoke test.
4. **(LOW, GPT #5) Keep the helper narrowly scoped** — path selection, parser
   invocation, absence/`OSError` mapping only; group-specific interpretation
   stays in the groups. Adopted.
5. **(LOW, GPT #6) Warnings must not echo raw event data.** `change_history`'s
   warning reports `len(frag.text)` and a line number, never the fragment text —
   matching `config.read_events`. Adopted.

**Adopted, then REVERTED during build:**

1. **(HIGH, both, convergent) `finalized_run_ids` corrupt policy → `None` on any
   fragment.** Implemented as specified, then reverted when the full suite went
   red: `test_arch_drift_event_scope.test_finalized_run_ids_skips_corrupt_lines`
   already pinned the opposite, and the function's docstring already documented
   "corrupt/blank skipped". Neither reviewer had that contract in context. It is
   a *policy* change rather than record recovery, so shipping it inside a defect
   repair would breach this iterate's governing invariant. Filed as follow-up.
   See "Reverted mid-build" above. **This is the one place the review round was
   followed and then unwound — recorded here so the review record stays true.**

**Verified and dismissed:**

1. **(MED, Gemini #3) "Add a `quiet=True` flag to the SSoT for AC3."** Not
   needed. `jsonl_records`' docstring states *"This module NEVER prints"*, and a
   grep for `print(`/`logging`/`warn` in it returns nothing. Discarding
   `.corrupt` fully satisfies AC3 without touching the shared signature — and
   widening an SSoT signature for a need that does not exist is the wrong trade.

**Rejected, with reasoning:**

1. **(HIGH, Gemini #1) "Discard `_events_read.py`; consolidate into
   `audit_adapters.py` and edit the baseline or golf lines to make room."**
   Rejected on three grounds:
   - `audit_adapters.py` is `state: grandfathered` — *already over* the 300-line
     limit. Gemini's remedy is to make an over-limit file further over-limit,
     which is precisely the ratchet the anti-ratchet gate exists to block; the
     pre-commit hook blocks that commit. It is not "an arbitrary line-count
     linter" being dodged, it is the gate working as designed.
   - Extracting a cohesive cluster into a new sub-300 module is this repo's
     **documented, sanctioned** remedy for exactly this situation, not a
     workaround invented here.
   - On semantics, `audit_adapters.py` is about *crossing the cross-package
     import boundary*. Event-log read policy is a different concern; putting it
     there is the weaker semantic home, not the stronger one.
   The finding is still partly right, and the plan absorbs that: the module is
   justified primarily as **deduplicating two byte-identical functions**, with
   bloat headroom as a secondary constraint — not the reverse.

## Confidence Calibration

- **Boundaries touched:** the `shipwright_events.jsonl` append-only log (read
  side, 11 sites: 6 briefed across 2 import tiers, 2 found by code review, and
  3 more in the verifier package — one of which the review did not name either);
  the ADR-045 cross-plugin import boundary; the module-load boundary (AC15).
- **Empirical probes run:**
  - All 6 BRIEFED sites reproduced at 0/2 recovery on a union-merge-shaped line;
    sites 7 and 8 (found by Stage-2 review) reproduce identically; the
    #405 reference reader recovers 2/2 on the identical input.
  - Sites 9-11 (`iterate_checks`): 6 of 9 new cases fail pre-fix — including the
    F11 oracle case (a `work_completed` second on a concatenated line read as
    absent, so F11 would fail a correctly-recorded run) and an `AttributeError`
    crash on a bare scalar line. The anti-vacuity case (an absent event must
    still read as absent) passes both before and after, by design.
  - Both `events_log` hardening behaviours verified by removing them: with the
    digest key and `.is_file()` guard stripped, the two dedicated cases fail.
  - ADR-045 barrier confirmed for the *compliance* plugin (was only verified for
    *adopt*): bare `from lib import jsonl_records` → `ImportError`.
  - Both compliance loaders resolve `jsonl_records` to the real shared file and
    recover 2/2, with the plugin-local `lib` intact afterwards → duplication
    unnecessary.
  - `change_history` additionally emits `ResourceWarning: unclosed file` — an
    unreported second defect at that site.
  - Bloat headroom measured before choosing the Tier B shape; `audit_adapters.py`
    and `group_b.py` both sit at **zero** headroom, which ruled out the
    otherwise-obvious consolidation target.
- **Test Completeness Ledger:** see `iterate_latest.test_completeness` in
  `shipwright_test_results.json`; 0 untested-testable. Count is re-derived at F5
  rather than carried forward from an earlier draft.
- **Confidence-pattern check:**
  - *Asymptote (depth):* the fix is a delegation to an already-proven leaf, so
    depth risk is concentrated not in the parser but in **preserving each call
    site's local contract** — G5 silence + literal path (AC3), fail-open `None`
    (AC2/AC5), partial recovery (AC6). Each is pinned by its own test.
  - *Coverage (breadth):* **the enumeration was NOT exhaustive, and that is the
    headline finding.** The brief named six sites; Stage-2 review found a 7th and
    8th and pointed at the verifier package; a final exhaustive sweep found the
    rest. Five remain, filed as `trg-360e494f`.
    Eleven ship here, each with a recovery test, both import tiers exercised —
    but breadth is explicitly INCOMPLETE by decision, not by belief. Anyone
    reading this section to calibrate trust in the sweep should read it as:
    the compliance/verifier/traceability path is covered, the class is not
    closed.
  - *Integration composition (`cross_component`):* AC7 drives a real
    `merge=union` merge of two divergent branches end-to-end into the shared and
    compliance readers. It pins the mechanism in BOTH directions — that git does
    **not** create the concatenation, and that it **propagates** an existing one
    into the merged tree. The components are proven to compose, not merely to
    pass in isolation.
