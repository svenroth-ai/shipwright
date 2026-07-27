# Mini-Plan — adopt-derived-catalogue-honesty

Run ID: `iterate-2026-07-27-adopt-derived-catalogue-honesty` · medium · Path A.
Scope is `plugins/shipwright-adopt/**` only (plus this iterate's own artifacts).

## Chosen approach

Three mechanisms, all inside the onboarding plugin, wired into the existing
Step E → E.17 → E.18 → F → H order.

### 1. `scripts/lib/derived_catalogue.py` (new, pure)

- `summarize(features, split_name) -> DerivedCatalogue` — per-FR
  `{fr_id, name, basis, confirmed}` plus `total`, `unconfirmed`, `by_basis`.
  `confirmed` is `basis in CONFIRMED_BASES` where `CONFIRMED_BASES = {"interview"}`
  — the only vocabulary value that means a human said so. Everything adopt
  emits today (`code` / `observed` / `assumed`) is therefore unconfirmed, and a
  future interview-backed row becomes confirmed without touching this module.
- `render_provenance_banner(summary) -> str` — a Markdown **blockquote**
  inserted between `## Functional Requirements` and the FR table. Prose only:
  every FR-table consumer (`fr_table_reader`, `traceability_layers`,
  compliance Group I) is line-based on a leading `|`, so a non-table block
  cannot change what any of them reads.
- `write_summary(project_root, summary) -> Path` →
  `.shipwright/adopt/derived-catalogue.json`, `schema_version: 1`.
- `confirmation_triage(summary, spec_rel)` → the follow-up card payload.

### 2. `scripts/lib/inherited_baseline.py` (new, pure)

- `coverage_gaps(fr_ids, backfill_report, skip_inventory)` — requirements with
  no `@FR`-tagged test (`fr_ids − (auto_written ∪ already_tagged)`) and the
  pre-existing disabled tests.
- `build_register(...)` → the `shipwright_known_failures.json` document:
  `known_failures[] · baseline_failure_count` (the shape
  `shipwright-compliance/scripts/lib/collectors/test_evidence.collect_known_failures`
  already reads, verbatim) **plus** additive keys `schema_version`,
  `generated_by`, `adopted_at`, `baseline_observed`, `baseline_source`,
  `inherited_coverage_gaps`. The collector uses `.get`, so additive keys are
  inert there.
- `gap_triage(register)` → one card per non-empty gap class.

**Non-laundering rule, enforced by test:** `inherited_coverage_gaps` never
feeds `baseline_failure_count`. The audit uses that count to *excuse* a
passed<total gap (`rtm_generator` → `COVERED (baseline)`), so folding skipped
or untested items into it would let a genuine future failure read as green.

### 3. `scripts/tools/record_inherited_baseline.py` (new, Step E.18)

Runs after E.17 (which produces the backfill report + skip inventory) and
before F (compliance seeding, so the first seeding already sees the register).
Reads `derived-catalogue.json`, `.shipwright/backfill/backfill-report.json`,
`.shipwright/adopt/traceability-baseline.json`; optionally
`--failures-json <path>` for an observed red baseline; writes the register and
files the triage cards idempotently via `shared/scripts/triage.append_triage_item_idempotent`
(`to_outbox=False`, matching `seed_traceability_baseline._file_triage` so the
cards land in the Step H commit). `--dry-run` writes nothing.

### Wiring (edits, all small)

| File | Change |
|---|---|
| `lib/artifact_writer.py` | `_render_spec_md` inserts the banner; `write_spec` returns/uses the summary |
| `tools/generate_adoption_artifacts.py` | build summary, write `derived-catalogue.json`, expose `results["derived_catalogue"]` |
| `lib/adopt_commit_template.py` | new `unconfirmed_fr_count` kwarg → one extra commit-body line |
| `lib/dry_run_reporter.py` | list the two new artifacts |
| `checks/validate_adoption.py` | hard error when either artifact is missing |
| `skills/adopt/SKILL.md` | new Step E.18 (Kern is at its 300-LOC cap → trim duplicated Step E prose first) |
| `skills/adopt/references/step-e18-inherited-baseline.md` | new step reference |
| `skills/adopt/references/step-h-validate-commit-handoff.md` | banner + commit-message shape |
| `tests/test_skill_references_link.py` | register the new step reference |

## Alternative considered and rejected

**Add a `Confirmed` column to the FR table, or write `code (unconfirmed)` in
`Basis`.** Rejected on evidence, not taste: `FR_TABLE_COLUMNS` is an explicit
two-sided contract (`shared/scripts/lib/fr_table_shape.py`) shared with the
greenfield producer and the compliance reader, so a column change is a
three-plugin change and breaks this card's OWNS boundary; and
`fr_basis.classify` classifies a vocabulary value carrying a qualifier as
**malformed → blocking** under audit check `I5`. The honest marking therefore
lives one level up — at the catalogue, where the claim actually is — in prose a
human reads and JSON a machine reads.

## Risks

- **Kern LOC cap.** `test_kern_skill_md_under_300_loc` fails on any net growth.
  Mitigation: trim Step E prose already carried verbatim by its reference doc.
- **Hard-erroring `validate_adoption`.** A repo adopted before this change now
  fails re-validation. Accepted deliberately: that repo genuinely lacks the
  honesty artifacts, and the message names the step that writes them.
- **ADR-045 `lib` collision.** Both new modules import no `lib` package; the
  new tool follows `seed_traceability_baseline`'s pattern (plugin `lib` on
  `sys.path`, shared `triage` imported lazily at call time).

## Tests (TDD, written first)

`tests/test_derived_catalogue.py`, `tests/test_inherited_baseline.py`,
`tests/test_record_inherited_baseline.py` (subprocess, real CLI), plus
round-trip boundary probes: banner → `fr_table_reader` reads the same rows;
register → the compliance collector reads back exactly what was written.

---

## External plan review — round 1 (openrouter: gemini-3.1-pro + gpt-5.6-terra)

Both reviews succeeded, not degraded. Every finding is dispositioned; nothing
is left merely raised.

| # | From | Sev | Finding | Disposition |
|---|---|---|---|---|
| G1 | gemini | med | additive keys may break a strict JSON schema for `shipwright_known_failures.json` | **Declined — verified false.** `shared/schemas/` holds exactly three schemas (`decision_drop`, `run_config.v2`, `triage_item`); none covers known-failures, and its only reader `collect_known_failures` uses `.get()`. Additive keys are inert. |
| G2 | gemini | med | missing E.17 inputs → `FileNotFoundError` in E.18 | **Accepted.** Every input read through one `_read_json_or_empty` guard; a clean repo yields empty gaps, not a crash. Tested. |
| G3 | gemini | low | `--failures-json` must be optional under `--autonomous` | **Accepted.** Optional; absent ⇒ `baseline_observed: false`, `baseline_source: "not_run"`, count 0. |
| G4 | gemini | low | a `\|` inside an interpolated banner value would be read as a table row | **Accepted — real.** `split_name` / project name are interpolated. All banner values pass through `_prose_safe()` (strips `\|`, collapses newlines). Tested with a pipe-bearing split name. |
| O1 | gpt | **high** | AC4's confirmation card has no owner in the flow | **Accepted.** ONE owner: `record_inherited_baseline.py` (Step E.18) files **both** the confirmation card and the gap cards — it is the only step that runs after the triage inbox exists (E.16). Tested: a normal run files exactly one confirmation card; a re-run files zero. |
| O2 | gpt | **high** | Step H must actually obtain the count and name the follow-up | **Accepted.** `build_adopt_commit_message` takes `unconfirmed_fr_count` as a **required** kwarg, so a caller cannot silently omit it (unit-tested `TypeError`). The Step H reference doc names the artifact to read and the dedup key to cite, pinned by a drift test. Honest limit: the *rendering* of the banner stays prompt-executed. |
| O3 | gpt | **high** | an unobserved baseline could still read as clean to today's consumer | **Accepted as a stated limitation, not silently.** With no file the collector already returns `([], 0)`; writing `baseline_failure_count: 0` changes nothing for it, and a non-zero would be a lie that *excuses* future failures. `baseline_observed:false` + `baseline_source` make the fact recordable; teaching the consumer is `trg-12b4cf3f`, which already owns it — no duplicate card (constitution: triage logs deferred work once). |
| O4 | gpt | med | `validate_adoption` call sites + fixtures | **Accepted.** Inventoried: `tests/test_validate_adoption_soft_checks._make_minimum_valid` is the only fixture builder; `test_snapshot_contract` only name-checks the file. Both new artifacts added to the fixture; error text names the step that writes each. |
| O5 | gpt | med | dedupe key must not vary with the count | **Accepted.** Keys are `adopt-derived-catalogue-confirmation` / `adopt-inherited-gaps::<class>` — count lives in the detail only. Documented: the card is a launch-pointer; the live count is the JSON. |
| O6 | gpt | med | coverage evidence validity + skip-inventory temporal boundary | **Partially accepted.** Accepted: FR ids from the backfill are intersected with the derived catalogue, so an unknown/stale tag cannot count as coverage. Declined-with-reason: re-ordering E.17's inventory to a pre-mutation snapshot is out of this card's OWNS boundary (TT7 owns that step); adopt writes no skipped tests, and the boundary is stated in the module docstring. |
| O7 | gpt | med | validate `--failures-json`; don't let a hand-authored empty file read as observed | **Accepted.** Closed input schema; `baseline_observed: true` only when the payload declares a real run (`source` **and** `command`); malformed or inconsistent input **fails closed** (non-zero exit), never a silent zero-count register. |
| O8 | gpt | med | JSON summary can drift from the rendered table | **Accepted — best finding.** Both are produced from the same feature sequence, and a contract test parses the final `spec.md` with `fr_table_reader` and compares ids + basis + count against the JSON. This doubles as the `touches_io_boundary` round-trip probe. |
| O9 | gpt | low | `--failures-json` could carry secrets into a committed artifact | **Accepted.** Only the five fields the collector reads (`test`, `description`, `ticket`, `added`, `count`) are copied; everything else is dropped. Tested with a payload carrying an `env`/`stdout` field. |

---

## External CODE review — round 2 (openrouter: gemini-3.1-pro + gpt-5.6-terra)

Run over the staged `plugins/` diff. Both succeeded, not degraded.

| # | From | Sev | Finding | Disposition |
|---|---|---|---|---|
| C1 | gemini | med | `_clean_failure` emits `""` for absent optional fields; the compliance collector may expect the keys omitted | **Declined — verified false.** `collectors/test_evidence.py:171-180` reads every one as `f.get("<field>", "")`, so an explicit `""` IS its default. The subprocess round-trip test already exercises the real collector against a written register. (Feedback also arrived truncated mid-sentence.) |
| C2 | gpt | **high** | `catalogue_from_document` used `bool(r.get("confirmed"))`, so `"confirmed": "false"` reads as **True** — a malformed or hand-edited catalogue could report zero unconfirmed requirements and silently suppress the confirmation follow-up | **Accepted — the best finding of the run.** It defeats the single guarantee the artifact exists to carry. Reading now **fails closed**: `schema_version == 1`, non-empty `requirements`, per-row non-empty `fr_id`, and `confirmed` must be a genuine `bool`. Stated `total`/`confirmed`/`unconfirmed` are recomputed from the entries and a disagreement is **rejected** rather than overridden — the contradiction is itself the signal. The CLI turns any of these into a non-zero exit naming Step E. Seven parametrized rejection cases + an end-to-end CLI case. |
| C3 | gpt | med | `_read_json_or_empty` treated a **corrupt** upstream artifact the same as an absent one, so a broken `backfill-report.json` would make E.18 record every requirement as untested and file triage cards asserting an inherited state it never read | **Accepted.** Split: absent → `{}` (a zero-test repo is the normal cleanest case); present-but-unreadable, or not a JSON object → non-zero exit naming the step that writes it. Covered end-to-end. |
| C4 | gpt | med | the confirmation card embeds a count, the dedup key is stable, and the triage layer has **no update path** — so a re-adopt leaves a stale number in the card | **Accepted, resolved by wording rather than machinery.** `append_triage_item_idempotent` appends or suppresses; adding an update path means changing shared triage, which is outside this card's OWNS boundary. The card now states its figures **as of onboarding** — a timestamped claim that stays true — and points at `derived-catalogue.json` for what is true now. Pinned by test. |

**Two structural consequences, both taken:** `derived_catalogue.py` crossed the
300-LOC source cap once the validation landed, so the serialized side moved to
`derived_catalogue_doc.py` (one-way dependency: doc → model). `test_derived_catalogue.py`
split the same way. Nothing was grandfathered.

**The new self-consistency guard immediately caught a fixture in this very
iterate** — a test built a 1-row catalogue while leaving `total: 3` in place.
That is the check doing its job on the first thing it looked at.
