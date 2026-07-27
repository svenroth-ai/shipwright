# Iterate: changelog writer must preserve the history it read

- **Run ID:** `iterate-2026-07-27-changelog-writer-preserve-history`
- **Intent:** BUG (critical data loss in a release-path writer)
- **Complexity:** medium (classifier: `estimate=medium`, `prior_source=history`,
  `history_n=20`; keyword estimate was `trivial` and is not upheld — the change
  rewrites a writer that destroys user data and adds an acceptance criterion)
- **Spec Impact:** ADD — `affected_frs = [FR-01.09]` (`/shipwright-changelog`).
  The overwrite defect is **conformance** to the existing (E) criterion
  *"the document's title and older entries are left intact"* (`spec.md:465-467`),
  which the code contradicted. The re-run guarantee is a **new** (E) criterion
  folded into FR-01.09 (FOLD, not MINT — no new FR id; see `shared/fr-authoring.md`).
- **Triage:** `trg-6690d175` (critical). Supersedes `trg-7ad0849b` (title-only
  restatement, so the severity is visible where only a title is shown).
- **Source:** FR-01.09 walk, `.shipwright/planning/campaigns/2026-07-23-req3-ac-evidence-ledger-mono.md:826-874`.

## Problem

`plugins/shipwright-changelog/scripts/lib/changelog.py::update_changelog` reads
the existing `CHANGELOG.md` into `content` and then **rebuilds the output from
fragments** instead of splicing the new entry into what it read. Two of its
three branches omit part of `content`, so the omitted part is written away.

Reproduced empirically (both scenarios below run against the real function):

| # | File shape | Branch | Result |
|---|---|---|---|
| 1 | exists, **no** `## [Unreleased]` marker | `else` (L156-158) | **whole file destroyed** — rebuilt as `CHANGELOG_HEADER + "## [Unreleased]" + entry` |
| 2 | marker present, **no** prior `## [x.y.z]` section | L141-148 | **every pending `[Unreleased]` bullet destroyed** — `rest` is read and discarded |
| 3 | marker present, prior version present | L149-155 | correct (splices) |

**Scenario 1 (the reported defect).** A hand-written history —
`# Release History`, entries down to `## [1.0.0]` — came back containing only
the new entry. `# Release History`, `[1.0.0]`, `[0.9.0]` and their bodies were
all gone. Who this hits: any project whose history file does not use the
`## [Unreleased]` marker — **the normal case for a brownfield repo onboarded
with its own history**, i.e. exactly `/shipwright-adopt`'s target population.

**Scenario 2 (found while probing, not in the original report).** Branch 2 was
recorded as safe. It is not: it keeps `content[:idx]` and drops `rest`, so a
`[Unreleased]` block holding unreleased bullets is erased whenever the file has
no released section yet — a fresh project's first release. It looked safe
because `test_update_changelog_new_file` exercises it with an **empty**
`[Unreleased]`, where there is nothing to lose.

**Scenario 3 (the re-run defect).** Setting the version marker is instruction
(SKILL.md Step 6 `git tag`), not code. A run interrupted between "changelog
written" and "tag created" leaves the note written and unmarked; the next run
recomputes the same version off the same last tag and **inserts it again** —
verified: `occurrences of '## [1.1.0]' = 2`. Nothing in the writer looks for a
section it has already written.

**Root cause (one, not three):** the function reconstructs rather than splices.
Every branch that reconstructs loses whatever fragment it forgot to concatenate,
and no branch consults the file for a section it already wrote.

**Test shape (third time this pattern):** `test_update_changelog_new_file`
covers "no file", `test_update_changelog_existing` covers "file with marker and
a prior version" — the branches that destroy data are the untested ones.

## Design decisions

**Splice, never rebuild.** `update_changelog` computes an insertion index (or
the span of an existing same-version section) and splices the entry into the
text it read. `CHANGELOG_HEADER` is used **only** when the file does not exist.
This makes data loss structurally impossible rather than fixed case-by-case: no
code path can drop a fragment it forgot to re-concatenate, because no path
rebuilds.

**Insertion-point chain** (matches the proven `aggregate_changelog.py`
behaviour, so a file is laid out the same way whichever writer touched it):
1. above the first non-`[Unreleased]` `## [...]` heading;
2. else after the `## [Unreleased]` block;
3. else after the title/header paragraph — *insert at the top, leave the rest
   alone*, which is the decided fix for an unknown file shape;
4. else end of file.

**Re-run replaces that version's section** (`extend or replace`, not append).
Replacement is the deterministic arm: the entry is regenerated from the same
commit range, so the regenerated section is authoritative. One version appears
once, whether the writer runs once or five times.

**Refuse rather than guess.** Two cases stop with an actionable `ValueError`
instead of writing something plausible:
- the entry carries no `## [version]` heading, or its heading is
  `[Unreleased]` — `update_changelog` writes *released* sections; the
  `[Unreleased]` block is owned by the aggregator, and replacing it would
  destroy pending bullets (the scenario-2 loss, re-entered through the front
  door);
- the file already contains **more than one** section for that version — the
  exact wreckage the old bug produced. Which one is authoritative is not
  knowable, so the writer names the file, the version and the count and stops.
  This is the "stop and ask when safe insertion is not possible" arm.

### Alternative considered and rejected

**Import `_insert_section` / `_find_structural_insertion_line` from
`shared/scripts/tools/aggregate_changelog.py`** instead of implementing the
splice in the plugin. Rejected: that module does
`sys.path.insert(0, shared/scripts)` and then `from lib.atomic_write import …`,
while this plugin has its **own** `scripts/lib` package. Importing it puts two
different `lib` packages on `sys.path`, and whichever lands first shadows the
other — the ADR-045 lib-collision failure mode (green locally, red in CI, or
worse, silently the wrong module). The plugin declares `dependencies = []` and
resolves nothing from `shared`; keeping it self-contained is the cheaper
correctness guarantee. Cost accepted: the insertion chain now exists in two
places. It is ~25 lines, the layout rules are pinned by tests on both sides,
and the shared copy stays the release-path authority.

## Acceptance Criteria

- **AC1** File exists **without** a `## [Unreleased]` marker → the new section
  is inserted and the title plus every pre-existing entry survives byte-for-byte
  — including trailing blank lines, the line-ending convention and a UTF-8 BOM.
  **One documented exception:** appending at end of file terminates a
  previously-unterminated last line. That adds a byte; it never removes content.
- **AC2** File exists **with** a marker but no released section → the new
  section is inserted below `[Unreleased]` and every pending `[Unreleased]`
  bullet survives.
- **AC3** File exists with a marker and a released section → unchanged
  behaviour: the new section lands between `[Unreleased]` and the previous
  release (existing test keeps passing).
- **AC4** File does not exist → created with the standard header, `[Unreleased]`,
  and the entry (existing test keeps passing).
- **AC5** Running twice with the same entry is idempotent: the version appears
  exactly once and the second result equals the first.
- **AC6** Re-running with a **changed** entry for the same version replaces that
  version's section; neighbouring sections are untouched.
- **AC7** An entry with no `## [version]` heading, or one headed `[Unreleased]`,
  raises `ValueError` and **leaves the file on disk unmodified**.
- **AC8** A file already containing two sections for the target version raises
  `ValueError` naming file, version and count, and leaves the file unmodified.
- **AC9** `spec.md` FR-01.09 gains an (E) criterion for the re-run guarantee.
- **AC10** The section-boundary predicate accepts the same headings the
  section-*name* predicate does, so a whitespace-variant heading
  (`##\t[1.0.0]`) ends a section being replaced instead of being swallowed by
  it. *(Added after external review — see below.)*
- **AC11** A **replaced** span is bounded by what the section actually owns
  (blank lines, deeper headings, list items, indented continuations), so
  trailing prose and the canonical Keep-a-Changelog link-reference footer
  survive a re-run even when the replaced version is the last section in the
  file. *(Added after the review cascade — see below.)*
- **AC12** The rewrite preserves a UTF-8 BOM and the file's own line endings,
  and is crash-safe (temp file + atomic replace, never an in-place truncation).
  *(Added after the review cascade — see below.)*

## Affected Boundaries

- **`CHANGELOG.md` on disk** — a user-authored document this function rewrites.
  This is the boundary the defect crosses; the round-trip probe is
  read → write → assert every pre-existing byte is still present.
- No config/env/JSON boundary is touched. The `json.load`/`json.dumps` calls in
  the module's CLI block are untouched by this diff.

## Confidence Calibration

- **Boundaries touched:** `CHANGELOG.md` (user-authored file rewritten in place).
  No `*_config.json`, `.env*`, `hooks.json` or wire-format boundary.
- **Empirical probes run:**
  - Pre-change scenario 1: hand-written history through `update_changelog` →
    `# Release History`, `[1.0.0]`, `[0.9.0]`, `an early bug` all
    `present_before=True present_after=False`. Total loss confirmed.
  - Pre-change scenario 2 (**not in the brief**): `[Unreleased]` with two
    pending bullets, no released section → both bullets `survived=False`. The
    "two branches preserve the file" premise was wrong; one does.
  - Pre-change scenario 3: same entry applied twice →
    `occurrences of '## [1.1.0]' = 2`.
  - Post-change: all three re-run green, plus a corpus probe applying the new
    writer to 12 real-world file shapes — **once, twice, and twice with a
    revised entry** — asserting zero byte loss on each.
  - **Review-cascade regressions, each reproduced before being accepted:**
    `FILE_SHAPES[4]` lost `We write these by hand.` on run 2 and `run2 != run1`;
    a link-reference footer was deleted outright; a BOM'd file lost
    `### Added` / `- first`; an LF file came back all-CRLF (`CRLF in after:
    True`). All four now clean, and each has a test that fails without its fix.
  - **Mutation probe (do the new tests falsify?).** Re-introduced each fixed
    bug and confirmed the guarding assertion fails: the old tail
    normalization → `lost or reordered line: '- first'` and `'\n'`; the old
    `startswith("## ")` boundary → index `9` of `9` lines, i.e. it swallowed
    the whole `1.0.0` release, versus `5` (the tab heading) now. Neither test
    is vacuous.
- **Test Completeness Ledger:** below — every AC has a `tested` row; 0
  untested-testable behaviours.
- **Confidence-pattern check:** *depth* — loss is asserted on the **bytes on
  disk** (`keepends` line-by-line, plus `read_bytes` for BOM and line endings),
  not on "the function returned"; idempotency is asserted by byte-comparing run
  1 and run 2, not by counting headings. *Breadth* — 12 file shapes × 3 run
  patterns, both insertion and replacement paths, all three refusal arms, the
  crash path, and the CLI entry point. *The asymptote that was missed:* the
  first pass ran the corpus **once**, which covers only insertion — the
  replacement path is the one that deletes a span, and it had zero preservation
  coverage until the cascade said so. Breadth of *inputs* hid an absent
  *operation*. *Integration composition* — none required: no `cross_component`
  machinery is touched (checked against `CROSS_COMPONENT_FILE_PATTERNS`); the
  writer's one caller surface, the `changelog.py generate` CLI, is covered
  end-to-end on both the success and the refusal arm.

### Test Completeness Ledger

| Behavior | Disposition | Evidence |
|---|---|---|
| AC1 no-marker file preserved (title + all entries) | tested | `test_changelog.py::test_update_changelog_preserves_file_without_unreleased_marker` |
| AC2 marker-only file preserves pending bullets | tested | `test_changelog.py::test_update_changelog_preserves_pending_unreleased_bullets` |
| AC3 marker+version ordering unchanged | tested | `test_changelog.py::test_update_changelog_existing` (pre-existing) |
| AC4 new-file creation unchanged | tested | `test_changelog.py::test_update_changelog_new_file` (pre-existing) |
| AC5 second run idempotent (byte-equal, one occurrence) | tested | `test_changelog.py::test_update_changelog_is_idempotent_on_rerun` |
| AC6 changed entry replaces same version, neighbours intact | tested | `test_changelog.py::test_update_changelog_replaces_same_version_section` |
| AC7 unparseable / `[Unreleased]` entry refused, file untouched | tested | `test_changelog.py::test_update_changelog_rejects_entry_without_released_version[no-version-heading]` + `[unreleased-heading]` |
| AC7 multi-section entry refused, file untouched | tested | `test_changelog_preservation.py::test_rejects_entry_with_more_than_one_section` |
| AC8 duplicate existing sections refused, file untouched (message names path, version, count) | tested | `test_changelog.py::test_update_changelog_refuses_ambiguous_duplicate_sections` |
| No-byte-loss across 12 real-world shapes, **one** run | tested | `test_changelog_preservation.py::test_insert_never_loses_existing_content` |
| No-byte-loss across 12 shapes, **re-run** (the replace path) | tested | `test_changelog_preservation.py::test_rerun_never_loses_existing_content` |
| No-byte-loss across 12 shapes, re-run with a **revised** entry | tested | `test_changelog_preservation.py::test_revised_rerun_never_loses_existing_content` |
| AC10 whitespace-variant heading ends a replaced section | tested | `test_changelog.py::test_update_changelog_replacement_stops_at_whitespace_variant_heading` |
| AC11 link-reference footer / trailing prose survive a re-run | tested | `test_changelog_preservation.py::test_replace_preserves_trailing_link_reference_footer` + `::test_replace_preserves_trailing_prose` |
| AC12 BOM preserved and not parser-blinding | tested | `test_changelog_preservation.py::test_preserves_utf8_bom` |
| AC12 LF and CRLF files keep their own endings | tested | `test_changelog_preservation.py::test_preserves_lf_line_endings` + `::test_preserves_crlf_line_endings` |
| AC12 a failed write leaves the original intact, no orphan temp file | tested | `test_changelog_preservation.py::test_failed_write_leaves_the_original_intact` |
| CLI `generate` reaches the fixed writer on a no-marker file | tested | `test_integration.py::test_generate_preserves_existing_history` |
| CLI refusal arm: exit 1, error JSON, file untouched | tested | `test_integration.py::test_generate_refuses_ambiguous_file_and_leaves_it_untouched` |
| AC9 spec criterion present | by-construction | `.shipwright/planning/01-adopted/spec.md:468-473` — no gate reads `01-adopted/spec.md`; asserted by inspection, not by a test |

## External review (mode `code`, openrouter — 2 providers, not degraded)

Both findings were **accepted and fixed**; neither was cosmetic.

1. **`section_end` boundary predicate (high, real).** `SECTION_HEADING_RE`
   accepts any whitespace after `##`, but `section_end` matched the literal
   `"## "`. A tab-separated heading was therefore a section to
   `section_starts`/`insertion_index` and *not* a boundary to `section_end`, so
   replacing the version above it would run through and delete it — the very
   defect class this iterate exists to remove. Fixed by giving both predicates
   one shared regex (`HEADING_RE`); confirmed by mutation probe (old predicate
   returned `9` of `9` lines, i.e. swallowed the release).
2. **Tail normalization contradicted AC1 (medium, real).** `"".join(...)
   .rstrip("\n") + "\n"` stripped pre-existing trailing blank lines and added a
   final newline to files that had none — mutating bytes outside the splice
   while AC1 claimed byte preservation, and `FILE_SHAPES[7]` is exactly such a
   file. Fixed by controlling only the separators around the inserted block;
   the reviewer's third point (the property test compared non-blank lines and
   so could not see this) is fixed by comparing with `keepends=True`.

The third finding is folded into #2: it was the reason #2 escaped the tests.

## Internal review cascade (spec-compliance → code → adversarial)

The cascade found a **regression I had introduced** — the same defect class this
iterate exists to remove — plus four real robustness gaps and two false evidence
citations. All were reproduced before being accepted, and all are fixed.

1. **The replace path re-introduced data loss (high).** `section_end` bounded a
   section at "the next `##` heading or EOF", so when the replaced version was
   the **last** section, everything below it was inside the replaced span and
   was deleted on the second run. Reproduced on the project's own corpus:
   `FILE_SHAPES[4]` lost `We write these by hand.`, and a canonical
   Keep-a-Changelog link-reference footer was deleted outright. The insert path
   was structurally safe; the replace path was not — and the property test could
   not see it because it ran the writer **once** and no corpus shape contained
   the entry's version, so the replace path had **zero** byte-preservation
   coverage. Fixed by AC11 (`continues_section`) and by running the corpus a
   second and third time.
2. **UTF-8 BOM blinded the parser (medium).** A BOM on line 0 made a first-line
   `## [1.0.0]` match no regex; the new section was inserted *inside* it and the
   orphaned body was deleted on the next run. Fixed by AC12; the repo already
   used `utf-8-sig` elsewhere for exactly this.
3. **Line endings were rewritten wholesale (medium).** `write_text` translates
   `\n` to `os.linesep`, so an LF-authored CHANGELOG.md became entirely CRLF on
   Windows — a whole-file diff on every release. Verified byte-exactly (my first
   probe of this mis-escaped its own byte literal and wrongly cleared the
   finding; the second probe confirmed it). Fixed by AC12.
4. **In-place truncating write (medium).** A crash mid-write would have left the
   history zero-length — the very loss this module prevents. Now temp file +
   `os.replace`, with failure injection proving the original survives. Not
   lock-coordinated with the aggregator; see "Out of scope".
5. **Two ledger rows cited tests that do not exist (high, honesty).** AC7 cited
   two node IDs that were never written (the real test is parametrized), and AC9
   cited `shared/tests/test_spec_ac_shape.py`, **a file that does not exist** —
   no gate reads `01-adopted/spec.md` at all. AC9 is now recorded as
   `by-construction` with a line anchor rather than a fabricated `tested`.
6. **AC1 still overclaimed (medium, honesty).** The end-of-file insertion arm
   terminates a previously-unterminated last line, and no corpus shape reached
   that arm. AC1 now states the exception; shape 10 reaches the arm.
7. **The CLI refusal arm was untested (medium)** while the ledger claimed "0
   untested-testable behaviours". It is the arm that actually delivers the new
   spec criterion's "stops and says why". Now covered.

**Findings recorded but NOT fixed** (deliberate, see "Out of scope"): the
aggregator's own re-run duplicate; fenced-code-block awareness; insertion-point
divergence from the aggregator for non-canonical `[Unreleased]` spellings.

## Out of scope

- `shared/scripts/tools/aggregate_changelog.py` — **untouched, and it carries a
  related defect this iterate does NOT fix.** It splices correctly (so it never
  loses content), but SKILL.md Step 4 makes it the writer the release path
  actually invokes, and `_insert_section` never looks for an existing
  same-version section. Its idempotency rests entirely on consuming drop files,
  and `_atomic_write` happens *before* the unlink loop — so an interruption in
  that window leaves the drops on disk and a re-run inserts a **second**
  `## [x.y.z]`. It also has no "stop and say why" arm. The FR-01.09 criterion
  added here is therefore worded at the level of *writing a release note*,
  which is what this diff genuinely guarantees, rather than claiming the whole
  release pipeline is idempotent. Fixing the aggregator means either a third
  copy of the section logic or extracting a shared one across the plugin/shared
  boundary (the ADR-045 hazard) — a separate iterate, flagged to the operator.
- **Fenced code blocks and HTML comments** are not recognised: a `## [1.1.0]`
  inside a ``` fence is parsed as a real heading. With AC11 in place this no
  longer *deletes* the fence terminator (the scan stops at the fence line), but
  it can still strand content or trigger the duplicate-section refusal on a
  changelog that documents its own format. Documented limitation.
- **Insertion-point parity with the aggregator is approximate, not exact.** The
  two disagree on non-canonical spellings (`## [unreleased]` lowercase; an
  `[Unreleased]` block followed by a non-bracket `## Notes`). Neither loses
  content; the layouts differ. Nothing pins the equivalence.
- Making `git tag` / PR creation code rather than instruction (FR-01.09
  criteria 1, 3, 7, 8, 9 are `prompt-only (mechanisable)`). That is the
  enforcement-register work in REQ-3 Phase 3, not this bug fix.
- Migrating files already corrupted by the old bug: unrecoverable from within
  the writer (the content is gone from disk). AC8 stops on the duplicate-section
  wreckage rather than compounding it.
