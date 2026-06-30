# Iterate Spec — Re-tag mis-filed compliance/security FEATURE work to FR-01.10/FR-01.07

- **Run ID:** `iterate-2026-06-30-fr-retag-honesty`
- **Intent:** CHANGE (compliance traceability data-correction)
- **Complexity:** medium
- **Spec Impact:** NONE for this iterate (metadata correction; no compliance *code* behavior change). The overlays it appends set `spec_impact=modify` on the **amended** events, reflecting that *those* events genuinely modified FR-01.10/FR-01.07 behavior.

## Problem

Recent `/shipwright-compliance` + `/shipwright-security` FEATURE work was filed
`change_type=compliance` / no-FR even though it delivers FR-01.10 (compliance
documentation) — and, for the security-evidence pieces, FR-01.07 — functionality.
This dropped the strict FR-tag rate for the last-30 window to **3/30 (10%)** vs
**18% all-time**. The Control Grade honesty gate (`_grade_gate.apply_verdict_gate`,
branch (a)) caps the headline at `NON_A_CEILING = 89` whenever `recent_pct <
all_pct`, so the grade is pinned at **B (89/100)** despite all dimensions being
otherwise green. (Verified by running the real producer on the worktree base.)

## Goal

Restore an **honest** grade A by correcting the FR-tagging of the genuinely
FR-bearing events — not by gaming the metric. Append `event_amended` overlays
(`record_event.py --type event_amended`) that set `affected_frs` (+ `spec_impact=
modify`) on the real features. Leave genuine infra/CI events as no-FR.

## Scope — exact event mapping

RE-TAG → FR-01.10 (+FR-01.07 on the two AR-10 security-evidence events):

| Event | ADR / desc | affected_frs | spec_impact |
|---|---|---|---|
| `evt-bcd40c31` | control-grade-honesty (Goodhart honesty gate) | FR-01.10 | modify |
| `evt-07b1fe9c` | ci-security-dashboard (AR-10 CI-security ingestion) | FR-01.10, FR-01.07 | modify |
| `evt-f8975c35` | ar10-sarif-ingestion (AR-10 SARIF fallback) | FR-01.10, FR-01.07 | modify |
| `evt-2aa2ddcf` | sbom-honesty (AR-04 SBOM quality) | FR-01.10 | modify |
| `evt-a0fb4818` | cc3-ar05-rtm-reconciled (AR-05 RTM Reconciled column) | FR-01.10 | modify |
| `evt-75761dd3` | grade-anchor-clarity (anchors, drop SonarQube) | FR-01.10 | modify |
| `evt-0bcce391` | grade-anchor-maint-wording (maintainability anchor) | FR-01.10 | modify |

STAY no-FR (real infra; already classified, left untouched): scorecard
add/fix/remove (CI; `evt-e1d5bdb0`, `evt-b89652cc`), mtime drift-detector removal
(`evt-62cb4cbd`), bloat-baseline tighten (`evt-244f895d`), events_log lazy-import
doc (`evt-5ba214bd`), ci-security.json data refresh (`evt-2d2828bd`).

FR-01.07 scope decision (user-confirmed): only the two AR-10 events. SBOM is named
under FR-01.10 in the spec, so it stays FR-01.10-only.

## Reconciliation safety (the CAVEAT)

`spec_impact=modify` makes the amended FRs **behavior-touched** at the **original**
event ts (overlays inherit the target's ts). The newest re-tagged event
`evt-bcd40c31` (2026-06-30T13:58) has `tests.total=0`, so it cannot self-reconcile,
and the current latest FR-01.10 verify (`evt-cf798241`, 13:13) predates it → an
unverified touch. Mitigation (user-confirmed "link a later test event"):
**this iterate's own F5b `work_completed` event** names `FR-01.10` + `FR-01.07`
with `tests.total>0` (real F0 counts) at `ts=now`, the latest event of all → it is
the verify that reconciles every retro-touch. (4 of 7 targets also self-reconcile
via their own test counts.)

## Affected Boundaries

- `shipwright_events.jsonl` (append-only event log) — 7 appended `event_amended`
  overlays + 1 F5b `work_completed` verify event.
- Regenerated compliance artifacts under `.shipwright/compliance/` (dashboard, RTM,
  test-evidence, change-history, sbom) — derived, produced by the real producer.

## Out of scope / follow-up

- **Sub-FR decomposition (`fr-model-followup`)** — no sub-FRs (FR-01.10.x) exist;
  building them is a separate spec-ADD iterate. Filed as a follow-up triage item.

## Confidence Calibration

- **Boundaries touched:** `shipwright_events.jsonl` (append-only data); derived
  `.shipwright/compliance/*` artifacts. **No source code changed (zero `.py` diff).**
- **Empirical probes run:**
  1. **Real producer baseline** (`update_compliance.py` on worktree base): Control
     Grade **B (89/100)** — *"Capped: traceability declining (FR-tag 10% vs 18%
     all-time, last 30)"*; Quality Indicator `3/30 (10%) WARN`. Reproduces the symptom.
  2. **Faithful rule-replay sim** (worktree base, 255 events): baseline
     `recent=3/30 (10.0%) < all=18.0%` → declining → B-cap. Projected (7 overlays +
     this-iterate verify event) `recent=11/30 (36.7%) > all=21.4%` → not declining;
     reconciliation ratio **1.0** (FR-01.10 + FR-01.07 RECONCILED).
  3. **Stress test** (overlays, NO verify event): reconciliation ratio **0.6** —
     FR-01.10 + FR-01.07 `NEEDS_REVERIFICATION`. **Proves the F5b verify event is
     load-bearing** (the newest re-tagged event `evt-bcd40c31` has `tests.total=0`,
     can't self-reconcile).
  4. **Post-overlay sim** (real modified log, 262 lines): `recent=10/30 (33.3%)`,
     declining=**False** — the decline is already cleared by the overlays alone.
  5. **F0 full suite** (all event-log/compliance-consuming subsystems):
     **4955 passed, 0 failed** (compliance 922, shared 3602+196+61, integration 174).
  6. **Post-finalize producer regen** (after F5b records the verify event
     `evt-f90c7126`): real dashboard reads **Control Grade A (100/100) "Under full
     control"**; Change reconciliation **0/5 behavior-touched FRs unreconciled**;
     "Recent changes traced to an FR 11/30 (37%) PASS". Decline gone.
- **Test Completeness Ledger:**

  | # | Behavior | Status | Evidence |
  |---|----------|--------|----------|
  | 1 | 7 events re-tagged FR-01.10 (+FR-01.07 on the 2 AR-10) via overlays | tested | probe 4: recent 3/30→10/30, all 18.0%→21.0%; overlays applied 7/7 |
  | 2 | FR-tag decline cleared → B-cap lifts → grade A | tested | probe 1 (B before) + probe 6 (A after) |
  | 3 | Reconciliation stays green (FR-01.10, FR-01.07 RECONCILED) | tested | probe 2 (ratio 1.0) + probe 6 (RTM Reconciled column) |
  | 4 | F5b verify event is load-bearing for the latest unverified touch | tested | probe 3 (ratio 0.6 without it) |
  | 5 | No source regression (data-only) | tested | probe 5 (4955 passed) |
  | 6 | Real infra events stay no-FR (not over-tagged) | tested | probe 2: all_pct rose only +3.4pp; stay-list excluded from overlay set |

  0 testable-but-untested · 0 untestable rows · enumeration covers the change.
- **Confidence-pattern check:** asymptote (depth) — verified against the **real
  producer** (not only the replica) at both baseline and post-finalize, plus the
  254→262-event log re-run after the actual append. Coverage (breadth) — strict
  FR-tag trend + reconciliation dimension + RTM Reconciled column + 4955-test
  regression sweep. Integration composition — n/a (no `cross_component` machinery
  touched; pure append-log data correction).
