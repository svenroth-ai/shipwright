# ADR 108 — One FR-table shape: `Area` rendered, `Basis` replaces `Source`, `Layers` marked

- Run-ID: `iterate-2026-07-20-converge-table-shape`
- Campaign: `2026-07-18-requirements-catalog` — sub-iterate **S5** (first VISIBLE step)
- Builds on: **ADR-107** (one header-driven reader), which made this safe by removing positional parsing
- Implements: campaign SPEC decisions **D1 / D2 / D3 / D7**, §3.1, §3.2, §6.2
- Mode: change · Spec Impact: **MODIFY** · Complexity: medium

## Context

S4 collapsed five *parsers* into one header-driven reader. The *producers* still
disagreed, so the divergence had moved upstream rather than gone away:

| Producer | Shape |
|---|---|
| `/shipwright-adopt` (`artifact_writer`) | `ID │ Name │ Priority │ Description │ Source │ Layers` |
| greenfield template (`spec-generation.md:131`) | `ID │ Requirement │ Priority │ Layers` |
| greenfield **example** (`:259`) | `ID │ Requirement │ Priority` — missing a mandated column |
| the live catalog on disk | `ID │ Name │ Priority │ Description │ Source` |

The example is the more copyable of the two greenfield forms, so an agent
following it emitted a table missing `Layers` outright. `Source` held a file path:
implementation detail (D3), answering *where we looked* rather than *how we know*,
and unvalidatable because every string is a legal path. `Area` did not exist, so
grouping was carried only by the folder — the axis D7 says must be rendered.

## Decision

One shape, emitted by both producers and now on disk:

```
| ID | Area | Name | Priority | Description | Basis | Layers |
```

`FR_TABLE_HEADER` in `shared/scripts/lib/fr_table_shape.py` is the single
constant; both producers are compared against it by test, because "byte-compatible
headers" is otherwise checkable only by eye and the reader resolves columns by
NAME — a renamed column is not a cosmetic difference, it is a column that stopped
existing.

## The hard blocker, and the empirical proof it is closed

A requirement's provenance becomes `explicit` the moment a header-named `Layers`
cell is non-empty **without** the literal `(inferred)` marker, and `explicit`
routes a coverage gap from advisory to hard (`_layer_coverage_core.py:177` →
`CheckResult(ok=False)` → ERROR → `sys.exit(1)`). Ten of the fifteen live
requirements have zero test links. Unmarked cells would have hard-aborted **on S5
itself**. There is no bypass.

Per the operator decision of 2026-07-19, every machine-emitted `Layers` cell
carries the marker. Measured after the migration, not before:

| | before | after |
|---|---|---|
| `defaulted_legacy` | 12 | 0 |
| `inferred_legacy` | 3 | **15** |
| `explicit` | 0 | **0** |

Both remaining sources are in `_LEGACY_SOURCES`, so every gap stays advisory. The
gate itself was then run — not just the reader — with **all 15 keys forced
behaviour-changed** (the maximum blast radius any iterate can produce):
**0 hard gaps, 15 advisory, exit 0.**

**The migrated cells record the inference that already ran; they add no claim.**
`_infer_layers` derived `(e2e,)` for the three UI/flow titles and `(unit,)` for
the other twelve, and those exact values are what is now written down.
`required_layers` is byte-identical per requirement before and after — pinned per
ID, not as a distribution, because a 12/3 count is also satisfied by a migration
that swaps two rows.

## D-S5-1 — the `Source` → `Basis` mapping, decided rather than derived

Measured: 13× `enrichment.json`, 1× `backfill`, 1× an iterate run id. (The brief
predicted a `cli` value; it is not present. 15 rows, 3 distinct values.)

| Today | → | Basis | Why |
|---|---|---|---|
| `enrichment.json` (13) | `code` | adopt's enrichment read plugin sources, `plugin.json` and `SKILL.md` files |
| `backfill` (1, FR-01.14) | `code` | the backfill scanner derives from repo history and source, not a human or a running app |
| run id (1, FR-01.15) | `code` | **re-derived, not carried over.** A run id records *when*, never *how*; D4 removes it from the requirement. The basis was re-established by inspection |

The migration was performed by a one-off script that raised on an unmapped
`Source` value rather than defaulting, so no value entered the table undecided.
**That script was a throwaway and is not in the tree — this is an audit-trail
gap, not a reproducible guarantee, and it should not be read as one.** What IS
reproducible is the outcome, which is checked in and asserted: 15 rows before and
after, the three source values above, and
`test_the_migration_did_not_change_any_required_layers` pinning the per-ID layer
mapping. A future migration of this kind should land its script under
`shared/scripts/tools/` so the claim and the artifact travel together.

**This answers campaign open question 3 — "`enrichment` maps to `code`/`observed`
depending on origin — is that lossy?" — with NO, because the generator already
knows which.** `_render_spec_md` picked `f.get("source_file", f.get("url", "—"))`:
a feature found by reading a file carries `source_file`, one found by the
Playwright crawl carries only `url`. That is exactly the `code`/`observed`
discriminator, available at the point `Source` was rendered. The loss was in the
old column, not in the new vocabulary. The generator now emits `code` /
`observed` / `assumed` accordingly.

## Other decisions

**D-S5-2 — `(inferred)` is scoped to machine-emitted cells.** The greenfield
template's `Layers` cells stay bare, so a human author's declaration reads as
`explicit`. Stamping the marker into the template would permanently disarm the
hard gate for every future greenfield project — the opposite of the honesty
argument that motivates it. The marker marks *machine inference*; a human
declaration is not inference. **This narrows the literal AC ("every `Layers`
cell"), deliberately and on the record.** It is verified where it bites: the 15
live rows, zero `explicit`.

**D-S5-2b — greenfield gains the `Area` COLUMN, which is more than the spec
asked for.** The S5 sub-iterate spec says *"Greenfield gains `Area` sections only
where a split holds more than one area"* — sections, not the column. The column
is nonetheless mandatory for greenfield here, because the acceptance criterion
above it requires **byte-compatible headers** from both producers, and a header
that omits `Area` for one producer is a different header. The `### Area`
*sections* remain scoped as the spec intended: only where a split holds more than
one area. This obliged a correction to `shared/fr-authoring.md`, which said
outright *"Do not add `Area` to a greenfield spec"* — it now describes `Area` as
the rendered label of the split grouping and reserves the "you don't need this"
advice for the sections. Recorded because it is a scope decision, not a
restatement of D-S5-2 (which governs the marker).

**D-S5-3 — `Basis` is read only from a column headed `Basis`.** Treating a legacy
`Source` cell as a `Basis` value would make every already-adopted repo hard-fail
on `enrichment.json` — a malformed verdict on data that never claimed to be a
basis. A spec with no `Basis` column skips the check.

**D-S5-4 — severity is asymmetric.** A value outside the vocabulary is hard (a
typo is not a special case). `other` never blocks (an escape hatch that blocks is
not one); a bare `other` is nagged in the detail, not escalated. A **blank cell
under a declared column** IS hard — declaring the column is opting in, every row
then answers, and `assumed` is always available. *(Raised by external code review;
my original design let a blank pass. Accepted and fixed.)* A known value with a
qualifier (`code (enrichment.json)`) is hard but says so specifically, because
"not in the vocabulary" is useless advice to someone who used a vocabulary word —
and letting it through re-opens the door D3 closed, since the qualifier authors
reach for first is the file path `Basis` replaced.

**D-S5-5 — Group I distinguishes SIX states, not two.** `no_spec` /
`no_fr_rows` / `no_governing_header` / `no_canonical_ids` / `rows_too_narrow` /
`all_rows_retired`. The last two were added during review, and both for the same
reason the first four exist: the module was reporting the **wrong cause**. It
branched on `header_seen` alone, but two reject reasons carry it, so a row too
narrow for its header was reported as "no row id is canonical — fix the ids"
about an id that was already canonical; and an all-retired spec was reported as
"contains no FR-shaped rows" about a file that plainly contains them. The
`detail` now also quotes **only the ids declined for the reason that decided the
state** — pooling every declined id was the same defect one field over.
Precedence is decided
from raw parse facts so one input cannot classify two ways. The last state is the
one S4's strict-id rule creates and that ADR-107, S4's mini-plan and
`frozen_bugs.py` FV-1 each cited this AC as mitigating — which, as originally
written, it did not: in that route the spec IS on disk and the header IS
recognised, and only the ids fail. It is read from the `rejects` accumulator S4
shipped (the same data the manifest publishes as `invalid_ids`, one hop earlier),
plus one additive field `header_seen`, because `non_canonical_id` alone cannot
tell the two apart. Every state still reports `skip` — Group I is detective-only —
but the detail now names which.

## What the boundary probes found

Per ADR-024, the producer/consumer pair for the `Layers` cell was probed, not
reasoned about:

- **`unit(inferred)` — one space short — parses to ZERO required layers.** The
  consumer tokenises on `[,\s/|]+`, so a glued marker makes the layer name part of
  one unrecognised token; the requirement keeps advisory provenance and silently
  loses its coverage requirement. **The separator is load-bearing.** Fixed by
  making `render_layers` the only sanctioned way to write the cell, and by moving
  the marker regex into `fr_table_shape` so the compliance-side consumer imports
  it instead of keeping a private copy. Producer and consumer each owning half of
  one serialized-format grammar is the exact ADR-024 defect class.
- `unit, e2e (auto)` and bare `unit, e2e` both yield `explicit` — the narrow
  regex behaves as specified, so the near-miss does NOT silently escape the gate.
- Case and inner-space variants (`(INFERRED)`, `( inferred )`) all match.
- **`basis_for` read the literal `"—"` placeholder as evidence.**
  `generate_adoption_artifacts` defaults an unmatched `source_file` to an em dash
  (it was a *display* placeholder for the old `Source` column), and a truthiness
  test labelled every crawl-only page `code` — the exact inversion of what the
  crawl observed. Caught by an existing merge test, fixed with an explicit
  absent-value set, pinned by a parametrised regression test.

Asymptote: the last probe round found no further defect across the census, the
worst-case gate evaluation, and the producer→file→consumer round trip. Declared
calibrated.

## External-Plan-Review-Findings

| # | Sev | Finding | Disposition |
|---|---|---|---|
| G1 | Med | Extracting `_fr_table_row.py` / `fr_area.py` to dodge the 300-line cap is over-production; use `# noqa` or bump the ratchet | **rejected-with-reason.** No `# noqa` exists for this gate, and bumping `current` is a contract violation (anti-ratchet). The critique had partial merit, so `fr_area` was FOLDED into `fr_table_shape` — its only consumer is the row renderer. `_fr_table_row` stays: it bought the reader's two additive fields at exactly 300 lines, and a frozen dataclass was never state-machine code |
| G2 / O4 | High | The layer parser may not strip `(inferred)`, changing `required_layers` | **verified-not-a-defect, then hardened.** Probed empirically: the marker is stripped correctly. The probe DID find the adjacent `unit(inferred)` defect, which is why `render_layers` now exists |
| G3 / O5 | Med | `other` with a reason, or a known value with a qualifier, may be misclassified | **accepted-and-fixed.** Grammar implemented and tested for four separators; qualifiers on known values are hard with a specific message |
| G4 | Med | The greenfield example row will gain a `Layers` column and could hard-abort a build | **verified-not-a-defect.** `spec-generation.md` lives under `plugins/.../references/`, not `.shipwright/planning/<split>/spec.md`, so no discovery walk reaches it |
| O1 | High | The plan contradicts the literal AC by leaving greenfield cells bare | **accepted — resolved explicitly, not silently.** D-S5-2 records the narrowing; three separate tests cover adopt output, template and example |
| O2 | High | The Area rendering contract is undefined | **accepted-and-fixed.** One function, one authority rule (id wins on disagreement), tested for every current group, an unknown group and a non-canonical id |
| O3 | High | The real greenfield rendering path may not be `spec-generation.md` | **verified.** `/shipwright-project` is prompt-driven with no code entrypoint — recorded and re-confirmed from `iterate-2026-07-15-required-layers-on-frs` O6, and a grep for a Python writer found none |
| O6 | Med | Generator Basis logic and migration mapping are not proven equivalent | **accepted-and-fixed.** Per-requirement evidence table above; generator branches unit-tested for source-file-only / url-only / both / neither |
| O7 | Med | `invalid_ids` vs `rejects` naming discrepancy; manifest consumers | **accepted, clarified.** Group I reads the reader's `rejects` directly — the source of `invalid_ids`, not a parallel accumulator. `header_seen` is deliberately NOT propagated to the manifest: schema v3 has an `origin/main` diff gate and Group I does not need it there |
| O8 | Med | The four states need explicit precedence | **accepted-and-fixed.** Precedence documented and tested, including the both-present case |
| O9 | Med | A reader-only census can pass while the real gate still aborts | **accepted-and-fixed.** The actual `evaluate_cross_layer` router was run at worst case: 0 hard, exit 0 |
| O10 | Low | "Byte-identical headers" needs one canonical source and an exact test | **accepted-and-fixed.** `FR_TABLE_HEADER` constant; every producer compared to it |
| O11 | Low | Free-text `other` reasons could break the table with unescaped pipes | **accepted-and-fixed.** All adopt cells now go through `markdown_table.escape_cell`, which the hand-written f-string never did |

## External-Code-Review-Findings

| # | Sev | Finding | Disposition |
|---|---|---|---|
| C1 | Med | A blank cell under a declared `Basis` column passes I5 | **accepted-and-fixed** — see D-S5-4; test added |
| C2 | Med | The layers test asserts only the aggregate distribution, so a swap between two rows would pass | **accepted-and-fixed.** Now an explicit per-ID mapping for all 15 |
| C3 | Med | `golden.json` was not regenerated | **rejected — false, and my fault.** It IS regenerated (499 insertions, `--reason` stamped, `08-converged` present) and `test_requirements_corpus_matrix.py` fails on a stale golden. The reviewer was misled because I excluded the 156 KB generated file from the diff I sent |

## Round 3 — fresh external review on the current head (`bb1bf6cf`)

Run because the repository's Tier-3 `PR Review` gate **failed closed on
truncation** (51,496 input tokens, `truncated=True`): the automated reviewer
could not read the diff, so every finding below was treated as must-fix rather
than triaged by severity. The diff was split into three chunks summing to the
complete human-authored change, with the regenerated artifacts (58% of the raw
diff, and the reason the gate truncated) excluded and declared.

| # | Sev | Finding | Disposition |
|---|---|---|---|
| R1 | High | Group I state model incomplete — `all_rows_retired` missing, and the ADR still said "four states" | **accepted-and-fixed.** Sixth state added; every stale count corrected |
| R2 | High | The greenfield example's bare `Layers` cells are copyable into a generated spec → `explicit` → hard abort | **partially fixed, escalated.** Documentation control applied; the policy question is the operator's — see above |
| R3 | Med | `Area` is persisted but never validated on read, so a stale cell shows a wrong label | **accepted-and-fixed.** Catalog test asserts every persisted `Area` equals the value derived from its own id |
| R4 | Med | Duplicate governed headers resolve silently; a second `Layers` column could force `explicit` | **CONFIRMED by probe, fixed.** `header_map` was a dict comprehension (last-wins); now first-wins, matching the rule `pick` already applied to synonyms |
| R5 | Med | Migration `Basis` attribution proven only in aggregate | **accepted-and-fixed.** Per-FR expected-Basis fixture, the durable record the throwaway script was not |
| R6 | Med | `Basis` normalization not specified as a contract | **accepted-and-fixed.** Trim → strip emphasis → lowercase, then exact ASCII match, documented in §4a; Unicode lookalikes fail loudly by design |
| G-partial | — | Gemini claimed a conflict between "qualifiers on known values are hard" and free-text `other` reasons | **not reproduced.** Probed all six forms: `other` is matched before the qualifier rule and is not in `BASIS_VALUES`, so there is no overlap |

**Gemini's leg degenerated a FIFTH consecutive time** — 770 characters, cut off
mid-sentence inside its first finding. Not counted; this round was
**single-leg** (GPT), which is exactly why the third leg was added.

**Third leg — Codex** (`codex-cli 0.130.0`), added under the truncation
exception. It found three defects the other legs missed, all confirmed by probe
before being accepted:

| # | Finding | Disposition |
|---|---|---|
| X1 | `pick` resolves `LAYERS_COLS` by SYNONYM order, so a header `\| Layer \| Layers \|` selects the later column regardless of position — flipping `unit (inferred)` to a bare `unit` and into `explicit`. The same hazard as R4, one level up | **CONFIRMED, fixed.** `named_cell` selects the lowest column index. `pick` keeps preference order because `TITLE_COLS` is NOT a synonym set — `description` outranks `name` by meaning, and the converged shape puts Name to the LEFT, so lowest-index there would return the wrong column for every row in the repo |
| X2 | Unknown `invalid_layers` reasons fell to ADVISORY, so a typo'd or newly-added reason silently stops blocking — a fail-OPEN gate | **CONFIRMED, fixed.** The ADVISORY set is now the closed one; anything unrecognised is hard |
| X3 | A marked cell whose tokens are not layer names (`ui (inferred)`) yields `required_layers=()` with advisory provenance and NO diagnostic — the glued-marker differential cannot see it, because both sides parse to the same empty tuple. Also named a second hand-formatter at `traceability_layers.py:169` | **CONFIRMED, fixed.** Recorded as `unknown_layer_token`; the adopt writer now calls `render_layers` through the sentinel loader, removing the third copy of the marker grammar |

Codex explicitly reported finding **no** defect in the `Basis` severity rules or
in the six-state precedence after the reason-based ordering — a useful negative,
since those are the two areas the other legs concentrated on.

**Gemini's code leg degenerated again** — 612 characters, truncated mid-sentence,
no coherent findings. This is the **fourth consecutive** sub-iterate (S2, S3, S4,
S5), so it is a standing provider defect, not a one-off. Recorded rather than
re-rolled, and **not counted as a passing review**: the external code review had
one usable leg.

## A fix that introduced the defect it was fixing

Recorded because it is the sharpest lesson of this iterate. Making the glued
`(inferred)` marker *visible* (a correct goal) was implemented by appending to
`invalid_layers` — and `invalid_layers` is a **hard** channel:
`_group_d_traceability` returned `fail` on `if hard or invalid:` with no filter
on `reason`. Before this change it carried exactly one reason,
`no_canonical_layer`, whose rows are deliberately kept `explicit` *so that gate
fires*. Appending an advisory-intent diagnostic to it meant an author dropping
one space in an `(inferred)` cell **failed the audit** — while ADR-108,
`fr-authoring.md` §4a and `path-a-feature.md`, in the same commit, all said the
marker is advisory and never blocks.

So the fix for "a diagnostic is invisible" shipped "a diagnostic blocks the build
and its own documentation denies it". Two sub-defects rode along: the render site
hardcoded `[HARD, explicit]`, stating the wrong severity **and** the wrong
provenance for a row that is `inferred_legacy` — the same wrong-cause defect the
six-state work exists to remove, one layer down — and the `lost` key, the only
new information the diagnostic produces, was never rendered at all.

Fixed by splitting the channel on `reason`: `no_canonical_layer` stays hard,
everything else is advisory evidence; the render site reads reason and provenance
from a table and prints `lost: e2e`. **The general lesson: adding a value to an
existing diagnostic channel is a severity decision, not a data decision.** Ask
what the channel is wired to before appending to it.

## D-S5-6 — the copyable worked example (raised by review, decided by the operator)

`/shipwright-project` is prompt-driven, so `spec-generation.md` IS the generator,
and its **worked example** carried real-looking rows with bare `Layers` cells. An
agent generating a new project copies those rows into the new `spec.md`; at that
moment the project has no tests, so a bare cell is `explicit` provenance against a
guaranteed gap — a hard abort on a freshly generated project. The reviewer's
framing was that copied template content is *functionally machine-supplied*
whatever the policy calls it.

I raised this rather than closing it, because closing it looked like reversing the
"write bare" greenfield policy. **It is not, and the distinction is the decision:**

> **The policy stands. Bare is the correct form for a considered author
> declaration** — `/shipwright-project` feeds `/shipwright-build`, which is TDD,
> so the tests land as part of building, and an author declaring "this must be
> tested at unit and e2e" *should* be held to it.
>
> **But a worked example is not a considered declaration — it is copyable
> boilerplate.** The failure is real precisely because a prompt-driven agent
> copies the example's SHAPE without inheriting the author's INTENT. So the fix
> belongs at the example, not at the policy.

Resolved by showing **both forms in the example, each labelled with its
consequence**: FR-01.01–.05 stay bare (binding, and the recommended form), and
FR-01.06 — a `May` capability whose layers nobody has verified — carries
`(inferred)` (advisory). Copying either is now an informed choice rather than an
accident, and the recommended form is still bare.

No code entrypoint exists to test this route; that is the same fact that makes the
example itself the only available control, which is why the control had to be
placed *in* it rather than beside it.

## Golden-corpus attribution — the deletions, reconciled

Insertions are the two additive `FrRow` fields (`basis`, `basis_declared`, empty
on all 109 pre-S5 fixture rows) plus the new `08-converged` fixture. The
**deletions** are worth enumerating exactly, because the discipline here is that
the numbers reconcile and an earlier count of "3 comma shifts" did not — the real
figure is **9 deleted lines**:

| Count | Line | Why |
|---|---|---|
| 7 | `…07-header-blind…` in five path/name forms | list-tail comma shifts: `08-converged` sorts after it, so the previously-last element gains a `,` |
| 1 | `"FR-07.01"` | same class — last id in a list that now continues |
| 1 | `"regenerated_for": "S4 …"` | replaced by this run's `--reason` stamp |

No fixture changed behaviour, and no row was removed. Verified by diffing the
committed baseline against `HEAD`, not by reading the summary.

## Consequences

- The catalog table is now readable as a capability list: an area, a short name,
  and how we know it, instead of a file path and a folder-implied grouping.
- Adopted repos get honest provenance per feature (`code` / `observed` /
  `assumed`) where they previously got one file path for everything.
- A malformed `Basis` is now catchable, which a free-text path never was.
- Group I stops reporting one indistinguishable `skip` for four different causes.
- `artifact_writer.py` **shrank** 695 → 690 lines while gaining behaviour.
- Every `Layers` cell in the repo now says, visibly, that nobody has verified it.
  That is the point: making `Layers` authoritative is a separate campaign whose
  real content is establishing the missing test links, not reshaping a table.

## Residual risk — declared, not hidden

- **THE CENSUS IS A SNAPSHOT OF 15 ROWS, AND THE NEXT ADDED FR RE-OPENS THE
  HARD BLOCKER.** This is the sharpest residual risk in this ADR and it belongs
  next to the missing test links, not buried in the outcome. The chain:
  `_requirement_parse` maps a bare `Layers` cell to `explicit`; a newly added FR
  is *always* in `behavior_changed_keys` in the iterate that adds it; a new FR
  has zero `@FR`-tagged tests at the moment its row lands; `explicit` + a gap →
  `verdict.hard` → `sys.exit(1)`, no bypass. So an iterate with
  `spec_impact=ADD` that appends `| FR-01.16 | … | code | unit |` hard-aborts
  its own finalization.

  **Nothing in the code prevents this, and nothing can.** `render_layers` is
  unreachable from the ADD path — that path is prompt-driven (see O3 above), so
  the only available control is documentation. The "write bare" policy is
  deliberate and is NOT weakened here: a human declaring layers for a capability
  they are about to build should be held to it, and TDD makes that the normal
  case. What was missing was any warning where the author actually is. Now
  documented in `path-a-feature.md` (ADD), `path-b-change.md` (ADD) and
  `shared/fr-authoring.md` §4a — all three state both forms and their
  consequences. **The mechanism keeping the census true is a prompt sentence,
  and that is worth knowing.**
- **Ten of fifteen requirements still have zero test links.** S5 does not fix
  that and does not pretend to; it keeps the gate honest about it (advisory)
  rather than either hiding the gap or hard-blocking on it.
- **A glued marker is prevented at the producer, not at the format.**
  `unit,e2e(inferred)` silently drops `e2e`. `render_layers` is the only
  sanctioned writer, but a `spec.md` is hand-edited by design, so sanction is
  not enforcement. Since this review the consumer RECORDS the loss
  (`invalid_layers`, reason `marker_glued`, detected differentially by
  re-parsing with the marker split off), and provenance deliberately stays
  advisory — the cell genuinely is tool-derived. Verified latent, not live:
  zero glued cells on disk.
- ~~`scan_specs` computes its state from retirement-filtered rows…~~ **FIXED,
  not deferred.** I first recorded this as a residual risk on the argument that
  the repair "wants its own change". An independent external review on the same
  head raised it as high-severity, and it is the same defect class as the
  `rows_too_narrow` misdiagnosis I had just accepted as must-fix in the same
  round. Deferring one instance of a class while fixing another is not a
  judgement, it is an inconsistency. `all_rows_retired` is the sixth state.
- **The `Removed Requirements` table shape was NOT converged.** It carries a
  different job (`Removed by`, `status`) and no AC asked for it; converging it
  would have been scope creep. It still parses.
- **`label_of_split` renders `03-payments-api` as `Payments Api`.** Deliberate: an
  acronym table is a second source of truth about names. An author who wants
  `API` renames the split.
- **Eight more adopt scaffolders carry the unguarded shared-module loader** —
  `automerge_setup_scaffolder`, `baseline_generator`, `ci_workflow_scaffolder`,
  `claude_review_workflow_scaffolder`, `codeql_workflow_scaffolder`,
  `gitattributes_scaffolder`, `gitleaks_config_scaffolder`,
  `security_workflow_scaffolder`. Each loads a `shared/scripts/lib/*.py` file via
  `spec_from_file_location` and guards only `spec is None or spec.loader is None`,
  which cannot fire for a missing path, so the plugins-without-`shared/` install
  fails as a bare `FileNotFoundError`. **Not fixed here, deliberately:** all eight
  are untouched by this PR, so merging makes nothing worse, and folding eight
  unreviewed edits into the round that was scoped as "these three, then ship" is
  the pattern that has cost this campaign five review rounds. Three instances
  were fixed here because they were in the blast radius
  (`traceability_layers`, `spec_table`, `adopt_brief_intake`); the rest is a
  mechanical one-line-each change that wants its own diff. Found by sweeping for
  the pattern rather than by fixing instances as they were reported — which is
  how the count went from "three" to "eleven".

## A measurement gap that was NOT a code defect (and was fixed, not declared)

Worth recording because the first pass of this run reported around it. Two
symptoms — `plugins/shipwright-grade` failing to collect
(`ModuleNotFoundError: defusedxml`) and `sbom.md` regressing from
`Licenses resolved 11/11` to `3/11` with 8 packages `unknown` — had **one** root
cause: the per-plugin `.venv` directories did not exist in this worktree, and
`_python_license` resolves licenses from each manifest's own `.venv` dist-info
METADATA rather than from ambient `sys.path`, deliberately, for determinism.

I initially declared the test-collection half in `degraded[]` as a pre-existing
environment gap — which was true (it reproduces on an unsynced main tree) but
was the wrong response, and I did not notice the SBOM half at all. A shipped
compliance artifact asserting that 8 dependency licences are unverified is a
false statement about the product, not a measurement inconvenience. Syncing the
14 plugin venvs restored `sbom.md` to 11/11 with 0 unknown — byte-identical to
the pre-change state — and brought `shipwright-grade` in at 385 passed / 1
skipped, raising the honest unit count from 8159 to 8548.

The lesson generalises: *"pre-existing, reproduces on the default branch"*
justifies not treating something as a regression. It does not justify shipping
it inside an artifact this run regenerates.

## Landmine re-verified (S4's correction holds)

**There are ZERO `### Removed Requirements` headings in the live spec.** The three
"occurrences" at lines 127/174/258 are prose inside requirement bodies;
`_HEADING_RE` requires `^#{1,6}\s`. SPEC §2.5's inline `**REMOVED** by` claim is
*also* wrong: the single marker at `01-adopted/spec.md:198` sits inside
`### FR-01.01 — /shipwright-run` and retires a sub-behaviour. Acting on either
claim deletes a live requirement. The migration touched table rows only, by
regex on the row form, and the row count is asserted at 15 before and after.

## Rejected alternatives

- **Emit real `Layers` values.** Hard-aborts on ~10 gaps, and asserts knowledge
  nobody has — the laundering `Basis: assumed` exists to prevent.
- **Misdeclare the iterate as `small` to skip cross-layer.** A misdeclaration, not
  a sanctioned escape. Explicitly refused.
- **Bump the bloat baseline for `fr_table_reader.py` / `group_i.py`.** Suggested
  by a plan reviewer. Refused twice; both files were kept under the cap by moving
  cohesive clusters out (`_fr_table_row`, `group_i_scan`).
- **Map `Source` values by string-munging in the generator.** Rejected: the
  mapping is a decision, recorded above, and the migration refuses unmapped values
  rather than inventing one.
