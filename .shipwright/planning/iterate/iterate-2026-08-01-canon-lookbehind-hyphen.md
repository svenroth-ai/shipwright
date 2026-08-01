# Iterate Spec: canon-lookbehind-hyphen

- **Run ID:** iterate-2026-08-01-canon-lookbehind-hyphen
- **Type:** bug
- **Complexity:** medium
- **Status:** draft

## Goal

The Layer-1 artifact-path-canon lint reports a legitimate source path as a
legacy-artifact reference whenever the directory name is *hyphen-suffixed* with a
migrated dirname — `plugins/shipwright-compliance/tests/x.py` reads as a bare
`compliance/` reference. Close that hole in the negative lookbehind so the gate
stops accusing correct paths, giving up no real legacy-path detection — not even
the leading-hyphen forms a wider fix would have cost.

## Acceptance Criteria

- [ ] **AC-1 (the false positive is gone).** For every migration in
  `ARTIFACT_MIGRATIONS`, no `old_path_patterns` entry matches a path whose
  legacy dirname is preceded by a hyphen CONTINUING A WORD — POSIX
  (`plugins/shipwright-compliance/tests/x.py`, `shipwright-compliance/tests`)
  and Windows (`plugins\shipwright-compliance\tests\x.py`) forms alike, and for
  the hyphen-suffixed form of *each* migrated dirname, not just `compliance`.
- [ ] **AC-2 (real detection is preserved).** A bare legacy reference still
  matches for every migration, POSIX and Windows: `planning/…`, `designs/…`,
  `agent_docs/…`, `compliance/…` and their backslash forms — **and so does a
  leading-hyphen form** (`-planning/…`, `- planning/…`), which the narrower
  guard deliberately keeps detectable.
- [ ] **AC-3 (canonical form stays clean).** `.shipwright/compliance/…` and the
  sibling canonical paths remain unmatched — the pre-existing `/` lookbehind is
  not disturbed.
- [ ] **AC-4 (no repo-wide regression).** `test_no_legacy_artifact_paths` passes
  for all four migrations against the real tracked tree, and the full
  `shared/tests` root is green.
- [ ] **AC-5 (the workaround is retired where this fix emptied it).** An
  `ALLOWLIST` entry is retired iff it **measured non-zero before the fix and
  zero after** *and* its recorded rationale named only the hyphen-suffixed
  plugin path. Entries that were already zero beforehand are pre-existing
  defensive exemptions, not something this change emptied, and are out of scope.
  Entries the fix emptied but which hold a standing basis of their own —
  generated artifacts that cannot carry an inline marker — are kept, and every
  surviving comment that asserted the false positive is live is corrected. The
  repo-wide lint stays green with the removals in place.
- [ ] **AC-6 (the inverted regression test is repurposed, not deleted).**
  `test_artifact_path_canon_manifest_allowlist.py` asserted that the false
  positive is *real*; after this change it asserts the opposite invariant — a
  manifest-rendered hyphenated plugin test id trips no migration — and it fails
  if the guard is removed again.
- [ ] **AC-7 (the decision reversal is recorded with its evidence).** The
  decision drop names **every** prior rejection of this fix found in the record —
  `decision_log.md:571`, `decision_log.md:1353`, ADR-091, and **ADR-080
  (`decision_log.md:1157`)** — and answers each on its own stated grounds, not
  on a count. The first three object to *breadth*; ADR-080 objects on a
  different axis (that a hyphen-preceded path could itself be legacy,
  e.g. `pre-planning/`) and must be answered separately. The reversal is
  auditable rather than a silent contradiction of the record.

## Spec Impact

- **Classification:** none
- **ADD:** none
- **MODIFY:** none
- **REMOVE:** none
- **NONE justification:** a bug fix restoring the lint's intended behaviour. No
  FR describes the negative-lookbehind character class; the gate's *contract*
  ("no legacy artifact-path references outside the allowlist") is unchanged —
  only its accuracy against that contract improves. BUG iterates are not gated
  by the F11 spec-impact verifier (`references/path-c-bug.md` Step 2).

## Out of Scope

- **A general `ALLOWLIST` purge.** Measured: 126 of the currently-exempt files
  still trip under the fixed patterns (prose like `compliance/security`,
  `"compliance"` enum values, `compliance/drift`). The allowlist was never
  holding back only this false positive, so retiring it wholesale is a separate
  change with its own risk. Only entries **this fix emptied** go — see AC-5.
- **Exemptions that already measured zero before this change.** 35 entries
  measure zero today, but 23 of them measured zero beforehand too: they are
  stale or defensive for reasons that predate this bug (the migration
  framework's own by-design references, `CHANGELOG-unreleased.d/**`,
  `plugins/shipwright-adopt/tests/**`, a plan glob pointing at another machine's
  home directory). Auditing those is a real cleanup, and a separate one — this
  change may not claim credit for emptying what it did not empty.
- **The `_COMMON_ALLOWLIST` dedupe** deferred by ADR-091. Still deferred.
- **The `"planning"` / `'planning'` quoted-literal patterns.** They cannot carry
  this false positive (a hyphen before the opening quote says nothing about the
  string's contents), so they are deliberately left alone — see Design Notes.
- **Any change to the AST scanner or the drift detector.** Neither is affected;
  the structural protection against a legacy directory actually existing on disk
  lives in `stale_artifact_detector.py` and is untouched.

## Design Notes

**Root cause.** The negative lookbehind `(?<![\w/.\\])` enumerates the
characters that, when they precede the dirname, mean "this is not a *bare*
reference". It covers word characters, `/`, `.` and `\` — but not `-`, which is
a legal intra-name character and, in this repo, the separator in all fourteen
`shipwright-*` plugin directories. So any directory whose name *ends* in a
migrated dirname after a hyphen reads as a bare legacy reference.

**Why `(?<!\w-)` and not `-` inside the class.** The obvious fix is to widen the
class to `[-\w/.\\]`. That works, but it suppresses a match after *any* hyphen —
including one that starts a token. `-planning/spec.md`, the shape a unified-diff
removal line or an unspaced list marker produces, would silently stop being
detected. The defect is only ever `<word>-<dirname>`, so the guard says exactly
that: `(?<!\w-)` excludes a hyphen that **continues a word** and nothing else.
Measured against the tree, the wide form drops 1,855 matches over 5 tokens and
the narrow form 1,840 over 4 — the difference is precisely the 12 bare
`-compliance/` occurrences the wide form would have stopped catching.

This is not a stylistic preference. **Breadth of weakening is the exact axis on
which three of this fix's four prior rejections rest** ("would globally weaken
legacy-path detection"). A reversal that answers that objection with the widest
available form would be conceding the point while overriding it. Both lookbehinds
are fixed-width and legal in Python `re`; the new match set is still a strict
subset of the old, so "no true positive lost" remains a one-line argument. (The
fourth, ADR-080, objects on a different axis and is answered below on its own.)

**Why only the two separator patterns change.** Each migration carries four
patterns. Patterns 1–2 (`<dirname>/`, `<dirname>\`) anchor on a path separator
and are the ones a hyphenated *directory name* reaches. Patterns 3–4 match the
quoted literals `"<dirname>"` / `'<dirname>'`, where the lookbehind sits before
the opening quote — a preceding hyphen there carries no information about the
string's contents and `"shipwright-compliance"` cannot match `"compliance"`
anyway. Adding the guard there would be inert, so it is not added: each
lookbehind means something specific in its position.

**Registry consumers** (no serialized format, so `touches_io_boundary` does not
fire): `old_path_patterns` is read by `shared/tests/test_artifact_path_canon.py`
(the lint), `shared/tests/test_path_canon_windows.py` (Layer 7 cross-platform)
`shared/tests/test_path_canon_hyphen_guard.py` (the guard's own module, split
out of the Windows one in this change) and
`shared/tests/test_artifact_path_canon_manifest_allowlist.py`. There is no
second copy of the pattern text anywhere in the tree — verified by grepping the
literal lookbehind, which returns the manifest plus prose describing it.

**This reverses a recorded decision, four times over.** The same fix was
rejected in 2026-05 and again in 2026-06. The fourth was found only by the
Stage-3 adversarial pass — the first three enumerations of this table missed it:

| Record | Stated reason for rejecting the regex fix |
|---|---|
| `decision_log.md:571` | "would change semantics of the path canon for ALL files, higher blast radius than per-file allowlist" |
| `decision_log.md:1353` | "would globally weaken legacy-path detection" |
| ADR-091 (rejected alternatives) | "Regex loosening globally weakens legacy-path detection (masks real bugs)" |
| **ADR-080 (`decision_log.md:1157`)** | "would silently allow real legacy paths after a hyphen (e.g. `pre-planning/`)" |

**The first three rest on one empirical claim** — that widening the class loses
real detection. That claim is measurable, and it is false for this repo (see the
Confidence Calibration probes): the change drops 1,840 matches across 156 files,
and every one is one of exactly four tokens, none a legacy artifact path. The
2026-05 reasoning was sound *as an unmeasured prior*; what changed is that it has
now been measured. The narrow guard also concedes their point rather than
overriding it — it gives up strictly less than the wide class they had in mind.

**ADR-080 is a different objection and needs a different answer.** It is the most
on-point record in the tree — it is the ADR that granted the
`finalize_security_compliance.py` exemption this change retires — and it was
missed until the Stage-3 doubt pass found it. Its counterexample is
`pre-planning/`, which the guard *does* suppress, so narrowing buys nothing
here. The answer is that **`pre-planning/` was never a legacy reference.** The
legacy artifact is the path segment `planning` exactly; `pre-planning` is a
different directory, and path segments are atomic — a substring match is not a
path reference. That is the same confusion that made
`plugins/shipwright-compliance/` read as `compliance/` in the first place, so
ADR-080's counterexample is an instance of the very bug being fixed. Checked
empirically: exactly **two** directories in the tree end in `-<migrated dirname>`
— `plugins/shipwright-compliance` and `.shipwright/compliance/skill-compliance`
— and both are legitimate. There is no `pre-planning`, and none can be legacy by
construction.

**What made this newly worth fixing.** The allowlist escape hatch requires
either a file-path entry or an inline `artifact-path-canon: legacy` marker.
`.shipwright/agent_docs/iterates/<run_id>.json` (the F5c entry) is neither
allowlisted nor able to carry an inline marker, because JSON has no comment
syntax — so the first F5c entry to cite a compliance-plugin test had no escape
hatch at all. The workaround on that run was to reword the entry, i.e. to change
what the record *says* to satisfy a broken check.

*The mechanism, since the Stage-3 pass disputed this:* the entry is mostly
scalars, but `test_completeness.behaviors[*].evidence` is free-form prose naming
the test that proves each behavior. That is the field that can carry
`plugins/shipwright-<x>/tests/...`. Verified: 52 tracked entries, and the shape
is confirmed in `iterate-2026-07-30-derived-gate-sees-the-pr.json`. None of the
52 trips the pre-fix patterns, which is consistent with the report that this was
the *first* such entry, not evidence that one is impossible. The directory is
still unexempt, so this run's own F5c prose says "hyphen-suffixed plugin path"
rather than writing the literal.

**Honest limit of the measurement.** The census is a `compliance` census. The
other three migrations have **zero** pre-existing occurrences of the pattern in
the tree — the single `shipwright-planning/` hit is this change's own comment —
so for `planning` / `designs` / `agent_docs` the fix rests on the argument, not
on data. That argument is the same one and it is sound (a hyphenated directory
name is a different directory), but no measurement backs those three, and the
record should not imply otherwise.

## Affected Boundaries

`n/a` — no serialized producer/consumer format changes. The change is confined
to regex literals in a registry module and its three in-repo consumers, all
listed under Design Notes. `touches_io_boundary` does not fire.

## Confidence Calibration

- **Boundaries touched:** none (`n/a` above).

- **Empirical probes run:**
  - *Probe 1 — reproduce.* Applied every migration's live patterns to a
    hand-built sample set. Reproduced the false positive on **all four**
    migrations, POSIX and Windows: `shipwright-planning/x`, `my-designs/x.html`,
    `some-agent_docs/x.md`, `plugins/shipwright-compliance/tests/x.py`,
    `plugins\shipwright-compliance\tests\x.py`. Confirmed
    `.shipwright/compliance/dashboard.md` is correctly *not* flagged, and that
    every bare legacy sample still is. Finding: the defect is general to the
    manifest, not specific to `compliance`.
  - *Probe 2 — blast radius over the real tree.* Ran old-vs-new patterns over
    every git-tracked lintable file, allowlist ignored, and collected every line
    that stops matching. Finding: 1,855 lines across 155 files; zero lines start
    matching (the new class is a strict subset of the old, so this direction is
    impossible by construction and the probe confirms it).
  - *Probe 3 — census of what is actually lost.* Because the new pattern set is
    a strict subset, a line stops matching **iff** every one of its matches was
    hyphen-preceded. Extracted the full token at each dropped match. Finding for
    the first (wide) cut: five tokens — `shipwright-compliance/` (1,826),
    `skill-compliance/` (27), `-compliance/` (11), `shipwright-compliance\` (2),
    `-compliance\` (1). The first is the plugin source tree; the second is a real
    subdirectory *inside* the canonical `.shipwright/compliance/`; the third is
    prose describing this very false positive.
  - *Probe 10 — the same census for the SHIPPED narrow form.* Stage 2 showed the
    wide class was broader than the defect, so the guard became `(?<!\w-)`.
    Re-measured against the true pre-fix pattern: **1,840 lines over 156 files,
    four tokens** — `shipwright-compliance/` (1,822), `skill-compliance/` (27),
    `shipwright-compliance\` (2), `shipwright-planning/` (1). Every one is a
    word continuing into a migrated dirname; the bare `-compliance/` prose
    occurrences are now **retained** as matches, which is the whole point of the
    narrower guard. **Zero true positives lost.** The probe refuses to run unless
    it finds exactly 8 guarded patterns, so it cannot report a vacuous zero.
  - *Probe 4 — which exemptions lose their basis.* Re-ran the lint's own text +
    AST scanners with the fixed patterns and the compliance allowlist emptied.
    Finding: **126 of the exempt files still trip** on independent grounds, so
    the allowlist is not merely a hyphen workaround and must not be purged
    (this is what put the purge Out of Scope).
  - *Probe 5/6 — the full sweep, after Stage 1 rejected the first cut.* The
    first pass named three retired entries from a spot check; the Stage-1
    reviewer found more, and re-measuring **every** compliance allowlist entry
    confirmed it: 51 entries still trip, 35 measure zero. So "measures zero" is
    far too wide a net — most of those 35 were never about the hyphen at all.
  - *Probe 7 — the rule that actually separates them.* An entry belongs to this
    change iff it measured **non-zero before** the fix and **zero after**. That
    is a property of the fix, not of the current tree, and it cuts the 35 down
    to 12. Of those, the seven whose recorded rationale named only the
    hyphen-suffixed plugin path are retired; the rest keep a standing basis
    (generated artifacts, the migration framework's own by-design references,
    and the `.gitignore` entry a Layer-5 test requires to stay present).
  - *Probe 8 — mutation check on the pins.* Flipped the hyphen back out of all
    eight lookbehinds and re-ran the **full runner command** (all three lint
    modules): **13 tests fail**, 0 after restoring. Twelve are the new pins; the
    thirteenth is `test_no_legacy_artifact_paths[compliance-migrated]`, and it
    is the one that matters for AC-5 — it can only fail if the seven retired
    exemptions really are gone, so the count is evidence about the *removals*,
    not just about the pins. The first run of the first version of this probe
    measured only the two pin files and reported 12, which read as if it
    covered both; Stage 1 caught the gap. An earlier attempt reported "reverted
    0 lookbehinds" — a shell-mangled no-op that had produced a full green board
    — so the mutator now exits non-zero rather than report a vacuous pass.
    Six tests correctly survive a revert: they are the positive controls, the
    canonical-form check, the untouched quoted half, and the allowlist-membership
    guard, none of which is a hyphen pin.

- **Test Completeness Ledger:**

  | # | Testable behavior | Disposition | Evidence / reason_code |
  |---|---|---|---|
  | 1 | A hyphen-suffixed dirname does not match, every migration, POSIX form | tested | `test_path_canon_hyphen_guard.py::test_hyphen_suffixed_dirname_is_not_a_legacy_reference` (4 params) |
  | 2 | Same, Windows backslash form, plus the `skill-<dirname>/` shape | tested | same test — samples 3 and 4 |
  | 3 | A bare legacy reference still matches, both separators, every migration | tested | `test_path_canon_hyphen_guard.py::test_bare_legacy_reference_still_matches` + pre-existing `::test_manifest_includes_windows_separator_pattern` |
  | 4 | A hyphen that STARTS a token still matches — `-<dirname>/` and `- <dirname>/` | tested | `test_path_canon_hyphen_guard.py::test_bare_legacy_reference_still_matches` — samples 5 and 6; this is what `(?<!\w-)` buys over the wide class |
  | 5 | The canonical `.shipwright/<dirname>/` form stays unmatched | tested | `test_path_canon_hyphen_guard.py::test_canonical_shipwright_path_is_not_a_legacy_reference` |
  | 6 | The quoted-literal patterns behave exactly as before | tested | `test_path_canon_hyphen_guard.py::test_quoted_literal_patterns_are_unaffected_by_the_hyphen_fix` — scoped to the 2 non-separator patterns, so it cannot pass if that half is deleted |
  | 7 | The guard is on the separator patterns ONLY, and no lookbehind class ends in a bare `-` | tested | `test_path_canon_hyphen_guard.py::test_only_separator_patterns_carry_the_hyphen_guard` |
  | 8 | A manifest-rendered hyphenated plugin test id trips no migration | tested | `test_artifact_path_canon_manifest_allowlist.py::test_manifest_content_trips_no_migration` |
  | 9 | That clearance is *caused by* the guard (non-vacuity) | tested | `..._manifest_allowlist.py::test_the_hyphen_guard_is_what_clears_the_manifest_content` |
  | 10 | The hand-written sample still represents real generated output | tested | `..._manifest_allowlist.py::test_sample_shape_still_occurs_in_the_generated_manifest` — scans the producer-controlled ids only, never the manifest's prose |
  | 11 | Every retired exemption measures zero findings, on BOTH of the gate's legs | tested | `..._manifest_allowlist.py::test_exemptions_the_fix_emptied_are_not_needed` |
  | 12 | Retained exemptions stay allowlisted; retired ones stay out of EVERY migration | tested | `..._manifest_allowlist.py::test_retained_exemptions_stay_allowlisted_and_retired_ones_stay_out` |
  | 13 | The repo-wide lint is green for all four migrations after the removals | tested | `test_artifact_path_canon.py::test_no_legacy_artifact_paths` (4 params) |

- **Confidence-pattern check:**
  - *Asymptote (depth).* Depth was NOT reached on the first pass, and the record
    says so: Stage 1 rejected the first cut, and re-probing confirmed all four
    of its substantive findings. Two of my own new tests then failed on first
    run — one because the helper ignored the inline marker the real lint honours,
    one because the migration-lookup sample could not match — and the mutation
    check caught a third defect in the check itself. Each was a real defect, so
    the depth signal is spent findings, not a self-assessment.
  - *Coverage (breadth).* 13 rows, 13 `tested`, 0 untested-testable.
  - *Integration composition.* `cross_component` does not fire — the diff
    touches no merge/churn resolver, no `hooks/*.py`, no phase validator, no
    campaign driver.

## Verification (medium+)

- **Surface:** cli
- **Runner command:** `uv run --extra dev pytest shared/tests/test_artifact_path_canon.py shared/tests/test_path_canon_windows.py shared/tests/test_artifact_path_canon_manifest_allowlist.py -q`
- **Evidence path:** `.shipwright/planning/iterate/iterate-2026-08-01-canon-lookbehind-hyphen/f0_5_surface.json`
- **Justification (only if surface=none):** n/a — the lint *is* the production
  surface, and running it against the real tracked tree is the end-to-end
  exercise, not a proxy for one.
