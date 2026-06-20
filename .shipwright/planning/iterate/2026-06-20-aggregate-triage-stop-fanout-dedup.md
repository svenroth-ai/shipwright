# Iterate: aggregate_triage Stop-hook fan-out dedup

- **Run ID:** `iterate-2026-06-20-aggregate-triage-stop-fanout-dedup`
- **Intent:** CHANGE (Path B) · **Complexity:** medium (risk floor `cross_component`)
- **Spec Impact:** NONE (behavior-preserving observability optimization; no FR change)
- **Risk flags:** `cross_component` (edits `shared/scripts/hooks/aggregate_triage_on_stop.py`,
  `(^|/)hooks/.+\.py$`) → integration coverage + full test suite + full review

## Problem (verified, not assumed)

Follow-up to `iterate-2026-06-20-bloat-gate-stop-fanout-dedup`. The bloat-gate
fix prompted an audit of the other un-guarded shared Stop hooks. Per-hook
finding (by reading + running each):

- `plugin_sync_reminder_on_stop` — already dedups (atomic `O_EXCL` sentinel) ✓
- `write_terminal_marker` — genuinely convergent (no-op in normal sessions;
  idempotent empty-file write) ✓
- `audit_compliance_on_stop` — `(sha,session)` marker dedups under serial Stop
  execution; only a theoretical parallel race. Deferred (lower value).
- **`aggregate_triage_on_stop` — the real gap:** NO dedup at all. It
  unconditionally calls `aggregate_triage.main` (regenerates the gitignored
  `triage_inbox.md` derived cache) on every one of the ~12 plugin fan-out
  invocations, and writes via a **non-atomic** `out_path.write_text` (line 373).
  So every Stop does ~11 redundant regenerations, and a true *parallel* fan-out
  has a file-corruption window (12 concurrent writers, last-write-non-atomic).

Invisible (stderr-only, never blocks), so it is not the user-visible "fires
multiple times" symptom — but it is genuinely redundant work + a latent
corruption window.

## Fix (mini-plan)

Add the established once-per-`(Stop, session)` guard before the regen:

1. Capture the stdin payload (today's `_consume_stdin` discards it) so a
   `session_id` is available; resolve `payload.session_id` → `SHIPWRIGHT_SESSION_ID`
   → `"unknown"`.
2. After the `is_shipwright_project` no-op guard and before the regen, call
   `claim_once_for_event(project_root, "stop-triage-inbox", sid)`. First
   invocation wins and regenerates; the rest skip. Emit a one-line stderr diag
   on both the regen and the dedup-skip paths (observability + test hook).
3. The claim serializes the fan-out to ONE writer per stop, which **also closes
   the non-atomic-write parallel-corruption window** — so no separate
   `durable_atomic_write` change is needed.

**Safety of first-wins (the "must observe upstream writes" contract):** in every
plugin's `hooks.json` Stop array, `aggregate_triage_on_stop` runs *after* the
triage producer `audit_compliance_on_stop`, and `audit_compliance`'s own marker
means the first plugin's invocation is THE audit. So whichever fan-out
invocation wins the claim has already seen the settled triage. The stale
docstring "registered as the LAST Stop hook" is corrected (bloat_gate +
plugin_sync_reminder now follow it; running after the triage *producer* is what
matters).

**30s-TTL staleness is benign here:** `triage_inbox.md` is a derived cache (RTM +
the live WebUI view read `triage.jsonl` directly — `[[project_triage_inbox_md_derived_cache]]`),
so a second stop within 30s reusing the slightly-stale cache is acceptable; the
authoritative source is never skipped.

### Alternatives considered (rejected)

- *Make the write atomic instead of deduping* — fixes corruption but keeps the
  11× redundant work; the claim fixes both. Rejected.
- *Per-stop-event discriminator key* — same reasoning as the bloat-gate iterate
  (unbounded `.cache` leak, diverges from the sibling hooks). Rejected.
- *Also guard `audit_compliance_on_stop`* — its marker already dedups under the
  (observed) serial Stop execution; only a theoretical parallel race remains.
  Left as a noted follow-up to keep this change single-concern.

## Affected Boundaries

- `shared/scripts/hooks/aggregate_triage_on_stop.py` — Stop hook stdin/stderr.
- `.shipwright/.cache/stop-triage-inbox-<sid>.claim` — new claim file (gitignored).

## Confidence Calibration
- **Boundaries touched:** the aggregate_triage Stop hook (now reads the stdin
  payload for `session_id`) + the `.shipwright/.cache` claim file.
- **Empirical probes run:**
  - Read all four un-guarded shared Stop hooks; only this one has zero dedup +
    a non-atomic unconditional regen.
  - Confirmed the regen call is unconditional (no marker/claim) → all N fan-out
    invocations regenerate.
  - Confirmed `aggregate_triage_on_stop` runs after `audit_compliance_on_stop`
    in all 12 plugin Stop arrays → first-wins observes settled triage.
  - `test_stop_hooks_write_runtime.py` (single-run write coverage) green at
    baseline → the guard cannot regress it (one fresh run is always first-wins).
- **Test Completeness Ledger:**

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | N fan-out invocations (same Stop, session) → exactly ONE regen, rest skip | `tested` (`category:integration`) | integration `test_aggregate_triage_fanout.py`; unit delete-then-rerun |
  | per-session: a second session regenerates independently | `tested` | unit `test_fanout_dedup_is_per_session` |
  | single invocation still regenerates (no regression) | `tested` | existing `test_stop_hooks_write_runtime.py` (unchanged) |
  | non-shipwright / pass-path invocation never claims | `tested` | unit `test_non_shipwright_project_no_claim` |
  | >TTL re-arms a genuinely-later stop | `untestable` | `covered-by-existing-test` (no new TTL logic; `test_event_once.py`) |

  0 untested-testable.
- **Confidence-pattern check:** asymptote (depth) — only an idempotency guard
  added before the regen; the regen itself is unchanged. coverage (breadth) —
  fan-out, per-session, single, pass-path. integration composition — a
  `category:"integration"` 12-plugin fan-out test proves register-everywhere +
  the claim guard compose (`check_integration_coverage` recomputes from the diff).

## Acceptance Criteria

- **AC-1** One Stop event firing the hook N× (same session) regenerates
  `triage_inbox.md` exactly once.
- **AC-2** A different session regenerates independently (claim per-session).
- **AC-3** A single firing still regenerates (no regression).
- **AC-4** A non-Shipwright / pass-path invocation never creates the claim.
- **AC-5 (integration)** The real hook across a 12-plugin fan-out regenerates once.

## Deployment note

Hook source lives in this monorepo; webui runs the cached plugin. After merge,
`bash scripts/update-marketplace.sh` (tracked in F12).
