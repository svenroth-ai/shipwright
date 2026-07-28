# Mini-Plan — IT-0 Hygiene-Sweep

Spec: `.shipwright/planning/iterate/2026-07-28-hygiene-sweep.md`

## Order of work

1. **AC-1 + AC-2 (data only)** — regenerate `shipwright_bloat_baseline.json`:
   add 9 missing oversize entries, lower 10 stale `current` ceilings to the
   measured value. Written through `bloat_baseline.write_baseline` (durable
   atomic write) so producer/consumer schema cannot drift. No hand-editing.
2. **AC-3 (doc)** — `CLAUDE.md` 213 → ≤200 by relocating two rationale blocks
   that already have a canonical home, replacing each with a one-line pointer.
3. **AC-4 (code + tests)** — `finalize_iterate.py` populates `tests` on the
   `work_completed` event from `shipwright_test_results.json`.
4. **AC-5 (code + tests)** — `check_security_scan` reads `ci-security.json`;
   retire the events-based review-findings RTM rows.
5. Boundary probes, ledger, F0 → F12.

## AC-4 — chosen design

`finalize_iterate._record_event` gains a resolver that reads
`shipwright_test_results.json` from `project_root` and derives
`{passed, total, skipped?, e2e_run?}`, validated through the **existing**
`tests_block.validate_tests_block` (the same contract `record_event.py` enforces
at line 219) so the two writers cannot disagree.

Precedence: explicit `tests` in `--event-extras-json` > derived-from-results >
key absent entirely.

Fail-open: missing file, unreadable file, malformed JSON, or a shape that fails
validation all leave the event with **no** `tests` key — byte-identical to
today's behaviour. F5b must never be the reason a finalize aborts.

**Which numbers.** `shipwright_test_results.json` carries `iterate_latest`. Read
the totals the F5 ledger already records for *this* run; do not recompute and do
not reach into a foreign run's block. If `iterate_latest.run_id` does not match
the run being finalized, treat it as absent — a stale snapshot must not be
laundered into this run's event. (This is the same failure mode as
`trg-81fbf8ed`/`project_derived_snapshots_stale_ledger`: the file is a derived
snapshot and a restore can reset it to the previous run.)

### Alternative considered — rejected

*Have F5b shell out to the test runner and count.* Rejected: F0 already ran the
full suite minutes earlier; re-running it doubles the slowest phase of every
iterate, and a second run can disagree with the one the ledger recorded, which
would make the event *less* trustworthy, not more. The recorded ledger is the
evidence; the event should carry it, not re-derive it.

## AC-5 — chosen design

`get_unresolved_findings` (RTM review-counter reader) is **replaced** by a
reader over `.shipwright/compliance/ci-security.json`:

| scan state | gate |
|---|---|
| file absent | allow (exit 0) — unchanged fail-open posture |
| unreadable / malformed | allow, diagnostic to stderr |
| `degraded: true` | **block** — a fataled scanner is not evidence of clean |
| `open_high_critical > threshold` | **block** |
| otherwise | allow |

Threshold stays `enforcement.allowed_critical_findings` (default 0), so an
operator who already set it keeps their setting.

The hook keeps its name: it now *is* a security-scan check, so renaming it would
churn `hooks.json` across 12 plugins for no gain. The docstring, the block
message and the override-log hook name stay consistent with the real subject.

RTM: drop the two events-based rows (`rtm_generator.py:622-623`). Keep the
section-based rows — different data source, genuine fixed-list.

### Alternative considered — rejected

*Keep reading the review counter but rename the hook to
`check_review_findings`.* Rejected on two counts: it preserves a gate over a
number that under-reports by construction (4/399 events carry the block, `fixed`
written pre-remediation), and it leaves the *deploy* path with no security gate
at all — the one thing a pre-deploy hook is actually for. Renaming would make
the label honest while keeping the gate useless.

## Risk / blast radius

- `cross_component` fires from the diff (`hooks/.+\.py$`) → integration test
  required, non-dodgeable at F11.
- `touches_io_boundary` → round-trip probe on the baseline JSON and on
  `ci-security.json`.
- `shipwright_bloat_baseline.json` is **not** churn-allowlisted: this run must
  land before any other run that writes it.
