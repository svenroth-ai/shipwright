# Mini-Plan: hand the Stop audit the iterate's own run_id

- **Run ID:** `iterate-2026-08-06-resolve-run-id-seam`
- **Complexity:** medium · **Type:** BUG

## Chosen approach — pointer as priority 0 inside `resolve_run_id`

Add one new highest-priority source to `resolve_run_id`: the per-session iterate
run pointer that `setup_iterate_worktree.py` already writes at B1a.

```
resolve_run_id(project_root, session_id)
  0. NEW  iterate run pointer for THIS session   <- most specific evidence
  1.      run_config top-level run_id
  2.      latest run_started event
  3.      SHIPWRIGHT_LOOP_ID (+ _UNIT_ID)
  4.      session_id, else "unknown"
```

### Steps

1. **Failing tests first** (`shared/tests/test_resolve_run_id_pointer_seam.py`,
   new): pointer wins over all three lower sources (AC-1); worktree / plain
   checkout / non-git roots (AC-2); no-pointer chain unchanged (AC-3); sentinel
   session id short-circuits (AC-4); unreadable / malformed / **non-object** /
   `run_id`-less pointer falls through (AC-5); every invalid `run_id` *value* —
   `null`, number, list, `""`, whitespace, `"unknown"` (AC-5b); producer→consumer
   round trip driven by a **session id that `sanitize_run_id_for_filename`
   rewrites** — the value the pointer *filename* is derived from — asserting the
   payload `run_id` returns untransformed (AC-6); payload `session_id` mismatch
   rejected (AC-9); composed seam over a real git worktree → S9/S10 stop skipping
   (AC-7); all five checks routed through `unresolvable_run_id_skip` (AC-10).
2. **Implement** `pointer_run_id(project_root, session_id)` and call it first
   from `resolve_run_id`. Lazy-import `lib.repo_root` + `lib.worktree_isolation`
   inside the helper.

   **Both land in a new `shared/scripts/lib/phase_quality/_run_id.py`, not in
   `_resolution.py`.** `_resolution.py` sits at *exactly* the 300-line source
   cap and is not grandfathered in `shipwright_bloat_baseline.json`, so
   implementing in place would open a new bloat crossing (~355 lines). Moving
   `resolve_run_id` and its new helper into their own module leaves
   `_resolution.py` at 247 and the new file at ~165 — the same split the package
   already used for `_engagement.py`, and the concern is genuinely distinct
   (run-id resolution vs. project/phase resolution). `_resolution.py`
   re-exports `resolve_run_id`, so `phase_quality.resolve_run_id` — the symbol
   every AC and both production callers name — is untouched. For the same
   reason the tests land in two files rather than one.

   Explicit contract, in order: normalise the session id **once** (`.strip()`)
   and reuse that one value for sentinel detection, filename lookup and payload
   comparison; return `None` for a sentinel session before touching the disk;
   accept a pointer only when it is a `dict`, its normalised payload
   `session_id` equals the audited one, and its `run_id` is a `str` whose
   stripped value is non-empty and not `"unknown"`. Return that stripped value.
   No pointer field other than `run_id` is consumed.

### `read_run_pointer`'s actual failure contract (verified, not assumed)

It catches `json.JSONDecodeError` and `OSError` → `None`. It does **not**:

- guard the decoded value's *shape* — valid non-object JSON (`[1,2]`, `"x"`)
  is returned as-is, and `null` decodes to `None`;
- catch `UnicodeDecodeError` from `read_text(encoding="utf-8")` — that is a
  `ValueError` subclass, so **invalid UTF-8 bytes in a pointer file raise
  straight through it**.

That second one matters more than it looks. `resolve_run_id` is called in
`audit_phase_quality_on_stop.py` *outside* the per-phase `try` and *after* the
once-per-Stop claim is taken — precisely the shape `resolve_run_id`'s own
docstring records for the `isinstance(data, dict)` bug: the raise killed the
audit for every phase, and the sibling fan-out invocations then no-oped on the
burned claim. So `_pointer_run_id` puts a narrow boundary — `OSError`,
`ValueError` (covers `UnicodeDecodeError` + `JSONDecodeError`) — around
main-root resolution and the pointer read, and carries the `isinstance(..., dict)`
check itself. Not a blanket `except Exception`: a programming error in the
imported helpers must still surface.
3. **Correct the documentation of record** (AC-8): the S9/S10 rows and the
   sentinel-exclusion paragraph in `docs/hooks-and-pipeline.md`; the
   `_iterate_run_id.py` module docstring; the tripwire docstrings in
   `shared/tests/test_spec_checks_run_id_guard.py`.
4. Review cascade, F0 suite, finalization.

### Why lazy imports

`_resolution.py` is imported by every Stop-hook fan-out invocation (~11 per
Stop; 10 return at the plugin-root gate without ever resolving a run id).
Measured incremental module cost of the two new deps is **2.7 ms on a 61 ms
baseline** — ~30 ms per Stop if paid eagerly, versus once when a lookup actually
happens. `_iterate_run_id.has_exact_iterate_entry` already establishes the
lazy-import precedent in this subsystem. Binding is unaffected: `_resolution.py`
already imports `lib.project_root` / `lib.events_log` eagerly, so `lib` is
bound identically either way (ADR-045 exposure unchanged).

### Failure posture

Every new step is fail-open into the existing chain: a missing, unreadable,
malformed, non-object or `run_id`-less pointer, and any git failure during
main-root resolution, all fall through to today's behaviour. The Stop hook is
observability and must never be broken by this lookup.

## Alternative considered — emit a `run_started` event

Make priority 2 work as designed by having the iterate emit a `run_started`
event at C/B1a.

**Rejected.** `shipwright_events.jsonl` is a tracked, PR-committed log, so a new
event type ripples into the FR-gate classifier, the event-schema validators and
the compliance readers, and it needs a new producer wired into `SKILL.md` (hence
a plugin-cache re-sync before it reaches runtime). The pointer is an existing,
gitignored, self-pruning artifact with a published SSoT reader and no commit
ripple. Same outcome, far less surface.

Second alternative — read `SHIPWRIGHT_RUN_ID` — is rejected on the record
already in `docs/hooks-and-pipeline.md`: assign-only-if-unset makes a phase
inherit an earlier phase's id, and a hook-launched subprocess never inherits the
skill's shell export.

## Blast radius

- `audit_phase_quality_on_stop` — S2/S3/W2/S9/S10 go live when the audit root is
  the run's own worktree. Only S2 is Tier-1 FAIL-capable, and only for a medium+
  iterate genuinely missing its spec file: the check working as designed.
- `audit_compliance_on_stop` — `run_id` is a finding *label* there. Cards become
  attributable to the canonical run instead of a session UUID. Strict improvement.
- No change when no pointer exists, so pipeline projects and non-iterate
  sessions are untouched.

## Two review suggestions deliberately NOT taken

**Validating the pointer's `worktree_path` against the audited root.** Suggested
to distinguish a current pointer from a reused-session one. Rejected: it would
*narrow* the repair. The audit legitimately runs with `project_root` = the main
root (that is how `audit_compliance_on_stop` labels findings), where
`worktree_path` necessarily differs from the audited root, so the check would
reject exactly the case it is meant to protect. The residual risk it targets is
already bounded: `write_run_pointer` keys the file by session id, so a reused
session id **overwrites** rather than accumulates — a stale pointer for a live
session id cannot exist. What remains is one session running an iterate and then
unrelated work under the same id, where attributing the audit to that iterate is
still the best available answer and strictly better than a session UUID.

**Changing the producer to normalise its session id.** The producer stores the
id as given; the hook strips it. If a padded id ever reached the producer, the
filenames would differ and the consumer would simply not find the pointer —
falling through to today's chain. That is fail-safe, so it does not justify
touching `setup_iterate_worktree.py`, which sits on the leak-guard's critical
path. Recorded here rather than silently skipped.
