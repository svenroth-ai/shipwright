# Iterate Spec: bloat-review (Campaign A.review)

- **Run ID:** iterate-2026-05-25-bloat-review
- **Type:** feature
- **Complexity:** medium
- **Status:** draft

## Goal

Implement Campaign A.review (A4 + A5 from
`.shipwright/planning/campaigns/2026-05-21-bloat-cleanup-A-prevention.md`):
extend the two subagent-reviewer prompts (`code-reviewer.md`,
`sub-iterate-runner.md`) with a verbatim-cited Bloat-Checklist section
(Karpathy 4 principles + Osmani Five-Axis-Review-Header / Change-Sizing
/ "Separate refactoring from feature work" / Dead-Code-Artifact check +
Shipwright-eigene rules), and add a new compliance audit Group **H**
producing five bloat-related findings (H1–H5).

> **Letter collision resolved upstream (2026-05-25, this run).** The
> campaign spec says "create new `group_g.py`", but `group_g.py` already
> exists (commit 423f702, plan v7 Step 8: G2 commit-scope + G3 ADR-refs;
> 17 passing tests). User chose "Use Group H for bloat" rather than
> replace or extend Group G. The audit semantics in the campaign are
> preserved; the letter changes from G→H. Documented in the iterate ADR.

## Acceptance Criteria

- [ ] **AC-1** — `plugins/shipwright-build/agents/code-reviewer.md`
  carries a `## Bloat Checklist` section appended at the end (before
  any pre-existing attribution footer), with three sub-blocks:
  - Karpathy 4 principles (verbatim, ~20 LOC, source attributed to
    multica-ai/andrej-karpathy-skills MIT © 2025 multica-ai)
  - Osmani Five-Axis-Review header + Change-Sizing 100/300/1000 table
    + "Separate refactoring from feature work" rule + Dead-Code-
    Artifact check (verbatim, ~30 LOC, source attributed to
    addyosmani/agent-skills `code-review-and-quality` MIT © Addy Osmani)
  - Shipwright-own rules: Allowlist-Diff, Anti-Ratchet detection, new
    violations without ADR
  Attribution footer at end of file links to both source repos.
- [ ] **AC-2** — `plugins/shipwright-iterate/agents/sub-iterate-runner.md`
  carries the same `## Bloat Checklist` section with identical
  three-block content + attribution footer. Verbatim parity with AC-1
  (drift-protection: a parametrized test asserts the two files'
  Bloat-Checklist sections are byte-identical except for the file-local
  surrounding context).
- [ ] **AC-3** — `plugins/shipwright-compliance/scripts/audit/group_h.py`
  exists, ≤300 LOC, structured analog to `group_e.py`. Produces six
  Finding classes (H6 added per external-review #1 / #5 — never crash
  on missing baseline-entry paths):
  - **H1 Drift** — files currently over their LOC limit and NOT in
    `shipwright_bloat_baseline.json` → `status="fail"` (hook bypass).
    Reuses `bloat_baseline.scan(project_root)` for enumeration + LOC
    semantics so the audit can never disagree with the producer.
  - **H2 Ratchet-Suggestion** — entries in baseline with `current` value
    above the actual on-disk LOC (the file shrank, baseline didn't
    update) → `status="fail"` MEDIUM, suggests `current=<actual>`.
    Uses `bloat_baseline._file_newlines` (same producer routine), not a
    parallel newline counter.
  - **H3 Anti-Ratchet** — entries with `state="anti-ratchet"` visible in
    the baseline → `status="fail"` HIGH (means `--no-verify`-style
    bypass occurred and was committed).
  - **H4 Exception-no-ADR** — entries with `state="exception"` but
    `adr` field is missing/null → `status="fail"`.
  - **H5 Deferred-no-Plan** — entries with `state="deferred-plan"` but
    `plan_ref` field is missing/null → `status="fail"`.
  - **H6 Stale-Entry** — entries whose `path` does not exist on disk
    (renamed/deleted) → `status="fail"` MEDIUM, suggests removing the
    entry. Prevents H2 from crashing on missing files (external-review
    #1/#5).
  Findings tagged `source="detective-only"`, `group="H"`.
  Baseline state semantics:
  - **Absent baseline file** → emit single H0 skip Finding
    (greenfield/pre-adopt).
  - **Malformed baseline file** (file exists but `load()` returns None)
    → emit single H0 fail Finding (real misconfiguration, do NOT
    silently mask — external-review #4).
  Path-traversal guard: every baseline-supplied `path` must resolve to
  a child of `project_root`; entries that escape are reported as H6
  fail with detail `"path escapes project_root"`.
- [ ] **AC-4** — `plugins/shipwright-compliance/tests/test_audit_group_h.py`
  exists with one test per finding class (H1–H6 = 6 tests) plus:
  - H0 absent-baseline → skip test
  - H0 malformed-baseline → fail test (external-review #4)
  - tags/group-letter detective-only test
  - integration test through real `bloat_baseline.load()` (not in-memory
    dict — external-review #10)
  - registration test (`register_group("H", ...)` succeeds + appears in
    `audit_detector.registered_groups()` — external-review #9).
  Total ≥11 tests. Style mirrors `test_audit_group_e.py` /
  `test_audit_group_g.py`.
- [ ] **AC-5** — Group H is registered in
  `plugins/shipwright-compliance/scripts/audit/_registry.py` and
  `audit_detector.register_group` accepts `"H"` as a valid letter.
- [ ] **AC-6** — **No modification to `phase_quality.py`** (campaign's
  hard constraint; dashboard column ships with B3 later). The audit
  produces JSON data only.
- [ ] **AC-7** — Probe iterate proofs (live, this run):
  - A probe diff that introduces a new bloat violation without
    allowlisting it produces an H1 fail in the audit.
  - A probe diff that mixes refactor + feature in one commit triggers
    the Osmani "Separate refactoring from feature work" rule when
    surfaced through `code-reviewer.md` (manual demonstration via spec
    review — the rule's text presence in the reviewer prompt is the
    structural enforcement; behavioral rejection is downstream when
    the reviewer subagent runs).
  - A probe diff with `_unused` artefacts or `// removed` comments
    triggers the Osmani Dead-Code rule (same demonstration pattern).
  Documented in the iterate ADR's "Probe Evidence" section.

## Spec Impact

- **Classification:** none
- **NONE justification:** No FR table touched. This iterate adds
  internal compliance tooling + reviewer-prompt content; both are
  framework infrastructure (`change_type: infra` for F7), not
  user-visible application features. The campaign's overall goal is
  enforcement of an internal coding-policy invariant, not a product
  capability change.

## Out of Scope

- **No touch to `phase_quality.py`** — campaign's hard "Doppel-Churn-
  Vermeidung" rule (Codex Finding #11). Dashboard wiring lands with B3.
- No new pre-commit / CI workflow (those land in A.defense).
- No constitution.md update (lands in A.defense via Phase-D acceptance).
- No baseline-schema migration. H4/H5 audit *future* states
  (`exception`, `deferred-plan`) that may or may not yet exist in any
  real baseline; current baselines only carry `grandfathered`. The
  audit fires only when an operator sets those states going forward.
- No retroactive ADR-NNN assignment for the existing decision-drop
  process (handled by /shipwright-changelog at release).

## Design Notes

n/a (no UI changes).

## Affected Boundaries

| Producer (writes)                      | Consumer (reads)                              | Format |
|---|---|---|
| `bloat_baseline.scan` / `bloat_baseline.write_baseline` | `group_h.run` (loads via `bloat_baseline.load`) | `shipwright_bloat_baseline.json` |
| Iterate authors (markdown text)        | `code-reviewer.md` Bloat-Checklist section consumer (the subagent at review time) | Markdown reviewer-prompt |
| Same text (copy of AC-1)               | `sub-iterate-runner.md` consumer              | Markdown reviewer-prompt |

The reviewer-prompt boundary is human-author → LLM-runtime. The
Bloat-Checklist parity between the two reviewer files is enforced by a
byte-compare test (the verbatim-attribution invariant).

## Verification

- **Surface:** cli
- **Runner command (F0.5-compatible, shell-free):**
  `uv run --directory plugins/shipwright-compliance pytest tests/test_audit_group_h.py --color=no`
  (the orchestrator runs the command without `shell=True`, so
  `cd ... && ...` chains do not work — `--directory` is the
  shell-free equivalent for plugin-scoped pytest invocations.)
- **Evidence path:** `.shipwright/runs/iterate-2026-05-25-bloat-review/surface_verification.log`
- **Plus drift-protection probe:** `uv run pytest shared/tests/test_reviewer_bloat_checklist_parity.py -v --color=no`
  (relocated from `plugins/shipwright-iterate/tests/` to `shared/tests/`
  per external-review #6 — the test reaches into two different plugins
  so its natural home is the shared test suite.)

The audit's behavior is library-CLI: the runner exercises group_h.run
end-to-end against constructed baseline fixtures via pytest. There's
no startable web/api surface.

## Confidence Calibration

- **Boundaries touched:** `shipwright_bloat_baseline.json` (machine-
  written by scan/baseline_generator, machine-read by group_h);
  reviewer-prompt markdown files (human-written, LLM-read).
- **Empirical probes run:**
  1. RED→GREEN cycle: ImportError before group_h.py existed → 14/14 pass after.
  2. Round-trip probe (`test_integration_through_real_baseline_load`):
     JSON written to disk → `bloat_baseline.load()` reads it → H2 finding
     produced with correct `actual=380`.
  3. Path-traversal probe (`test_h6_flags_path_escaping_project_root`):
     `../escape.py` baseline entry → H6 fail (Gemini #5 / OpenAI #12).
  4. Malformed-input probe (`test_h0_fail_when_baseline_malformed`):
     `{not json` content → H0 fail (not silent skip — OpenAI #4).
  5. Stale-entry probe (`test_h6_flags_missing_file_in_baseline`):
     non-existent path → H6 fail, no crash on subsequent checks
     (Gemini #1 / OpenAI #5).
  6. Registration probe (`test_register_group_accepts_letter_h`):
     exercised the hardcoded letter-set widening in `audit_detector`.
  7. Parity probe (5 tests in `shared/tests/`): byte-compare extraction
     between `code-reviewer.md` and `sub-iterate-runner.md` is identical
     (Gemini #3 / OpenAI #7+#8).
  8. Full-suite regression probe: 528 compliance + 2396 shared = 2924
     tests pass. Surfaced 2 hardcoded letter-set assertions in sibling
     tests; both fixed by adding `"H"`.
- **Edge cases NOT probed + why acceptable:**
  - Non-list `entries` field → `bloat_baseline.load()` returns None
    via existing producer-side fail-open. H0 emits fail.
  - Non-string `state` field → falls through to `entry.get != value`
    comparison; never crashes. Writer never produces this shape.
  - Empty `entries=[]` baseline → H1 fires if any oversize file
    exists; covered by `test_h1_flags_oversize_file_not_in_baseline`.
- **Confidence-pattern check:** no "yes/no confidence" question fired-
  then-found-bug in this run. Two regression findings (registry-letter-
  set + sibling test count) surfaced empirically through test runs, not
  self-attestation. Asymptote reached.

## External-Plan-Review-Findings (Step 4)

Run via `external_review.py --mode iterate` (provider: openrouter,
17 findings across Gemini 5 + OpenAI 12). See ADR for full disposition.

| Severity | Finding | Disposition |
|---|---|---|
| HIGH (G1)  | H2 crashes on deleted/renamed paths | accepted-and-fixed: added H6 Stale-Entry class |
| MED (O1)   | H1 ambiguity: scan vs baseline state filter | accepted-and-fixed: pseudocode + test clarify; H1 fires regardless of baseline-entry states |
| MED (O2/O3)| LOC metric drift between writer + audit | accepted-and-fixed: reuse `bloat_baseline.scan` + `_file_newlines` directly |
| MED (O4)   | Malformed baseline should fail, not skip | accepted-and-fixed: H0 distinguishes absent (skip) vs malformed (fail) |
| MED (O5)   | Missing-file handling for H2/H3/H4/H5 | accepted-and-fixed: `_partition_entries` quarantines into H6; downstream checks see only resolvable entries |
| MED (G2)   | Reviewer-prompt token budget | rejected-with-reason: code-reviewer.md 174→273, sub-iterate-runner.md 382→481 LOC; well within model headroom |
| MED (O9)   | Registration test, not just unit findings | accepted-and-fixed: `test_register_group_accepts_letter_h` |
| MED (O10)  | Integration through real `load()` | accepted-and-fixed: `test_integration_through_real_baseline_load` |
| LOW (G3)   | Parity extraction boundaries | accepted-and-fixed: explicit `## Bloat Checklist` start + `<!-- /Bloat Checklist -->` end marker |
| LOW (G4)   | Global LOC for files not in baseline | accepted-and-fixed (already): H1 reuses producer `scan()` which carries `limit` per-file |
| LOW (G5/O12)| Path-traversal guard | accepted-and-fixed: `_resolve_under_root` checks `relative_to(project_root)` |
| LOW (O6)   | Parity test cross-plugin reach | accepted-and-fixed: relocated from `plugins/shipwright-iterate/tests/` to `shared/tests/` |
| LOW (O7/O8)| Footer duplication risk | accepted-and-fixed: section is self-contained with explicit markers |
| LOW (O11)  | Record snapshot date in attribution | accepted-and-fixed: footer carries `snapshot 2026-05-25` |

## Notes

- The campaign already prepared the External-References block in its
  header table (Karpathy MIT, Osmani MIT, Superpowers MIT, Multica
  out-of-scope). This iterate verbatim-copies the source text into the
  reviewer prompts and adds an Attribution footer linking back to the
  source repos.
- All review-rule text is "rule-base header" content — the reviewer
  subagent reads these rules and applies them; the iterate does NOT
  encode them as automated lints (that's not the scope here).
