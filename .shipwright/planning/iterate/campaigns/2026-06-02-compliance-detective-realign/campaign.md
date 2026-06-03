---
campaign: 2026-06-02-compliance-detective-realign
branch_strategy: stacked
created: 2026-06-02
expands_triage: trg-5eb9b125
closes_findings: [trg-8747213b, trg-2bce4cc6]
---

# Campaign: 2026-06-02-compliance-detective-realign

## Intent

The detective audit (and its invocation) have drifted out of sync with two
framework redesigns:

1. **events.jsonl worktree-commit** (`iterate-2026-05-29-events-jsonl-worktree-commit`):
   `work_completed` events now ship with `commit:""` **by design** and link to
   their commit via the F6 commit's `Run-ID:` footer ↔ the event's `adr_id`.
2. **changelog/release producer**: `/shipwright-changelog` regenerates the
   tracked agent-doc / compliance MDs and commits them as `chore(release):`
   **without** a `Run-ID:` trailer.

Two detective checks still assume the *old* model, and the audit's background
invocation assumes a Python project env. The result is **recurring
false-positive compliance findings in both repos** that the per-project
`disabled_checks` band-aid (#132) only *masks* — it does not fix the root.

This campaign realigns the checks + the invocation with current reality so the
findings close at the root and the existing triage items auto-clear.

**Tracking model (mirrors the `2026-06-02-hook-consolidation` / `trg-721b1765`
pattern):**
- **Anchor:** `expands_triage: trg-5eb9b125` — a stable, hand-authored
  `kind: improvement` / `source: architecture` triage item that represents this
  engineering work and is what the campaign expands. It is **not** part of the
  producer-owned compliance backlog, so it does not auto-dismiss.
- **Closed findings:** `trg-8747213b` (monorepo, Group E) + `trg-2bce4cc6`
  (webui: A5.0 / B7 / D3 / D5 / G2) are the producer-owned **symptom** items.
  We do **not** mint duplicates of those — they auto-dismiss when the work lands
  (see Closure map) and serve as the verification signal.

### Root-cause evidence (verified this session)

| Finding | Repo | Root cause (file:line) | Verdict | Sub-iter |
|---|---|---|---|---|
| **Group E** `session_handoff`/`build_dashboard` | monorepo | `audit_staleness.find_snapshot_commit()` matches only `git log --grep=Run-ID:`; `a0aa1e62 chore(release): v0.23.1` regenerated both MDs **without** a `Run-ID:` trailer → audit compares on-disk (==HEAD) against the older `f75a0390` snapshot. Files are clean & ==HEAD. | False-positive, recurs every release | **C1** |
| **B7** commits w/o event | webui | `group_b._check_b7` builds `tracked` only from the event `commit` field (empty-commit events excluded, line 420); `git_log_scan.apply_retention_rules` knows only merge/bot/path. Since 2026-05-29 events ship `commit:""` and link via `Run-ID:`↔`adr_id`. **Verified:** `26ea506` carries `Run-ID: iterate-2026-06-02-campaigns-board-lane`; event `evt-177f8389` has the matching `adr_id`. B7 is blind to that linkage. | Check not nachgezogen to 2026-05-29 design | **C1** |
| **A5.0** PyYAML unavailable | webui | `audit_compliance_on_stop.py` runs the full audit via `uv run <shared-script>` from the **project root**; a non-Python adopt repo has no root `pyproject` declaring `pyyaml` and the audit entry has no PEP-723 deps → `group_a5.py:544 import yaml` fails. **Reproduced:** `uv run python -c "import yaml"` from webui root → `ModuleNotFoundError`. Monorepo is immune (root pyproject has pyyaml → no A5.0 there). | Invocation/env bug, not repo content | **C2** |
| **D3** FR promised, never reaffirmed | webui | `group_d._check_d3` requires a **strictly-later** `affected_frs` event (`ts > promised_ts`). `FR-01.33` is introduced (`new_frs`) **and** affected in the **same** event `evt-177f8389` → perpetually "pending". | Semantics too strict for single-iterate FRs | **C3** |
| **D5** feature event, no FR link | webui | reopen event `evt-83b9b73f` (`intent=feature`, `spec_impact=ADD`, no `affected_frs`/`change_type`) should have been hard-rejected by the FR-gate (`record_event._fr_or_change_type_gate_error`, ADR-059), but `finalize_iterate._record_event` **bypasses the gate** (documented: "out of scope for C.1"). | Real gap — D5 detects what the gate should prevent | **C3** (prevent) + **C4** (data) |
| **G2** scope=`board` | webui | `board` not in webui `audit_config.g2_stoplist`. | Config maintenance | **C4** |

> **The `disabled_checks` band-aid masked, not fixed.** The monorepo disabled
> B7/G2 wholesale (#132), which is precisely why the B7-vs-Run-ID mismatch never
> surfaced there. Disabling B7 in the webui too would re-mask C1. **Do not.**

## Consolidation principle

6 distinct issues → **4 iterates**, grouped by cohesion (shared theme + shared
code + same review/risk profile), not 1:1:

- **C1** bundles B7 + Group E because both are *the same conceptual fix*: "teach
  the detective audit to honor **Run-ID provenance**" (event↔commit via the
  `Run-ID:` footer; tracked-MD snapshot via the Run-ID-bearing / release
  commit). Shared helper opportunity, shared tests, one reviewable PR.
- **C2** is a different layer (audit **invocation**, not check logic) → its own
  small iterate.
- **C3** bundles the FR-gate finalize bypass (preventive, write-side) + D3
  semantics (detective, read-side) because both are *FR-linkage lifecycle*
  correctness and touch the same `affected_frs`/`new_frs` concept.
- **C4** is the only **webui-repo** work and must land last (after the monorepo
  fixes are merged **and** `update-marketplace.sh` synced), else it is a
  treadmill.

## Sub-Iterates

| ID | Slug | Title | Repo | Depends on | Status |
|---|---|---|---|---|---|
| **C1** | audit-run-id-provenance | Detective audit honors Run-ID provenance: B7 matches `Run-ID:`↔`adr_id` (commit-field fallback for legacy); Group E recognizes changelog/release snapshots | monorepo | — | pending |
| **C2** | audit-invocation-resilience | Guarantee PyYAML at audit invocation (PEP-723 deps / `uv run --with` / `--project`) **and** degrade `group_a5` to SKIP (not FAIL) when yaml is genuinely absent | monorepo | — | pending |
| **C3** | fr-linkage-lifecycle | Close the FR-gate bypass on the finalize path (prevent D5-class at write) + accept same-event `new_frs`+`affected_frs` as delivered in D3 | monorepo | — (trace resolved) | pending |
| **C4** | webui-data-config | webui repo: add `board` to `g2_stoplist`; link reopen event `evt-83b9b73f` to its FR (data reconcile) | **webui** | C1 + C2 merged + `update-marketplace.sh` synced | pending |

## Sequencing rationale

- **C1 + C2 first** — both no-dep, verified/reproduced bugs, independent
  (different files), can run in parallel/stacked in any order. They are what
  auto-closes the Group E part of `trg-8747213b` and the A5.0/B7 parts of
  `trg-2bce4cc6`.
- **C3 trace RESOLVED (2026-06-02)** — the bypass is
  `finalize_iterate._record_event` → `append_event` (no FR-gate); the reopen
  event's real SHA is just the F7 `--commit` path, not a separate writer. AC-1's
  insert point is pinned (see C3 spec). C3 is now deps-free; it stays *after*
  C1/C2 only by priority (highest blast radius — the finalize gate can block
  iterate completion), not by dependency.
- **C4 last and in the webui repo** — the webui background producer fires the
  **cached** plugin; the C1/C2 fixes only reach it after merge + marketplace
  sync. Doing the data/config fixes earlier would be masked/re-flagged.

## Closure map (which sub-iterate clears what)

- `trg-8747213b`: Group E → **C1**.
- `trg-2bce4cc6`: B7 → **C1**; A5.0 → **C2**; D3 → **C3**; D5 → **C4** (data) +
  **C3** (prevent recurrence); G2 → **C4**.
- **No manual closure tracking needed** — once the work lands and the producers
  re-run, `audit_compliance_on_stop.mirror_findings_to_triage` auto-dismisses
  the cleared findings. The two triage items ARE the done-signal.

## Out of scope

- Reshaping the triage producer cadence / SBOM cluster collapse
  (`proposed-sbom-triage-cluster-collapse.md`) — unrelated.
- Hook fan-out topology (`2026-06-02-hook-consolidation` campaign) — separate.
- Behaviour of checks not listed above (A5.2–A5.7, C/F groups) — untouched.
