# Sub-iterate B — GC / compaction of the dismissed pile

- **Campaign:** 2026-06-05-track-triage-jsonl (sub-iterate B of A→E)
- **run_id:** `iterate-2026-06-05-triage-dismissed-gc`
- **Type:** feature (one-off maintenance tool) · **Complexity:** small ·
  **Risk flags:** `touches_io_boundary` (rewrites the triage.jsonl log)
- **Branch:** `iterate/triage-dismissed-gc` · **Anchor:** `expands_triage: trg-2fb7d3bc`

## Problem

Before `.shipwright/triage.jsonl` becomes git-tracked (sub-iterate C), the
dismissed pile (175 items / **53 machine-churn**) must be compacted so producer
churn does not enter permanent history. But the pile is **~half human-curated**
(122 kept: re-prioritisations, "resolved by PR #N", supersessions, billing
notes) — that is real audit history and must survive.

## Decision (policy = machine-churn ONLY, user-approved 2026-06-05)

New tool `shared/scripts/tools/triage_gc.py`. An item is droppable **iff**:
`status == "dismissed"` **AND** `statusBy ∈ {sbomGenerator, auditDetector,
driftDetector, f05Detector, githubImporter, complianceBacklog,
phaseQualityBacklog, testEvidence}` **AND** `statusReason ∈ {sbomResolved,
auditResolved, driftResolved, f05Resolved, githubResolved, complianceResolved,
phaseQualityResolved, testEvidenceResolved}` (exact token). Both conditions
required → a human dismissal that reuses a token, or a producer dismissal with
free-text rationale, survives. `promoted` + open never dropped.

> **Set completeness (Codex review):** the original draft listed 6 producer
> pairs; `phaseQualityBacklog`/`phaseQualityResolved`
> (`phase_quality/_triage_bundle.py:247,254`) and
> `testEvidence`/`testEvidenceResolved` (`test_evidence.py:908,909`) are real
> background-producer auto-resolves that were missing — added so GC actually
> collects them. The both-conditions predicate keeps the policy conservative
> (human-curated dismissals still survive). External review (GPT-5.4) flagged the
> spec/code drift; this list is now the authoritative 8+8 set.

The store is append-only, so compaction is a **destructive rewrite**:
dry-run is the default; `--apply` writes a `.bak` backup first and re-validates
(header intact, no orphan `status` events, no droppable item survives).

## Deliverable vs run

This PR ships the **tool + tests** (the capability). The destructive `--apply`
on the live pile is a **gated operational step** run once at the C/E migration
window — after sub-iterate A's one-time cluster-key migration churn settles, so
that churn is compacted in the same pass — then E commits the compacted jsonl.

## Acceptance criteria (sub-iterate)

- [x] **B-AC1.** Machine-churn dismissals dropped; all human/operator/webui/cli
      dismissals + promoted + open kept (both-conditions predicate).
- [x] **B-AC2.** Dry-run is default and writes nothing; `--apply` backs up + rewrites.
- [x] **B-AC3.** Rewrite drops every line (append + all status events) of a
      dropped id; post-rewrite validation rejects orphan status / surviving drop.
- [x] **B-AC4.** Idempotent (`--apply` twice → no second rewrite).
- [x] **B-AC5.** Report is console-encoding-safe (cp1252 can't crash on `→`).
- [x] **B-AC6.** Live dry-run: 175 total → 53 droppable / 122 kept (evidence).

## Affected Boundaries

| Producer | Consumer | Format |
|---|---|---|
| `triage_gc.apply_gc` rewrites the event log (removes lines) | every triage reader (`read_all_items`), WebUI, RTM, audit detectors | `.shipwright/triage.jsonl` |

Read-back contract preserved: header first line, append+status events, last-status-wins.

## Confidence Calibration

- **Boundaries touched:** the `.shipwright/triage.jsonl` log file (rewrite). The
  triage event schema and `read_all_items` resolution are unchanged.
- **Empirical probes run:**
  1. *Predicate probe* — `is_machine_churn` requires BOTH producer dismisser AND
     exact machine token; human-reason / human-dismisser / promoted all return False.
  2. *Round-trip probe* — `apply_gc` → `_iter_raw_lines` → `read_all_items`: dropped
     ids absent, kept ids intact, header present, no orphan status (multi-status item).
  3. *Idempotency probe* — second `--apply` is a no-op (byte-identical).
  4. *Backup probe* — `.bak` written before rewrite and still holds the dropped data.
  5. *Console-safety probe* — cp1252 stdout with a `→` title does not crash (regression).
  6. *Live dry-run probe* — main-tree pile: 53 droppable (pure producer auto-resolves),
     122 kept (incl. all human curation). Writes nothing.
- **Test Completeness Ledger:**

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | predicate requires both conditions | `tested` | `test_is_machine_churn_requires_both_conditions` |
  | plan drops machine, keeps human | `tested` | `test_plan_drops_machine_keeps_human` |
  | promoted/open never dropped | `tested` | `test_promoted_and_open_never_dropped` |
  | machine reason + human dismisser kept | `tested` | `test_machine_reason_but_human_dismisser_kept` |
  | producer dismisser + human reason kept | `tested` | `test_producer_dismisser_but_human_reason_kept` |
  | dry-run writes nothing | `tested` | `test_dry_run_writes_nothing` |
  | apply compacts + backs up | `tested` | `test_apply_compacts_and_backs_up` |
  | multi-status item fully dropped, no orphan | `tested` | `test_apply_drops_all_lines_of_multi_status_item` |
  | apply idempotent | `tested` | `test_apply_idempotent` |
  | header preserved + validates | `tested` | `test_apply_preserves_header_and_validates` |
  | report console-safe (cp1252) | `tested` | `test_report_survives_non_cp1252_title` |

  0 testable-but-untested. The live `--apply` run is an operational step (deferred
  to C/E), not a behavior of this diff.
- **Confidence-pattern check:** *depth* — predicate + rewrite + validation are
  each probed at the boundary; *breadth* — drop/keep/promoted/open/multi-status/
  idempotent/backup/console all covered.
