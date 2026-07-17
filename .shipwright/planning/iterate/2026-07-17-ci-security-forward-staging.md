# Iterate: Stage `ci-security.json` in the churn regenerate follow-up (close #375 CR-1)

- **Run ID:** iterate-2026-07-17-ci-security-forward-staging
- **Intent:** bug (forward-staging defect in the churn-merge regenerate step)
- **Complexity:** medium — the `classify_complexity` message-prose estimate came
  back `large`, a known DESCRIPTION-keyword false-positive (the diff-authoritative
  `risk_detectors` recompute at F11 governs, not the prose). The real signal is the
  `cross_component` risk flag (the diff touches `resolve_churn_conflicts.py`, a
  `CROSS_COMPONENT_FILE_PATTERN`) whose **safety floor is medium**. Overridden to
  medium and recorded in `shipwright_test_results.json.degraded[]`.
- **Risk flags:** `cross_component` → enforces **integration coverage** + full test suite.
- **Spec Impact:** NONE — framework-internal merge machinery; no project FR /
  `spec.md` / product-surface change. (BUG default; behaviour-correcting.)

## Problem (deferred #375 CR-1, "pre-existing, independent of the allowlist admission")

`shared/scripts/tools/resolve_churn_conflicts.py::regenerate_tracked_snapshots`
re-derives the tracked snapshots after an `integrate_main` merge and stages them.
Its staged set is built purely from its own `out` dict:

```python
if any(t in COMPLIANCE_MDS for t in targets):
    paths = finalize_iterate._update_compliance(project_root)   # iterdir-covers the WHOLE compliance/ dir
    for rel in sorted(COMPLIANCE_MDS):                          # .md-shaped set only
        out[rel] = "regenerated" if paths else "error"
...
staged = [rel for rel, outcome in out.items() if outcome != "error" and (project_root / rel).exists()]
```

`_update_compliance` runs `update_compliance.py`, whose `refresh_ci_security`
best-effort-rewrites `.shipwright/compliance/ci-security.json` **from a fresh
`security.yml` run**. But `ci-security.json` is a `.json`, so it is absent from
the `.md`-shaped `COMPLIANCE_MDS`/`DERIVED_MDS`, so it never enters `out`, so it
is never staged. When a fresh scan DID rewrite it, that rewrite is left
**modified-but-unstaged**; the follow-up commit (`git commit` on the staged index)
returns `ok` with a **dirty local `ci-security.json`** and the refresh is lost —
the pushed branch carries only the merge's `--theirs` mainline placeholder.

#375 added `ci-security.json` to the regenerate-failure **ROLLBACK** restore set
(`sorted(DERIVED_MDS | {CI_SECURITY_SUMMARY})` in `integrate_main`) but not the
**forward staging** set. So the two sides are asymmetric: rollback restores it,
the happy path drops it. This closes that asymmetry.

### Why it is benign but real
When `refresh_ci_security` does not write — `gh` unavailable / offline / no fresh
`security.yml` run within the freshness window — the summary is untouched, so
there is nothing to stage and this is a true no-op (fail-soft SKIP, no write).
When a fresh scan DID rewrite it (the drop case), the rewrite was silently
dropped: the **pushed branch stayed correct** (it carries the committed
`--theirs` placeholder), but the local refresh was lost + a dirty line left.
Present on **every** integrate regen, independent of the #375 allowlist admission
(confirmed by the #375 code-reviewer).

**Frequency nuance (doubt-review advisory 1):** on a `gh`-available dev machine,
`refresh_ci_security` writes the LATEST run's summary whenever a run exists — it
does not diff against the committed content first. So post-fix, integrate will
**legitimately** stage+commit a ci-security refresh whenever a genuinely newer
run is the latest (different `run_id`/`scan_date`). That is the fix's whole point
— a *desired*, non-phantom refresh commit, not churn. It is only a no-op when the
producer skips or re-fetches the *same* run (`write_ci_security` is deterministic
`sort_keys`, no wall-clock field → byte-identical → `git add` no-op).

## Fix (forward-staging parity — the mirror of the rollback set)

Add `CI_SECURITY_SUMMARY` to the compliance staging loop so it enters `out` and
the existing `.exists()`-guarded `staged` filter picks it up:

```python
for rel in sorted(COMPLIANCE_MDS | {CI_SECURITY_SUMMARY}):
    out[rel] = "regenerated" if paths else "error"
```

- `ci-security.json` is produced by the **same** `_update_compliance` call as the
  five compliance MDs, so it belongs in the same block.
- The `staged` filter already guards on `(project_root / rel).exists()`, so a
  non-existent summary is skipped; `git add` on an **unchanged** summary is a
  no-op, so the fail-soft common case creates **no phantom follow-up commit**.
- This is the exact forward mirror of `integrate_main`'s rollback restore set
  `DERIVED_MDS | {CI_SECURITY_SUMMARY}` — the two are now symmetric.

**ADR-099 300-cap parity (in scope this time):** `resolve_churn_conflicts.py` is
at its ADR-099 exception ceiling (357 = baseline `current`), so the anti-ratchet
gate (local hook + `bloat-check.yml` CI) blocks any net growth. The fix is
**net-neutral**: the new `CI_SECURITY_SUMMARY` import line is offset by unwrapping
the sibling `triage_inbox` producer-dispatch call (E501/E704 are deliberately
un-gated in this repo's ruff ruleset), holding the file at exactly 357 lines. No
baseline bump, no new ADR, no Group-H crossing.

## Affected Boundaries

- Framework cross-component merge machinery: `resolve_churn_conflicts`
  (`regenerate_tracked_snapshots`) ⊕ `churn_merge` (`CI_SECURITY_SUMMARY`) ⊕
  `integrate_main` (follow-up commit). The composition axis under test.
- `ci-security.json` compliance-snapshot IO boundary — but this change only
  classifies/stages its **path**; it does not parse or serialise the file. No
  `touches_io_boundary` producer/consumer keyword is added.

## Acceptance Criteria

1. `regenerate_tracked_snapshots` records `ci-security.json` as `regenerated` in
   its `out` map when `_update_compliance` runs successfully, and **stages** it
   when it exists on disk.
2. When a fresh `_update_compliance` REWRITES `ci-security.json`, the rewrite is
   staged and reaches the `integrate_main` regenerate follow-up **commit** — the
   working tree is clean afterwards (no modified-but-unstaged summary).
3. When `_update_compliance` leaves `ci-security.json` untouched (fail-soft, no
   fresh scan), it is **not** staged into a phantom follow-up commit (`git add`
   on an unchanged file is a no-op) — the common case is unchanged.
4. Net-neutral on `resolve_churn_conflicts.py` (still 357 lines) — the
   anti-ratchet gate stays green; no baseline edit.
5. The pre-existing `test_regenerate_invokes_canonical_producers_and_stages`
   (asserts exactly 5 staged compliance files) stays green — ci-security is only
   staged when it exists, so a compliance dir without it is unaffected.

## Confidence Calibration

- **Boundaries touched:** `resolve_churn_conflicts.regenerate_tracked_snapshots`
  (one loop-set widened + one import), exercised through `integrate_main.integrate`.
  No serialise/parse of `ci-security.json`.
- **Empirical probes run:**
  - Traced the drop: `_update_compliance` (`finalize_iterate.py:183`) iterdir-returns
    the whole `.shipwright/compliance/` dir incl. `ci-security.json`, but the
    `for rel in sorted(COMPLIANCE_MDS)` loop records only the 5 `.md` files → the
    `.json` never enters `out` → the `staged` filter never sees it. Confirmed RED.
  - Confirmed the fix mirrors the #375 rollback set `DERIVED_MDS |
    {CI_SECURITY_SUMMARY}` (`integrate_main.py:180`).
  - Confirmed `git add` on an unchanged tracked file is a no-op → no phantom
    commit in the fail-soft case (Test AC-3 pins it).
  - Verified the pre-existing 5-file staging assertion still holds because that
    test's fixture never creates `ci-security.json` (AC-5, Test carry-over).
- **Test Completeness Ledger:**

  | Behavior (AC) | Disposition | Evidence |
  |---|---|---|
  | AC-1 record + stage ci-security on rewrite | `tested` | `test_ci_security_forward_staging.py::test_regenerate_stages_ci_security_when_rewritten` |
  | AC-2 fresh scan reaches integrate follow-up commit, clean tree (integration) | `tested` | `test_ci_security_forward_staging.py::test_ci_security_fresh_scan_reaches_followup_commit` (real-git, `category:"integration"`) |
  | AC-3 fail-soft no-scan → no phantom staging | `tested` | `test_ci_security_forward_staging.py::test_regenerate_does_not_stage_unchanged_ci_security` |
  | AC-4 net-neutral 357 LOC / anti-ratchet green | `tested` | `bloat-check.yml` CI + local `anti_ratchet_check.py` (F0 gate) |
  | AC-5 5-file staging assertion preserved | `tested` | pre-existing `test_resolve_churn_conflicts.py::test_regenerate_invokes_canonical_producers_and_stages` (regression, re-run at F0) |

  0 testable-but-untested behaviors.
- **Confidence-pattern check:**
  - *Asymptote (depth):* the drop is reproduced against the real `out`/`staged`
    code path and the fix verified through the real `integrate_main.integrate`,
    not asserted from memory.
  - *Coverage (breadth):* unit (record+stage) + safety (fail-soft no-phantom) +
    **integration composition** (real-git integrate follow-up) + regression
    (existing 5-file assertion) + gate (anti-ratchet net-neutral).
  - *Integration composition:* AC-2 is the `category:"integration"` behavior the
    `cross_component` flag requires — proving `churn_merge` ⊕
    `regenerate_tracked_snapshots` ⊕ `integrate_main` compose on the fresh-scan
    forward-staging path. The F11 `check_integration_coverage` recomputes the flag
    from the diff and STOPs without it.
- **Empirical red→green proof:** all 3 tests were run against the pre-fix code
  (fix stashed) and FAILED (AC-1/AC-3 at `out.get(ci-security) == "regenerated"`;
  AC-2 with `steps == ['fetched','merge-committed','regenerate-noop']` and a dirty
  tree — the exact bug), then PASS post-fix. Full shared suite green at F0
  (4167 passed / 12 skipped).

## External review disposition (GPT-5.4 + Gemini 3.1 Pro, `--mode code`)

- **GPT-5.4:** "No concrete defects found … ship-as-is." Confirmed the existence
  guard prevents phantom staging and the LOC-neutral restructuring preserves the
  ADR-099 ceiling.
- **Gemini 3.1 Pro:** verification walkthrough (confirmed `CI_SECURITY_SUMMARY`
  import source + the whole-block success/fail parity); no defect raised.

## Internal review disposition (shipwright-build code-reviewer + doubt-reviewer, opus)

- **Code-reviewer:** no blocking findings — "correct, net-neutral, and genuinely
  well-tested." Verified out→staged→follow-up-commit, the 5-file regression stays
  green, and the compliance-fail path marks all six `error` together (symmetric
  with the rollback set).
- **Doubt-reviewer (biased-to-disprove):** no HIGH/blocking defect; the two
  highest-risk objections DISPROVEN (#6 timestamp drift — no wall-clock field,
  deterministic `sort_keys`; #1 phantom/empty commit — `_has_staged_changes` guard
  + fail-soft SKIP-without-write). 3 LOW advisories, all dispositioned:
  1. *Spec-framing (clean no-op optimism):* ADOPTED — refined above; on
     gh-available machines a genuinely newer run legitimately commits a refresh
     (desired, not churn).
  2. *CRLF cross-platform flip:* NEUTRALIZED — `core.autocrlf=true` is set;
     verified the committed `ci-security.json` AND sibling `dashboard.md` index
     blobs are LF-only. Pre-existing + shared with the five `.md` producers; no
     `.gitattributes` change (a repo-wide `eol=lf` is a separate, broader concern).
  3. *Rollback can't un-create a brand-new untracked ci-security.json:*
     ACKNOWLEDGED — pre-existing from #375's rollback set (shared with
     `DERIVED_MDS`), not reachable in the error path of THIS change
     (`outcome=='error'` is never staged), and not realizable in a repo that
     already tracks `ci-security.json` (the norm). Out of scope.
