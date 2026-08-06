# Iterate: hand the Stop audit the iterate's own run_id

- **Run ID:** `iterate-2026-08-06-resolve-run-id-seam`
- **Type:** BUG
- **Complexity:** medium
- **Risk flags:** `touches_io_boundary`
- **Affected FRs:** none
- **Spec Impact:** NONE — this repairs a resolution seam so five already-specified
  spec checks evaluate the run they were written for. No check's contract changes.
- **Status:** in progress

## Problem

`resolve_run_id` (`shared/scripts/lib/phase_quality/_resolution.py`) is the sole
supplier of `run_id` to both Stop-time audits (`audit_phase_quality_on_stop.py`,
`audit_compliance_on_stop.py`). It resolves in priority order:

1. `shipwright_run_config.json` top-level `run_id`
2. the latest `run_started` event in `shipwright_events.jsonl`
3. `SHIPWRIGHT_LOOP_ID` (+ `SHIPWRIGHT_LOOP_UNIT_ID`)
4. the raw session id, else the literal `"unknown"`

**For an iterate, none of the first three is ever populated.** The canonical id
lives in the per-run ledger under `.shipwright/agent_docs/iterates/` and in
`shipwright_test_results.json::iterate_latest.run_id`; run_config carries no
top-level `run_id`, and no producer emits a `run_started` event — every file
matching that string is a reader.

So the audit is handed either the raw **session UUID** (when
`SHIPWRIGHT_SESSION_ID` reaches the hook) or the sentinel `"unknown"` (when it
does not). Neither is an `iterate_history` key, so
`_iterate_run_id.has_exact_iterate_entry` is `False` and **every spec check
gated by `unresolvable_run_id_skip` — S2, S3, W2, S9, S10 — SKIPs on every real
invocation.** The family is inert in production.

The guard is correct and stays: without it, S9/S10 inherited an unrelated run's
category and decided their verdict from it (fixed by
`iterate-2026-08-06-s9-s10-sentinel-guard`). The defect is upstream of the
guard, in the seam that should hand the audit the run it is auditing.

### Root-cause evidence (reproduced live, before any fix)

Probed from both roots the Stop hook can resolve, session
`1ce34d44-0ee1-4c91-871e-d2d52fea7247`:

| audit root | `resolve_run_id` → | sentinel? | `has_exact_iterate_entry` |
|---|---|---|---|
| this run's worktree | `'1ce34d44-0ee1-4c91-871e-d2d52fea7247'` | no | **False** |
| the main repo root | `'1ce34d44-0ee1-4c91-871e-d2d52fea7247'` | no | **False** |

This refines the reported premise in one respect worth recording: with the
session env var set the resolved id is the **session UUID, not `"unknown"`**.
The SKIP is identical either way (both fail `has_exact_iterate_entry`), but only
the blank-env case produces the `iterate-unknown-unknown.json` snapshot cited as
evidence. It also means the finding is *not* always filtered by the read-time
sentinel rollup filter — a session-UUID run_id is not a sentinel.

## Decision

**Add the per-session iterate run pointer as the highest-priority source.**

`setup_iterate_worktree.py` already writes
`<main_root>/.shipwright/iterate_active/<session_id>.json` at B1a — before any
build work, for every iterate, unconditionally — carrying `run_id`, `slug`,
`branch`, `worktree_path`, `main_root` and `session_id`. It is read back by the
existing SSoT reader `worktree_isolation.read_run_pointer(main_root,
session_id)`. That artifact is keyed by exactly the value the Stop hook already
holds, so it is the most specific evidence available about *which run this
session is executing* — strictly more specific than the three project-global
sources below it. Hence priority 0, not a new tail.

The pointer lives in the **main** tree while an iterate's cwd is its worktree,
so the lookup resolves the main root first via `repo_root.main_repo_root_or`,
which returns `project_root` unchanged when the project is not a worktree and on
any git failure. One code path therefore covers the worktree case, the plain-
checkout case and the non-git case.

Rejected alternative: **emit a `run_started` event** so priority 2 works as
designed. It revives the intended chain, but `shipwright_events.jsonl` is a
tracked, PR-committed log — a new event type ripples into the FR-gate
classifier, event-schema validators and the compliance readers, and it needs a
new producer wired into the skill (hence a plugin-cache re-sync). The pointer is
an existing, gitignored, self-pruning artifact with a published reader. Far less
surface for the same result.

Rejected alternative: **read `SHIPWRIGHT_RUN_ID`.** `docs/hooks-and-pipeline.md`
records why that id is untrustworthy — it is set with assign-only-if-unset in
build/test/changelog, so a phase inherits an earlier phase's id, and a
hook-launched subprocess never inherits the skill's shell export at all.

### Scope of the repair — measured, not assumed

An early draft of this spec claimed the five checks "go live when the audit's
`project_root` is the run's own worktree, which is the normal case". Stage 2
review challenged that as unverified, so it was **measured** — the real
`audit_phase_quality_on_stop.py` was executed against this run:

```
[phase-quality] run=iterate-2026-08-06-resolve-run-id-seam audited 2 phase(s)
S2 SKIP | run_id=iterate-2026-08-06-resolve-run-id-seam is not a resolvable
          iterate run (no exact iterate_history entry, no matching file)
S3, W2, S9, S10 — same
```

The claim was **wrong in its second half**. What the change delivers, proven:

- **`run_id` is now the canonical one in production.** The hook reports
  `run=iterate-2026-08-06-resolve-run-id-seam`; before, the same invocation
  reported the raw session UUID (and the only prior iterate snapshot on disk,
  `iterate-unknown-unknown.json`, reported `unknown`). Per-run finding JSONs are
  keyed by it, `audit_compliance_on_stop` labels its triage cards with it, and a
  SKIP now names the run instead of a meaningless id.
- **The five checks do not thereby evaluate.** They additionally need the
  audited tree to hold the run's own `iterates/<run_id>.json`, which F5c writes
  into the **worktree** — while the Stop hook resolves `project_root` from the
  session's cwd, which is the **main repo**. So an in-flight run still SKIPs.
  It evaluates where the entry is present: an audit rooted in the worktree
  (pinned by AC-7), or the main root once the PR has merged.

That residual is fail-safe — a SKIP, never a false FAIL — and out of scope
here; it is a question of where the ledger lives, not of run-id resolution. Two
follow-ups are filed rather than silently absorbed: **trg-276994a4** (a worktree
retained after its PR merges keeps a pointer looking live) and **trg-b36fd844**
(`already_audited` keys on `(phase, run_id, session_id)`, so a run's verdicts
can be frozen at the first Stop, before its ledger entry exists).

## Acceptance Criteria

- **AC-1:** Given a run pointer on disk for the audited session, when
  `resolve_run_id` runs, then it returns the pointer's `run_id` — in preference
  to a top-level run-config `run_id`, a `run_started` event, and the loop vars.
- **AC-2:** Given the audited `project_root` is a linked worktree whose pointer
  lives in the main tree, when `resolve_run_id` runs, then it still resolves the
  pointer (main-root resolution), and it behaves identically for a plain
  checkout and for a non-git directory.
- **AC-3:** Given no pointer for the session, when `resolve_run_id` runs, then
  the existing four-step chain is byte-for-byte unchanged, including the
  `"unknown"` sentinel tail.
- **AC-4:** Given a sentinel session id (`""` / `"unknown"`), when
  `resolve_run_id` runs, then no pointer lookup is attempted, so a degenerate
  `unknown.json` can never bind a run.
- **AC-5:** Given an unreadable, malformed, non-object or `run_id`-less pointer,
  when `resolve_run_id` runs, then it falls through to the existing chain rather
  than raising — the Stop hook must never be broken by a bad pointer.
- **AC-5b (value validation):** Given a pointer whose `run_id` is present but not
  a usable string — `null`, a number, a list, whitespace-only, `""`, or the
  sentinel `"unknown"` — when `resolve_run_id` runs, then the pointer is rejected
  and the existing chain proceeds. `resolve_run_id`'s non-empty-string contract
  cannot be violated by pointer contents.
- **AC-6 (round-trip):** Given `write_run_pointer` writes a pointer, when
  `resolve_run_id` reads it back for that session, then the run_id survives the
  producer→consumer round trip unchanged — including for a **session id whose
  characters `sanitize_run_id_for_filename` rewrites**, which is the value the
  pointer *filename* is derived from. The `run_id` is a payload value and is
  never transformed.
- **AC-9 (session identity):** Given a pointer file whose payload `session_id`
  is not the session being audited — a sanitiser filename collision, or a
  hand-edited/stale file — when `resolve_run_id` runs, then the pointer is
  rejected and the existing chain proceeds.
- **AC-7 (integration composition):** Given a real git worktree, a pointer
  written by the real producer and the run's own ledger entry on disk, when the
  composed seam runs — `resolve_run_id` → `unresolvable_run_id_skip` → S9/S10 —
  then the checks no longer SKIP and evaluate *this* run's category.
- **AC-8:** The documentation of record is corrected in the same diff: the S9/S10
  rows and the sentinel-exclusion note in `docs/hooks-and-pipeline.md`, the
  `_iterate_run_id.py` module docstring, and the tripwire test's own docstring —
  each currently asserts that the chain is inert.
- **AC-10:** All five affected checks — S2, S3, W2, S9, S10 — are proven to route
  through `unresolvable_run_id_skip`, so "the seam repairs five checks" is
  asserted rather than inferred from naming.
- **AC-11 (liveness):** Given a pointer whose `worktree_path` is missing, blank,
  non-string, deleted, or a file rather than a directory, when `resolve_run_id`
  runs, then the pointer is rejected and the existing chain proceeds — so an
  orphaned pointer cannot bind a finished run to later work in the same session.
  A pointer whose worktree is live still resolves, so the guard cannot silently
  disable priority 0.

## External plan review — findings addressed

Branch A (`openrouter`: openai `revise`, deepseek `approve`; no contradiction).
Six findings, all accepted; four required facts, established before coding:

1. **Lifecycle/identity contract (medium).** Confirmed same source at both ends:
   `setup_iterate_worktree.py` defaults `--session-id` to `$SHIPWRIGHT_SESSION_ID`,
   and `audit_phase_quality_on_stop.py` reads the same variable. One asymmetry —
   the hook `.strip()`s, the producer does not — so both sides are normalised
   before comparison here. **Pruning cannot race Stop:**
   `prune_stale_run_pointers` has exactly two callers, both inside
   `setup_iterate_worktree.py`, and it only unlinks pointers whose
   `worktree_path` is not a directory; a live run's worktree exists, so a
   concurrent iterate's setup can never delete this run's pointer. Covered by
   AC-9 and the AC-7 composed-seam test.
2. **Pointer `run_id` value validation (medium).** Accepted → **AC-5b**.
3. **Session-keyed filename vs run_id payload (medium).** Correct: AC-6 as
   originally written described the wrong sanitiser subject. Rewritten, and
   payload-session verification added as **AC-9**.
4. **Other `resolve_run_id` callers (low).** Exhaustive sweep (direct calls,
   attribute access, string literals, `getattr`, `__all__` re-exports):
   **exactly two production callers** — `audit_phase_quality_on_stop.py:115` and
   `audit_compliance_on_stop.py:219`. `stamp_test_results._resolve_run_id` is an
   unrelated private function with its own signature, not a caller;
   `handoff_phase_canon.py` only mentions it in prose, and C3 deliberately takes
   no run id at all. No dashboards or telemetry consume it.
5. **Local pointer integrity at priority 0 (low).** Mitigated in depth: the
   pointer is accepted only after structural validation (payload session match +
   non-empty non-sentinel string `run_id`), no field other than `run_id` is used,
   and the resolved id stays data-only. Path safety is already independently
   enforced downstream — `_findings.finding_filename` runs `_sanitize_filename`
   (`[^A-Za-z0-9._-]+` → `-`) over the run_id before it reaches a path, so a
   traversal string in a pointer cannot escape `FINDING_DIR`. A local process
   able to write this directory can already write the audit output directly.
6. **Prove all five checks, not two (low).** Accepted → **AC-10**.

## Stage 2 code review — findings addressed

`REQUEST_CHANGES`, 9 findings, all accepted or answered with evidence:

1. **(medium) Headline claim unverified through the production path.** Correct,
   and it was wrong — see "Scope of the repair" above. The docs of record, the
   `_run_id` docstring and the `_iterate_run_id` docstring now claim only what
   the probe proves. The `already_audited` half is filed as **trg-b36fd844**.
2. **(medium) `RecursionError` / `ImportError` could still escape post-claim.**
   Both closed: `RecursionError` added to the caught tuple (matching
   `lib/jsonl_records`), and the two function-local imports promoted to
   module-level *module* imports — so a packaging fault can no longer surface
   after the claim is burned, while `monkeypatch.setattr(worktree_isolation,
   ...)` keeps working. The 2.7 ms rationale for deferring them was too weak
   against that failure mode; it is now a comment explaining the opposite choice.
3. **(medium) A stale pointer could attribute later work to a finished run.**
   Accepted → **AC-11**. Implemented as a `worktree_path` liveness predicate
   matching the sibling consumer `iterate_stop_finalize`. The reviewer's
   stronger form — require `project_root` to be the pointer's worktree — was
   **rejected with reason**: production audits from the main root, so it would
   reject the very case that carries the delivered benefit. Residual staleness
   (worktree retained post-merge) is filed as **trg-276994a4**.
4. **(low-medium) The run-config branch has the same escape.** Fixed:
   `except (ValueError, OSError, RecursionError)`.
5. **(low) Two extra `git rev-parse` per Stop.** Accepted as-is; a comment now
   records that the call is unconditional and why (only git can locate the main
   tree from a linked worktree).
6. **(low) Module map stale.** Fixed in `phase_quality/__init__.py` and
   `_resolution.py`'s summary line.
7. **(low) Duplicated `would_warn` / `_history` fixtures.** **Not taken.**
   Hoisting them into `shared/tests/conftest.py` would put a change under a
   conftest shared by ~8 200 tests to save ~22 LOC in two files. The regression
   surface is not worth it in this diff.
8. **(low) Tombstone comment in the removed allowlist entry.** Fixed — deleted;
   `test_allowlist_entries_are_not_stale` already prevents the rot it warned of.
9. **(low) Undocumented tail behaviour change.** Documented in the
   `resolve_run_id` docstring (whitespace-only `session_id` → `"unknown"`;
   unreachable from either production caller).

## Affected Boundaries

| Producer | Format | Consumer | Probe |
|---|---|---|---|
| `worktree_isolation.write_run_pointer` (B1a) | `iterate_active/<session>.json` | `resolve_run_id` (this change) | AC-6 round-trip test |
| `resolve_run_id` | `run_id` string | `unresolvable_run_id_skip` → S2/S3/W2/S9/S10 | AC-7 composed-seam test |
| `resolve_run_id` | `run_id` string | `audit_compliance_on_stop` finding labels | reviewed: label-only, strict improvement |
| `main_repo_root_or` | main-tree `Path` | pointer lookup | AC-2 worktree / checkout / non-git cases |

## Verification

- **Surface:** CLI (Python) — no UI, no HTTP surface in this diff
- **Runner:** targeted pytest over `shared/tests`, then the full F0 suite
- **Evidence path:** `.shipwright/runs/iterate-2026-08-06-resolve-run-id-seam/surface_verification.log`

## External code review — findings addressed

Branch A, `--mode code` (openai `revise`, deepseek `revise`; no contradiction).
Run because Stage 3 could not (below), so the diff still got an adversarial
pass from an independent provider.

1. **(medium) `str()` coercion on the payload `session_id`.** REAL and fixed: a
   non-string payload could bind whenever its repr matched the audited id
   (`42` vs `"42"`, `true` vs `"True"`). Now `isinstance`-guarded, pinned by
   `test_a_non_string_session_cannot_bind_via_its_repr`, which constructs
   payloads whose repr genuinely equals the audited id — the pre-existing `42`
   case passed either way and did not pin the guard.
2. **(medium) `run_id.strip()` transforms the payload vs AC-6's "unchanged".**
   Accepted as a wording defect, not a code defect: normalising is deliberate
   because the resolved id becomes an audit *key* (finding filenames, the
   `already_audited` triple, triage labels), so a padded copy would key the same
   run twice. AC-6 and the code comment now say so explicitly.
3. **(low) No named non-git-directory test for AC-2.** Fixed —
   `test_a_non_git_directory_resolves_its_own_pointer`. It was covered
   incidentally by every `tmp_path` test; now it is asserted on purpose.
4. **(low) No explicit test for the whitespace-session tail change.** Fixed —
   `test_a_whitespace_only_session_resolves_to_the_unknown_sentinel`.
5. **(medium, deepseek) `" unknown "` bypasses the sentinel check then returns
   `"unknown"`.** **FALSE POSITIVE** — verified, not assumed:
   `_constants.is_sentinel_run` strips *and* lower-cases internally, so
   `is_sentinel_run(" unknown ") is True`. The reviewer said outright that the
   definition was not in the diff. Already covered by the passing
   `run-id-whitespace` / `run-id-sentinel` parametrizations.
6. **(low, deepseek) `is_sentinel_run("UNKNOWN")` may not be case-insensitive,
   so the `"UNKNOWN"` test case may fail.** **FALSE POSITIVE**, same root cause
   — it is case-insensitive, and that parametrization passes. No change made;
   "fixing" either would have been a change made to satisfy a mis-read.

## Confidence Calibration

- **Boundaries touched:** `write_run_pointer` (B1a) → `pointer_run_id`;
  `resolve_run_id` → `unresolvable_run_id_skip` → S2/S3/W2/S9/S10;
  `resolve_run_id` → `audit_compliance_on_stop` finding labels;
  `main_repo_root_or` → main-tree location from a linked worktree;
  `events_log.resolve_events_path` (replacing a raw join).

- **Empirical probes run:**
  - *Root cause, before any fix:* `resolve_run_id` probed from both the
    worktree and the main root returned the session UUID, `has_exact_iterate_entry`
    `False` in both. Refined the reported premise — the resolved id is the
    session UUID when the env var is set, not `"unknown"`.
  - *After the fix:* both roots return `iterate-2026-08-06-resolve-run-id-seam`.
  - *Production path (the decisive one):* ran the real
    `audit_phase_quality_on_stop.py`. It reported
    `run=iterate-2026-08-06-resolve-run-id-seam` and wrote a finding JSON keyed
    by it — **and S2/S3/W2/S9/S10 still SKIPped**, which disproved the draft
    spec's second claim and forced the rewrite above. This is the probe that
    changed the deliverable rather than confirming it.
  - *Import-cost measurement:* +2.7 ms on a 61 ms package import for the two new
    deps — used first to justify lazy imports, then overridden by Stage 2's
    post-claim-`ImportError` argument.
  - *`is_sentinel_run` behaviour:* executed against 6 inputs to falsify two
    external findings rather than act on them.
  - *ADR-045 exposure:* confirmed no plugin `lib/` carries **any** of the five
    eagerly-imported modules, so the new imports bind exactly as the three
    pre-existing ones; falsified empirically by running the two plugin roots
    that import `phase_quality` — `shipwright-run` 542 passed,
    `shipwright-compliance` 1628 passed.
  - *Bloat:* every touched file measured; `_resolution.py` 300 → 247,
    `handoff_phase_canon.py` 298 → 299, all new files ≤ 299.

- **Test Completeness Ledger** — every behavior this diff introduces, each
  `tested` with cited evidence. 0 testable-but-untested.

  | # | Behavior | Disposition | Evidence |
  |---|---|---|---|
  | 1 | Pointer outranks run-config, `run_started` and loop vars | tested | `test_pointer_outranks_every_lower_priority_source` |
  | 2 | Chain unchanged with no pointer (4 tails) | tested | `test_run_config_still_wins…`, `…run_started_event…`, `…loop_vars…`, `…tails_are_unchanged` |
  | 3 | Sentinel session performs no disk lookup | tested | `test_sentinel_session_attempts_no_pointer_lookup` (spies the reader; 4 params) |
  | 4 | Structurally invalid pointer falls through | tested | `test_structurally_invalid_pointer_falls_through_to_the_chain` (11 params) |
  | 5 | Malformed / invalid-UTF-8 / unreadable pointer never raises | tested | `test_malformed_json_pointer_falls_through`, `test_invalid_utf8_pointer_cannot_escape_the_resolver`, `test_unreadable_pointer_falls_through` |
  | 6 | Fail-open stays narrow (a real bug still propagates) | tested | `test_a_programming_error_is_not_swallowed` |
  | 7 | Payload session identity required, `isinstance`-guarded | tested | `test_pointer_naming_another_session_is_rejected` (5), `test_a_non_string_session_cannot_bind_via_its_repr` (3) |
  | 8 | Session identity compared after normalisation | tested | `test_session_identity_is_compared_after_normalisation` |
  | 9 | Producer→consumer round trip incl. sanitiser-rewritten session ids | tested | `test_round_trip_through_the_real_producer` (4 params, real `write_run_pointer`) |
  | 10 | Worktree liveness required (AC-11) | tested | `test_pointer_without_a_usable_worktree_path_is_rejected` (4), `…worktree_was_removed…`, `…file_at_the_worktree_path…`, `test_a_live_worktree_still_resolves` |
  | 11 | Worktree audit crosses to the main tree | tested | `test_a_worktree_audit_resolves_the_pointer_from_the_main_tree` (real `git worktree add`) |
  | 12 | Plain checkout + non-git roots resolve | tested | `test_a_plain_checkout_audit_resolves_its_own_pointer`, `test_a_non_git_directory_resolves_its_own_pointer` |
  | 13 | **Composed seam: producer→resolver→guard→S9/S10 stop skipping** | tested (`category: integration`) | `test_s9_and_s10_stop_skipping_once_the_seam_is_repaired` |
  | 14 | Main-root audit still SKIPs pre-merge (the honest boundary) | tested | `test_the_main_root_audit_still_skips_before_the_run_merges` |
  | 15 | All five checks route through the shared guard | tested | `test_every_affected_check_is_gated_by_the_shared_run_id_guard` (5 params, spy per module) |
  | 16 | Whitespace-only session → `"unknown"` tail | tested | `test_a_whitespace_only_session_resolves_to_the_unknown_sentinel` |
  | 17 | Guard still SKIPs when no pointer names the session | tested | `test_the_seam_still_skips_when_no_run_pointer_names_the_session` |
  | 18 | Events-log join goes through the SSoT; allowlist entry retired | tested | `test_no_unaccounted_raw_event_log_joins`, `test_allowlist_entries_are_not_stale` |

- **Confidence-pattern check:**
  - *Depth (asymptote):* the failure modes are enumerated from the actual
    contract of `read_run_pointer` — read verbatim rather than assumed — which
    is how the `UnicodeDecodeError` escape was found; and from two review
    rounds that added `RecursionError`, the `isinstance` session guard and the
    liveness predicate. New probes stopped producing new failure classes.
  - *Breadth (coverage):* 83 targeted tests, the full `shared/tests` root
    (8 193 passed), two plugin roots (542 + 1 628), ruff clean.
  - *Integration composition:* behavior 13 runs the real producer, a real
    `git worktree add`, the real resolver, the real guard and the real checks in
    one test. `cross_component` does **not** fire on this diff (no
    `hooks/*.py`, no `hooks.json`), so `check_integration_coverage` will
    green-skip; the behavior is recorded as `integration` regardless, because
    the risk it covers is real even where the flag does not reach.
  - *What is NOT claimed:* that the five checks now evaluate in production.
    Measured, and they do not — see "Scope of the repair".

## Out of Scope

- Moving or duplicating the per-run iterate ledger so a main-root audit can see
  an unmerged run. That is a separate storage decision.
- Emitting `run_started` events (rejected above); priority 2 stays dormant.
- Any change to the five checks' own logic, or to `unresolvable_run_id_skip`.
