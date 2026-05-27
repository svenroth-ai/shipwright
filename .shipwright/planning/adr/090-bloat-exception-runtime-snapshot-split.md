# ADR 090: Bloat exception — 6 files bumped to absorb the runtime/snapshot split implementation

<!-- Granting a bloat-baseline exception for 5 files modified by
     iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox.
     New `current` values land in shipwright_bloat_baseline.json with
     state="exception" and adr="ADR-090". -->

- **Status:** accepted
- **Date:** 2026-05-27
- **Re-Review-Date:** 2026-08-27 _(3 months out — re-evaluate whether the
  finalize_iterate snapshot helpers can be moved into a sibling module,
  and whether test_generate_handoff_on_stop's double-assertion contract
  per test case can be factored into a shared helper)_
- **Incident Reference:** iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox
  + PR pending — closes the recurring "main is dirty after every session"
  regression class verified against session `40b1eb76` end-state. See
  also ADR-089 for the full technical decision.

## Context

The iterate extends PR #78's single-producer pattern (compliance MDs) to
the 3 agent-doc MDs (session_handoff, build_dashboard, triage_inbox)
AND closes a finalize sandbox-escape via stale session→worktree pointer
AND codifies merge-not-rebase for Run-ID branches. Six files grow past
their existing grandfathered baselines:

| File | Baseline | New | Delta |
|---|---:|---:|---:|
| `shared/scripts/tools/finalize_iterate.py` | 352 | 475 | +123 |
| `shared/tests/test_generate_handoff_on_stop.py` | 337 | 402 | +65 |
| `plugins/shipwright-compliance/scripts/audit/audit_staleness.py` | 308 | 347 | +39 |
| `shared/scripts/tools/aggregate_triage.py` | 373 | 400 | +27 |
| `shared/scripts/hooks/generate_handoff_on_stop.py` | 321 | 339 | +18 |
| `plugins/shipwright-compliance/tests/test_audit_snapshot.py` | 450 | 464 | +14 |

The growth is concentrated in `finalize_iterate.py` (4 new helpers:
`_atomic_replace`, `_refuse_symlink`, `_unlink_runtime_artifacts`,
`_snapshot_triage_runtime`) and `test_generate_handoff_on_stop.py`
(8 updated tests now asserting both runtime and tracked paths under the
new contract).

## Ousterhout Argument

`finalize_iterate.py` is a genuinely deep module by Ousterhout's
definition. The public interface is small — `run(project_root, run_id, ...)`
and `attach_commit_after_finalize()`. Behind it sits substantial
behavior: event recording with idempotency, compliance regeneration,
dashboard generation, handoff generation with canon marker, and (post
this iterate) atomic triage snapshot + runtime cleanup. Splitting the
new snapshot helpers into a sibling module would expose internal
contracts (when to copy vs when to direct-write, when to wipe runtime,
how to handle symlinks) that consumers don't and shouldn't care about.
The interface stays `run(...)`; the per-file decision is implementation
detail.

`aggregate_triage.py` similarly has a narrow `main(argv)` CLI surface.
The `--out-dir` flag with path-escape validation is implementation
detail of the same CLI.

The two test files are inherently coupled to the contracts they verify
— splitting `test_generate_handoff_on_stop.py` by test would require
duplicating the `tmp_project` fixtures + the hook subprocess helpers in
multiple files, increasing total LOC.

`generate_handoff_on_stop.py` and `test_audit_snapshot.py` grew by
≤27 LOC each, which is within the noise floor of any non-trivial
feature change.

## YAGNI Check

Walking the 5 files' responsibilities:

- `finalize_iterate.py` — every new helper is load-bearing TODAY: the
  snapshot helpers are the single producer of tracked agent-doc MDs;
  the atomic-replace + symlink-refuse mitigate concrete external review
  findings (OpenAI #4, #11). No speculative scope.
- `test_generate_handoff_on_stop.py` — every updated test asserts the
  single-producer contract on a real production path (Stop hook writers).
  None can be removed without losing regression coverage.
- `aggregate_triage.py` — `--out-dir` is required by the Stop hook AND
  by the new finalize seed path. Path-escape validation is needed
  because the flag becomes attacker-influenceable via the project_root
  argument.
- `generate_handoff_on_stop.py` — the runtime-path redirect is the
  point of the iterate. No speculative growth.
- `test_audit_snapshot.py` — the new test_compare_doc test covers the
  realistic post-merge scenario (registry expansion). Needed to
  drift-protect the code-reviewer HIGH #1 fix.

Nothing in this iterate's growth is "might need next quarter."

## Chesterton-Fence Check

The existing baselines were established by iterate-2026-05-25-bloat-foundation
(Campaign A). At that time `finalize_iterate.py` was 352 LOC, having
absorbed the F5b/F6.5/F7 + event recording + idempotency machinery from
multiple prior iterates. The fence was deliberately raised to grandfather
the historically-grown file. There is no documented intent to split it
— the iterate that established the limit accepted the existing shape.

The runtime/snapshot helpers added here are the natural extension of
the F5b step pattern: each existing step already lives as a private
helper (`_update_dashboard`, `_update_compliance`, `_record_event`,
`_generate_handoff`). The new helpers follow the same pattern. Splitting
into a sibling module would require either (a) duplicating the `_atomic_replace`
+ `_refuse_symlink` primitives, or (b) inventing an "import surface"
between two finalize modules that don't otherwise share code. Both
options trade clarity for LOC.

## Decision

Bump `current` for the 5 files to absorb the iterate's growth, with
state="exception" and adr="ADR-090". New limits:

```
plugins/shipwright-compliance/scripts/audit/audit_staleness.py     300 → 347
plugins/shipwright-compliance/tests/test_audit_snapshot.py         300 → 464
shared/scripts/hooks/generate_handoff_on_stop.py                   300 → 339
shared/scripts/tools/aggregate_triage.py                           300 → 400
shared/scripts/tools/finalize_iterate.py                           300 → 475
shared/tests/test_generate_handoff_on_stop.py                      300 → 402
```

Retirement plan: at the 2026-08-27 re-review, evaluate two splits:

1. `finalize_iterate.py` → move `_atomic_replace`,
   `_refuse_symlink`, `_unlink_runtime_artifacts`, `_snapshot_triage_runtime`
   into `shared/scripts/lib/iterate_snapshot.py`. Reduces this file by
   ~120 LOC if the helpers don't need access to the existing private
   step helpers.
2. `test_generate_handoff_on_stop.py` → extract the double-assertion
   pattern (runtime + tracked) into a shared helper, reducing per-test
   line count.

Both splits are deferred to this iterate (would have expanded scope
beyond the bug fix).

## Consequences

- The bloat anti-ratchet hook no longer blocks commits to these 5
  files at their new limits.
- Group H (bloat detective audit) will still flag any future regression
  past the new limits — the exception is a one-shot bump, not a
  permanent waiver.
- The 2026-08-27 re-review is the gate for the deferred splits. If
  neither lands by then, this ADR should be re-justified or amended
  with a new re-review date.

## Rejected alternatives

- **Shrink to baseline.** Trimming `finalize_iterate.py` by 123 LOC
  without losing the new helpers would require collapsing docstrings,
  removing the per-file decision rationale, and inlining the symlink
  refuse + atomic replace helpers. That would weaken readability and
  reviewer trust against minimal LOC gain. The helpers' bodies are
  near-irreducible (atomic-replace is 12 LOC including error handling;
  unlinking with status reporting is 18 LOC). Rejected.
- **Split finalize_iterate.py NOW.** The helpers don't otherwise share
  state with the existing step helpers, so a sibling module IS feasible.
  But splitting in the same diff as a contract change increases the
  reviewer surface and risk. The re-review date is the correct gate.
  Rejected for this iterate.
- **One bloat-exception ADR per file.** Mechanically uniform but bureaucratic:
  the 5 files share a single justification (this iterate's coherent
  feature implementation). One ADR covers them with one re-review date.
  Five ADRs would force five separate re-reviews. Rejected.
- **Skip the change.** The recurring "main is dirty after every session"
  pattern affects every operator, every session. The fix's value is high
  and the LOC growth is justified. Rejected obviously.

---

## External Sources Acknowledged

This ADR follows the template at
`.shipwright/planning/adr/_template-bloat-exception.md`. The YAGNI Check
and Chesterton-Fence Check headings are adapted from obra/superpowers
(MIT © Jesse Vincent) and addyosmani/agent-skills (MIT © Addy Osmani)
per the template's attribution.
