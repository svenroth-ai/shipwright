# Mini-Plan: bloat-review (Campaign A.review)

- **Run ID:** iterate-2026-05-25-bloat-review
- **Spec:** `.shipwright/planning/iterate/2026-05-25-bloat-review.md`

## Approach

Three independent file groups + one registry-wire:

1. **Reviewer prompts** — append `## Bloat Checklist` section to two
   `.md` files with verbatim-cited external content + Shipwright rules
   + attribution footer.
2. **Compliance audit Group H** — new `group_h.py` (≤300 LOC, struct
   analog `group_e.py`) producing five Finding classes from
   `shipwright_bloat_baseline.json` data.
3. **Tests** — `test_audit_group_h.py` for the audit, plus a
   parity-drift test for the two reviewer files.
4. **Registry wire** — `_registry.py` import + `register_group`
   letter-set update.

TDD order: tests first (RED), implementation (GREEN). Reviewer-prompt
parity test is the drift-protection that catches future divergence.

## Files

### Modify

- `plugins/shipwright-build/agents/code-reviewer.md` (+~80 LOC at end)
- `plugins/shipwright-iterate/agents/sub-iterate-runner.md` (+~80 LOC at end)
- `plugins/shipwright-compliance/scripts/audit/_registry.py`
  (+3 LOC: import + register)
- `plugins/shipwright-compliance/scripts/audit/audit_detector.py`
  (1-line change: add `"H"` to the valid letter set in `register_group`)

### Create

- `plugins/shipwright-compliance/scripts/audit/group_h.py` (≤300 LOC).
- `plugins/shipwright-compliance/tests/test_audit_group_h.py` (~250 LOC).
- `plugins/shipwright-iterate/tests/test_reviewer_bloat_checklist_parity.py`
  (~80 LOC — drift-protection: code-reviewer.md vs sub-iterate-runner.md).

## Bloat Checklist content (shared between AC-1 + AC-2)

Three sub-blocks rendered identically into both reviewer files:

### Block 1 — Karpathy 4 principles (verbatim citation)

Text source: [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills),
MIT licensed © 2025 multica-ai. The four principles are
**Think Before Coding**, **Simplicity First**, **Surgical Changes**,
**Goal-Driven Execution**. Verbatim text (~20 LOC).

### Block 2 — Osmani Five-Axis-Review header + Change-Sizing + rules

Text source: [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills)
`skills/code-review-and-quality/SKILL.md`, MIT licensed © Addy Osmani.
Includes Five-Axis-Review-Header keywords, Change-Sizing table
(100 / 300 / 1000 LOC), "Separate refactoring from feature work" rule,
Dead-Code-Artifact check (no `_unused` symbols, no `// removed` comments
left in the diff). Verbatim text (~30 LOC).

### Block 3 — Shipwright-own rules

- **Allowlist-Diff** — if the change pushes a file's LOC over its
  limit, the file MUST already exist in `shipwright_bloat_baseline.json`
  OR the change MUST split it. A new crossing in a new file
  requires either splitting or an ADR-promoted exception.
- **Anti-Ratchet** — bumping `current` upward in
  `shipwright_bloat_baseline.json` is a contract violation. The
  baseline records grandfathered crossings, not a sliding ceiling.
- **No new violations without ADR** — `state: exception` requires
  `adr: ".shipwright/planning/adr/NNN-slug.md"`; `state: deferred-plan`
  requires `plan_ref: ".shipwright/planning/iterate/..."`.

### Attribution Footer

```
---

External rule sources cited verbatim above:
- [multica-ai/andrej-karpathy-skills](https://github.com/multica-ai/andrej-karpathy-skills) — Karpathy 4 Principles (MIT, © 2025 multica-ai)
- [addyosmani/agent-skills](https://github.com/addyosmani/agent-skills) — `code-review-and-quality` Five-Axis-Review + Change-Sizing + Dead-Code (MIT, © Addy Osmani)
```

## Group H — Finding contract

```python
# Input: shipwright_bloat_baseline.json (via bloat_baseline.load)
#
# H1 Drift           — for each (limit, current, state="grandfathered") entry whose path's
#                      on-disk current > entry.limit AND path NOT in baseline: status=fail.
#                      Actually: enumerate via bloat_baseline.scan(project_root) → "oversize
#                      tracked files that NEED to be in baseline"; subtract paths already in
#                      baseline. Remainder = H1 fail.
# H2 Ratchet-Suggest — for each baseline entry: actual = newline_count(entry.path); if
#                      actual < entry.current → fail (baseline ratcheted up artificially).
# H3 Anti-Ratchet    — for each baseline entry with state == "anti-ratchet": fail HIGH.
#                      (Anyone setting that state explicitly committed a bypass.)
# H4 Exception-no-ADR — entry.state == "exception" AND entry.adr in (None, ""): fail.
# H5 Deferred-no-Plan — entry.state == "deferred-plan" AND entry.get("plan_ref") in
#                      (None, ""): fail.
#
# Skip rule: bloat_baseline.load() returns None → emit single H0 skip Finding (greenfield/
# pre-adopt/corrupt baseline → fail-open, mirror existing pattern in bloat_gate_on_stop).
```

## Tests (RED → GREEN)

`test_audit_group_h.py` (created RED → passes GREEN):

1. `test_h0_skip_when_baseline_missing` — no `shipwright_bloat_baseline.json`
   → single H0 skip finding.
2. `test_h1_drift_flags_oversize_file_not_in_baseline` — tmpdir with
   a 400-LOC source file + baseline that doesn't list it → H1 fail.
3. `test_h1_pass_when_oversize_file_is_grandfathered` — same file IS
   in baseline → H1 pass.
4. `test_h2_ratchet_suggestion_when_current_exceeds_actual` — baseline
   has `current=500`, file is actually 380 LOC → H2 fail (suggest
   `current=380`).
5. `test_h3_anti_ratchet_flags_state` — baseline carries one entry
   with `state="anti-ratchet"` → H3 fail HIGH.
6. `test_h4_exception_without_adr` — entry `state="exception"`,
   `adr=null` → H4 fail.
7. `test_h4_exception_with_adr_passes` — same but `adr="path"` → H4 pass.
8. `test_h5_deferred_plan_without_plan_ref` — `state="deferred-plan"`,
   no `plan_ref` → H5 fail.
9. `test_all_findings_are_detective_only_and_group_h` — group tag
   parity check.

`test_reviewer_bloat_checklist_parity.py`:

10. `test_bloat_checklist_section_present_in_both_files` — anchor on
    `## Bloat Checklist` heading.
11. `test_bloat_checklist_content_byte_identical_between_reviewers` —
    extract section body from both files, byte-compare.
12. `test_attribution_footer_present_in_both_files` — both files end
    with the External-References footer linking to karpathy + osmani
    repos.

## Test strategy

- Group H tests use `tmp_path` + direct JSON file construction
  (no git involvement — only consume `shipwright_bloat_baseline.json`).
- Reviewer-parity tests use `Path(__file__).resolve()` walks up to
  repo root then reads the two reviewer .md files.
- All tests must pass `pytest --color=no` at F0.

## Alternative approaches considered

1. **Replace existing Group G with bloat-G1..G5** — rejected by user;
   would lose 17 passing detective tests (G2 commit-scope, G3 ADR-refs).
2. **Extend Group G with G4..G8** — rejected; the new findings semantically
   belong to a different domain (bloat policy, not commit hygiene).
3. **Put bloat audit under Group A or D** — those groups have their
   own internal coherence (A=artifact integrity, D=event-log FR
   coverage). Bloat is its own concern and deserves its own letter.
4. **Encode reviewer rules as automated lints** — out of scope. The
   rules are "rule-base headers" for the human/LLM reviewer; an
   automated checker would be a separate iterate (and partly already
   exists via `check_file_size.py` + `bloat_gate_on_stop.py`).

## Risks / Mitigations

- **Risk:** the verbatim Karpathy + Osmani text drifts in the upstream
  repos. **Mitigation:** the attribution footer references the source
  repos; the iterate ADR records the snapshot date. If upstream
  evolves materially, a future iterate refreshes the verbatim block —
  the framework guarantees the source attribution, not eternal text-parity.
- **Risk:** `audit_detector.register_group`'s hardcoded letter set
  rejecting `"H"` silently breaks group registration with a misleading
  `ValueError`. **Mitigation:** explicit 1-line widening of the set is
  part of AC-5; a test asserts `register_group("H", ...)` succeeds.
- **Risk:** test fixture creates a baseline with a state value
  (`"deferred-plan"`) that the writer-side never produces. **Mitigation:**
  this is by design — the audit's job is to surface that state IF
  someone (operator / future iterate) ever sets it. The test fixture
  documents the forward-looking contract.
