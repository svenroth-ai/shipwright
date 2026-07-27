# Iterate ADR — Compliance evidence discloses when the cross-check last ran

- **Run-ID:** iterate-2026-07-27-disclose-audit-last-run
- **Standalone iterate** (NOT a campaign). Closes triage `trg-a1fd8125`.
- **Complexity:** medium · **change_type:** change · **spec_impact:** modify (FR-01.10 gains one (E) AC)
- **Owns:** the compliance dashboard and the report renderers.
  **Does NOT own** artifact run-id stamping — that is `trg-4d5b6a56`, extracted so it is built
  once. Nothing here stamps a run identifier into a document; this iterate adds exactly one new
  fact to the documents (when the cross-check last ran) and nothing else.

## Problem statement

`FR-01.10` promises "an on-demand cross-check that reports where that evidence disagrees with
reality". That cross-check (`run_audit.py`, the detective audit) is wired to **no trigger**: no
cron, no workflow, no hook. It runs only when someone invokes `/shipwright-compliance`.

That is the right design and stays — the operator decided against a schedule, because a check
nobody asked for produces warnings nobody wants. The defect is not the absence of a trigger; it
is that **the evidence documents do not say the check has not run.** Empirically, on `main` today:

- `.shipwright/compliance/dashboard.md:84` reads
  `_Detective cross-artifact audit not run this session — run /shipwright-compliance to refresh._`
  Read literally that is a statement about *this session*, not about the project. It is the same
  sentence whether the audit ran yesterday or has never run in the repo's life.
- `traceability-matrix.md`, `test-evidence.md`, `change-history.md` and `sbom.md` say **nothing at
  all**. Each carries only `Generated: <ts>` — which is when the document was *written*, never
  whether anything checked it.
- The audit's own outputs (`audit-report.md` / `audit-report.json`) are **gitignored transients**
  (`.gitignore:205-206`), so they are absent on a fresh clone, in CI, and on the public repo.
  The dashboard's existing summary therefore renders from a file that only exists on the machine
  that last ran the audit — the tracked document's content depended on local, untracked state.
- The tracked event log records no audit event at all (`shipwright_events.jsonl` types:
  `adopted`, `work_completed`, `phase_completed`, `compliance_update_failed`, `event_amended`,
  `grade_snapshot`) — so there was no durable record of a run anywhere.

Net: in a project where nobody thinks of the audit for three months, divergence accumulates while
the documents look unchanged and trustworthy the whole time. This iterate turns
**possibly-never-checked** into **visibly-not-checked-since**.

## Alternatives considered

- **Alt A (rejected): add a schedule / CI trigger.** Explicitly rejected by the operator and
  restated in the card — a check nobody asked for produces warnings nobody wants. On demand stays.
- **Alt B (rejected): keep rendering from the gitignored `audit-report.json`.** The tracked
  documents would then say different things on different machines (dev has the transient, CI does
  not), churning tracked files and making "not run" unfalsifiable. A disclosure whose value
  depends on untracked local state is not evidence.
- **Alt C (rejected): a new tracked artifact `.shipwright/compliance/audit-freshness.json`.**
  A whole new artifact (plus gitignore-canon, path-canon and DOC_REGISTRY questions) for four
  scalars, when a tracked file that already holds exactly this class of state exists.
- **Alt D (rejected): append an audit event to `shipwright_events.jsonl`.** The event log is
  cross-component machinery (churn resolver, merge union, schema consumers); adding an event type
  to carry a single "last ran" fact buys nothing a config key does not, and buys merge risk.
- **Chosen: record the run in `shipwright_compliance_config.json`, render it from `ComplianceData`.**
  That config is already a mixed settings+state file written by read-modify-write from
  `update_compliance.py` (`status`, `phases_covered`, `last_full_generation`, `seeded_by_adopt`
  are all machine-written run state). It is tracked, has no schema, and is read loosely by every
  consumer, so an additive key is safe. The audit is its own producer; the renderers are pure
  consumers.

## Design

1. **New leaf module** `plugins/shipwright-compliance/scripts/lib/audit_disclosure.py` — the single
   home for the fact and both of its renderings. Stdlib-only.
   - `record_audit_run(project_root, *, findings, any_fail, scope)` — read-modify-write of
     `shipwright_compliance_config.json`, preserving every other key; writes
     `last_audit = {ran_at, verdict, scope, checks:{total,pass,fail,skip}}`.
   - `read_last_audit(project_root)` — tolerant reader (absent file / unreadable / non-object root
     / non-object value / missing `ran_at` ⇒ `None`).
   - `freshness_note(project_root, as_of)` — the compact ` · Consistency audit: …` suffix carried
     by every evidence-document header.
   - `render_consistency_audit(project_root, as_of)` — the dashboard's rich block. **Moved here**
     from `_control_block.py` and rewritten to read the durable record instead of the transient.
2. **`_control_block.py`** — `render_consistency_audit` and `_audit_generated_date` deleted; the
   name is re-exported from the new module so `compliance_report.py`'s existing import line is
   unchanged. Net −45 lines.
3. **`ComplianceData.audit_freshness_note: str = ""`** — collected once in `collect_all` (like
   `timestamp`) and interpolated verbatim by every renderer. Collect-once/render-many is why this
   is a field and not a per-renderer import: the fact is one header fact shared by five documents,
   and four of those renderers are grandfathered at their anti-ratchet ceiling with zero headroom
   (a new import line in each would be four ratchet blocks). Directly-constructed
   `ComplianceData` (tests, fixtures) defaults to `""` and renders exactly as before.
4. **Renderers** — one-for-one line edits appending `{data.audit_freshness_note}` to the
   `Generated:` line in `rtm_generator`, `test_evidence`, `sbom_generator`, `change_history`.
   The dashboard does not carry the suffix: it has the full section.
5. **`run_audit.py`** — records the run after the report is written, on **every** invocation
   including a failing audit and a `--only` partial run. Fail-soft: a recording failure never
   changes the audit's exit code.
6. **Determinism.** Age is computed against `data.timestamp` (the event-pinned reference the
   `Generated:` banner already uses), never wall-clock. The render is a pure function of
   **(event log, durable record)** — running the audit between two regens *does* change the
   documents, which is the feature; what can never change them is the clock. This restates,
   rather than weakens, `iterate-2026-05-22-deterministic-render-timestamps`: the record is an
   explicit render input, pinned in `test_the_audit_record_is_an_explicit_render_input`.
7. **Two records, not one.** `last_audit` (latest run, any scope) and `last_full_audit` (latest
   whole-project run). One slot would let a Friday `--only A` erase Thursday's full audit and
   leave the documents reading "partial" indefinitely — losing exactly the answer a reader wants.
8. **The audit refreshes what it discloses.** `/shipwright-compliance` recorded the run but
   regenerated nothing, so the documents would keep reporting the *previous* answer — usually
   "never run" — at the exact moment the operator asked for the check. `PHASE_REPORTS["compliance"]`
   now covers all five documents (an audit changes the disclosure every one of them carries, not
   just the dashboard's section) and the skill gained Step 2b to invoke it after every audit,
   including a failing one.
9. **Absent ≠ unreadable.** A damaged record renders as *unknown*, never as "never run": the
   latter asserts something the project cannot know, which is the failure mode this iterate
   exists to remove. Stored values are validated before they reach markdown — the config is
   tracked and hand-editable, so a hostile `scope` or a string check-count must not inject
   layout into compliance evidence.

## Acceptance criteria

- **AC-1** Given any compliance evidence document (dashboard, RTM, test evidence, change history,
  SBOM), when it is generated, then it discloses when the consistency audit last ran.
- **AC-2** Given no audit run has ever been recorded, when a document is generated, then it says
  the check has never run, explicitly — silence is not an option.
- **AC-3** Given a recorded run, when a document is generated, then the disclosure carries how
  long before that document's own reference point the check happened, so a reader can weigh it.
- **AC-4** Given the audit runs, when it finishes, then the run is recorded durably in tracked
  state — including a failing audit — so the disclosure survives a fresh clone.
- **AC-5** Given a partial audit (`--only A,B`), when it is recorded, then the disclosure names it
  as partial, so it cannot be read as a full cross-check.
- **AC-6** Given the dashboard, when it is generated, then its Consistency Audit section renders
  from the durable record only, so the tracked document reads identically on every machine, and
  states that the check is on demand by design.
- **AC-7** Given the durable record is absent or malformed, when a document is generated, then the
  disclosure degrades to the never/unknown wording and the regen still completes.

## Scope

Disclosure only. Explicitly out of scope: any trigger for the audit (Alt A), run-id stamping
(`trg-4d5b6a56`), and any change to what the audit checks.

### Deliberate: this PR ships with the record EMPTY ("never run")

A full audit was run during development (probe 3) and its record was deliberately **not**
committed. Any audit run mid-iterate fails Group E by construction — the working tree's compliance
documents necessarily differ from the last commit's snapshot while the iterate is in flight — so
the recorded verdict would have been `fail`, dominated by staleness this very commit resolves,
plus the known-false-positive D1/D3. Committing that as the repository's official last cross-check
would ship a misleading document from the change whose entire purpose is to stop documents from
misleading. The repo therefore ships in the honest `never run` state — no operator-initiated audit
has been recorded — and the first `/shipwright-compliance` after merge writes the first meaningful
record, with Step 2b making it visible in all five documents immediately.

## Guardrails honored

- Anti-ratchet: the four grandfathered renderers (`compliance_report` 359, `rtm_generator` 763,
  `test_evidence` 906, `sbom_generator` 522) are all exactly at baseline with zero headroom, so
  every edit in them is line-neutral; `_types.py` stays at exactly 300.
- Determinism of the compliance render (event-pinned, no wall-clock in any render path).
- ADR-045 lib discipline: the new module lives in the plugin's own `lib/`, stdlib-only.

## External-Plan-Review-Findings (Step 3.5 — Gemini 3.1 Pro + GPT-5.6 via OpenRouter, both succeeded)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| G1 / O1 | Med / High | Time-math inversion: `ran_at` is wall-clock, `as_of` is event-pinned, so a normal audit run yields a negative age. O1 adds: "regenerating from an unchanged event log after an audit changes the document", contradicting the determinism claim. | **accepted-and-fixed (already-clamped + claim restated)** — `_age_phrase` clamps `days <= 0` → `same day` (pinned by `test_audit_newer_than_the_render_reference_clamps`). The determinism *claim* was wrong and is corrected: the render is pure over **(event log, durable record)**, and the record is now an explicit render input with its own test. |
| G2 / O5 | Med | A partial `--only` run overwrites the single record, erasing the last full audit; the documents then read "partial" indefinitely. | **accepted-and-fixed** — split into `last_audit` + `last_full_audit`. The header leads with the last *full* cross-check and reports the partial alongside it; a project with only partial runs reads "never fully run". |
| O2 | High | `read_last_audit` collapses absent / malformed / missing-`ran_at` into `None`, so a damaged record renders as "never run" — a materially false statement. | **accepted-and-fixed** — `load_audit_freshness` returns `absent` / `valid` / `invalid`; the renderer says "never run" only for absent and "last-run record unreadable — … unknown" for invalid. |
| O3 | High | Read-modify-write of a shared tracked config can lose updates / corrupt on overlap. | **partially-accepted** — writes are now atomic (temp + `os.replace`, temp cleaned on failure), strictly better than the existing `update_compliance.py` writer. A project-scoped lock was **not** added: there is no such protocol for this file today, and last-writer-wins between two concurrent writers is a pre-existing property of the existing writer, not something this card introduces. |
| O4 | Med | "Survives a fresh clone" only holds once the config is **committed**; a bare `run_audit.py` leaves a dirty tree. | **accepted-as-documentation** — stated in the module docstring and the guide; the config ships in this commit with the rest of the compliance write-set. |
| G3 / O7 | Low / Med | Fail-soft recording is silent: a failed write leaves every document claiming "never run" with no signal. O7 adds: what about an audit that aborts? | **accepted-and-fixed** — `run_audit` now prints a `WARNING` to stderr when a completed run could not be recorded. Aborted runs already record nothing: the `exit 2` (bad root) and `exit 3` (import-gate) returns both precede the recording call, so a stored record always means "this audit finished". |
| O6 | Med | The durable record must preserve what the transient rendered and distinguish completed-clean / with-findings / with-skips / partial. | **already-satisfied** — `verdict` + `checks{total,pass,fail,skip}` + `scope` cover every state the old block rendered, plus scope, which it lacked. |
| O8 | Low | Values from a tracked, hand-editable JSON are interpolated into markdown — a hostile `scope` can inject layout. | **accepted-and-fixed** — `ran_at` must parse as ISO-8601 (else the record is `invalid`), `verdict` must be `pass`/`fail`, `scope` is stripped to `[A-Za-z0-9,_-]` capped at 40 chars, on **both** write and read. |
| G4 | Low | JSON dump params must match `update_compliance.py` or the file will thrash. | **already-satisfied** — identical `json.dumps(..., indent=2, ensure_ascii=False) + "\n"`; pinned by `test_written_file_is_valid_utf8_json_with_trailing_newline`. |
| O9 | Med | No regression coverage for the state contract and all five render paths; existing doc snapshots could depend on a developer's local audit state. | **accepted-and-fixed** — 82 tests across five modules cover every state × every document. Existing fixtures use `tmp_path` roots with no compliance config, so they render the deterministic `absent` state. |

## External-Code-Review-Findings (Step 3.7 — GPT-5.6 succeeded; Gemini truncated)

| # | Sev | Finding | Disposition |
|---|-----|---------|-------------|
| C1 | Med (bug) | **Upgrade path data loss.** A config written before `last_full_audit` existed holds its full run only under `last_audit`. The first `--only` run after the upgrade overwrites that slot and leaves `last_full_audit` absent, so the project silently reads "never fully run" despite a durable prior full run. | **accepted-and-fixed** — `record_audit_run` promotes a valid *full* `last_audit` into `last_full_audit` before a partial run overwrites it. Regressions: `test_a_partial_run_promotes_a_pre_upgrade_full_record` + the negative case `test_a_partial_run_does_not_promote_a_prior_partial_record`. |
| C2 | Med (security) | Check counts are interpolated into dashboard markdown without type validation; a string count in the tracked, hand-editable config injects arbitrary markdown — contradicting the module's own stated intent. | **accepted-and-fixed** — `_clean_checks` keeps only non-negative `int` counts (bools excluded) at parse time; anything else is dropped and the counts sentence is omitted. Regression: `test_non_integer_check_counts_are_dropped`. |
| C3 | Low (test) | The partial-preserves-full test only covers records made by the new writer, so it misses the real upgrade state. | **accepted-and-fixed** — the C1 regression seeds the pre-upgrade shape directly (`last_audit` only, no `last_full_audit`). |
| C-Gemini | — | Response truncated at 478 chars mid-analysis (echoed source, no finding reached). | **no actionable defect** — GPT's pass covered the same diff and produced three findings, all fixed. |

Overall: GPT rated **ship-with-fixes**; both bugs fixed and pinned before commit.

## Internal review cascade

`code` and `doubt` (the `code-reviewer` / `doubt-reviewer` subagents) were **not run**: this
session prohibits the Agent tool. Both rows are closed explicitly in `reviews.json` with that
rule named — an empty Review row must mean "genuinely not run", never "nobody wrote it down".
The adversarial function was carried by the two external code reviewers, which found and fixed
two real bugs (C1, C2).

## Self-Review (Step 7 — canonical 7-item checklist)

1. **Spec Compliance** — PASS. All seven ACs are implemented and pinned by tests: every evidence
   document discloses the last cross-check (AC-1), never-run is explicit (AC-2), the age is
   relative to the document's own reference (AC-3), the audit records itself durably including on
   failure (AC-4), a partial run is named as partial and cannot erase the last full one (AC-5),
   the dashboard renders from the durable record only (AC-6), and a damaged record degrades to a
   stated *unknown* without aborting the regen (AC-7). No trigger was added — the on-demand design
   is untouched, as the card requires. No run-id stamping (that is `trg-4d5b6a56`).
2. **Error Handling** — PASS. Every read path is tolerant (absent / unreadable / non-object root /
   non-object record / bad timestamp / bad verdict) and resolves to `absent` or `invalid`, never a
   crash inside a compliance regen. The write path refuses to clobber an unparseable config, is
   atomic, cleans up its temp file on failure, and reports failure both in the JSON payload and
   loudly on stderr — while never changing the audit's exit code.
3. **Security Basics** — PASS. The record is tracked and hand-editable, so every value that
   reaches markdown is validated: `ran_at` must parse as ISO-8601, `verdict` ∈ {pass, fail},
   `scope` stripped to `[A-Za-z0-9,_-]` (≤40 chars) on both write and read, check counts kept only
   when non-negative `int`. No shell, no network, no dynamic import; JSON is parsed, never eval'd.
4. **Test Quality** — PASS. 82 tests over five modules: the writer (durability, key preservation,
   fail-soft, round-trip), the state contract (scope bookkeeping incl. the upgrade path, the four
   trust states, hostile values), rendering (four states × age arithmetic × single-line contract),
   the five documents end-to-end through the real `collect_all`, and the CLI itself so the wiring
   cannot be silently dropped. Behaviour-asserting, not implementation-asserting.
5. **Performance Basics** — PASS. One extra small JSON read per compliance regen (`collect_all`
   already reads several configs); rendering is pure string work. No new I/O in any hot path.
6. **Naming & Structure** — PASS. Fact and rendering are separate modules (`audit_disclosure` /
   `_audit_disclosure_render`), mirroring the existing `_control_block` / `_dashboard_sections`
   pattern. Every touched grandfathered file is **exactly** at its anti-ratchet baseline (359 /
   763 / 906 / 522 — every edit line-neutral by design); `_types.py` holds at exactly 300;
   `_control_block.py` shrank 296 → 247. No new 300-line crossings.
7. **Affected Boundaries (ADR-024)** — PASS. One new serialized boundary: the `last_audit` /
   `last_full_audit` block in `shipwright_compliance_config.json`, written by `run_audit.py` and
   read by the compliance renderers. Producer and consumer are round-trip tested
   (`test_round_trips_through_the_file`) and every malformed-input axis is covered. No schema
   exists for this config and every consumer reads it loosely, so additive keys break nothing.

## Confidence Calibration

- **Boundaries touched:** (1) `shipwright_compliance_config.json` — new `last_audit` /
  `last_full_audit` keys (producer: `run_audit.py`; consumers: all five compliance renderers via
  `collect_all`); (2) `ComplianceData` — new `audit_freshness_note` field on the B8 cross-plugin
  contract (additive, defaults to `""`, appended last so positional construction is unaffected);
  (3) the rendered markdown header line of four evidence documents. No event-log, hook, workflow
  or phase-validator surface is touched (`cross_component` does not apply).
- **Empirical probes run:**
  - *Probe 1 — what does the repo actually say today?* Read the committed `dashboard.md:84`:
    `_Detective cross-artifact audit not run this session…_` — a sentence about the session, not
    the project, identical whether the audit ran yesterday or never. The other four documents say
    nothing at all. Finding: the defect is real and live in tracked artifacts.
  - *Probe 2 — is there any durable record to read?* Counted event types in
    `shipwright_events.jsonl`: `adopted`, `work_completed`, `phase_completed`,
    `compliance_update_failed`, `event_amended`, `grade_snapshot` — no audit event, and both audit
    reports are gitignored (`.gitignore:205-206`). Finding: nothing durable existed; a new record
    was required, not merely a new render.
  - *Probe 3 — does the producer work on a real repo?* Ran the real `run_audit.py` against this
    worktree: 58 checks (38 pass / 10 fail / 10 skip), `recorded: true`, `scope: full`. Finding:
    end-to-end wiring works on real data, and the ten fails are pre-existing (E* staleness vs an
    older snapshot, the known-false-positive D1/D3, H1 flagging four files none of which are mine).
  - *Probe 4 — does the render change?* Re-rendered against the real repo: header now reads
    `Generated: … · Consistency audit: never run — this evidence has never been cross-checked`,
    and the dashboard section states it plainly plus why nothing will fix it on its own.
  - *Probe 5 — is the anti-ratchet constraint actually met?* Measured every touched file against
    `shipwright_bloat_baseline.json` by `\n`-count (the gate's own measure): all four grandfathered
    renderers exactly at baseline, no new 300-crossings.
  - *Probe 6 (F0 finding) — does the import chain hold under both package roots?* The F0 gate
    turned `integration-tests/test_fr_table_shape_convergence.py` red (15 failures): that tooling
    puts `…/scripts` on `sys.path` and imports `lib.collectors`, under which the absolute
    `from scripts.lib.audit_disclosure import …` in the new render module does not resolve
    (ADR-045). Fixed to a relative import and pinned close to the code by
    `TestImportDiscipline::test_collectors_import_under_the_bare_lib_package_root`, so the next
    editor finds out here instead of in a distant integration test.
- **Test Completeness Ledger:** every behaviour introduced by this diff, `tested` or `untestable`
  with a closed-vocabulary reason. 0 testable-but-untested.

  | # | Behaviour | AC | Disposition | Evidence |
  |---|-----------|----|-------------|----------|
  | 1 | Each of the four evidence documents discloses the last cross-check on its `Generated:` line | AC-1 | tested | `test_evidence_docs_disclose_audit.py::test_never_run_is_disclosed_in_every_document` + `…::test_recorded_run_is_disclosed_in_every_document` (parametrized over all four) |
  | 2 | The dashboard carries the full section instead of the header suffix (no double-disclosure) | AC-1 | tested | `…::test_dashboard_carries_the_section_not_the_header_suffix`, `…::test_dashboard_section_reflects_a_recorded_run` |
  | 3 | The disclosure is additive — the generation timestamp is still readable | AC-1 | tested | `…::test_disclosure_does_not_displace_the_generated_timestamp`, `test_sbom_keeps_its_own_header_qualifier` |
  | 4 | Never-run is stated explicitly, in both renderings | AC-2 | tested | `test_audit_disclosure_render.py::test_never_run_says_so_explicitly`, `…::test_never_run_is_stated_plainly` |
  | 5 | Age relative to the document's own reference; same-day, singular day, plural days | AC-3 | tested | `…::test_records_the_date_and_the_age`, `…::test_same_day_reads_as_same_day`, `…::test_one_day_is_singular` |
  | 6 | A reference that trails the audit clamps instead of rendering a negative age | AC-3 | tested | `…::test_audit_newer_than_the_render_reference_clamps` |
  | 7 | A completed audit records itself durably: counts, verdict, scope, timestamp | AC-4 | tested | `test_audit_disclosure.py::test_records_run_with_counts_and_verdict`; CLI-level `test_run_audit_records_run.py::test_a_full_run_is_recorded_in_tracked_state` |
  | 8 | A failing audit is still recorded (it still happened) | AC-4 | tested | `…::test_failing_audit_is_still_recorded`, `test_audit_disclosure_render.py::test_failing_run_names_the_drift` |
  | 9 | Recording preserves every unrelated config key (read-modify-write) | AC-4 | tested | `…::test_preserves_unrelated_config_keys`; CLI-level `…::test_recording_does_not_disturb_an_existing_config` |
  | 10 | The write is atomic and leaves no temp file behind | AC-4 | tested | `test_audit_disclosure_state.py::test_no_temp_file_is_left_behind` |
  | 11 | Producer→consumer round-trip: what is written is what is read | AC-4 | tested | `…::test_round_trips_through_the_file` (Boundary Probe for `touches_io_boundary`) |
  | 12 | A partial run is recorded and disclosed as partial | AC-5 | tested | `test_audit_disclosure_state.py::test_a_partial_run_never_erases_the_last_full_check`; CLI-level `…::test_a_partial_run_is_recorded_as_partial`; render `…::test_partial_run_does_not_displace_the_last_full_check` |
  | 13 | A pre-upgrade full record is promoted before a partial run overwrites it | AC-5 | tested | `…::test_a_partial_run_promotes_a_pre_upgrade_full_record` (+ negative: `…_does_not_promote_a_prior_partial_record`) |
  | 14 | A project with only partial runs reads "never fully run" | AC-5 | tested | `…::test_partial_only_project_says_never_fully_run` (note + dashboard) |
  | 15 | The dashboard renders from the durable record only — the gitignored transient cannot change it | AC-6 | tested | `…::test_gitignored_transient_does_not_change_the_render` |
  | 16 | Rendering is deterministic; the audit record is an explicit render input, the clock is not | AC-6 | tested | `…::test_render_is_deterministic`, `…::test_render_stays_byte_stable_across_regens`, `…::test_the_audit_record_is_an_explicit_render_input` |
  | 17 | A damaged record reads as *unknown*, never as "never run" | AC-7 | tested | `test_audit_disclosure_state.py::test_damaged_records_are_invalid_not_absent` (6 shapes), render `…::test_unreadable_record_is_unknown_not_never`, `…::test_damaged_record_renders_as_unknown` |
  | 18 | An unparseable / non-object config never aborts a compliance regen | AC-7 | tested | `…::test_unparseable_config_is_invalid`, `…::test_non_object_config_root_is_invalid` |
  | 19 | An unwritable or corrupt config is reported, never clobbered, never raised | AC-7 | tested | `test_audit_disclosure.py::test_never_raises_on_an_unwritable_config`, `…::test_corrupt_config_is_not_clobbered_silently` |
  | 20 | Hostile `scope` / non-integer counts never reach a rendered document | AC-7 | tested | `test_audit_disclosure_state.py::test_a_hostile_scope_value_is_stripped_before_it_is_stored`, `…_on_read`, `…::test_non_integer_check_counts_are_dropped` |
  | 21 | The note is always single-line and never empty (it rides a header) | AC-1 | tested | `…::test_note_is_a_single_line` (all four states) |
  | 22 | A directly-constructed `ComplianceData` renders exactly as before | — | tested | `…::test_directly_constructed_data_renders_without_the_note` |
  | 23 | `run_audit` warns on stderr when a completed run could not be recorded | AC-4 | untestable → `covered-by-existing-test` | The failure branch itself is pinned by `test_never_raises_on_an_unwritable_config` (the `recorded: False` payload it keys off). The added `print(..., file=sys.stderr)` is a one-line diagnostic on that already-covered branch; asserting console text would pin wording, not behaviour. |
  | 24 | The compliance phase regenerates **all five** documents, so an audit's answer is visible immediately instead of one regen cycle later | AC-1 | tested | `test_disclosure_e2e.py::test_the_compliance_phase_refreshes_every_documents_disclosure` |
  | 25 | The whole chain works through the real CLIs: cross-check → durable record → regenerated documents on disk | AC-1, AC-4 | tested | `test_disclosure_e2e.py` (5 tests — never-run state, post-audit state, partial-vs-full, disclosure byte-stability, phase refresh); this module is the F0.5 surface runner |
  | 26 | The disclosure modules import under both the `scripts.lib.*` and bare `lib.*` package roots (ADR-045) | — | tested | `test_audit_disclosure.py::TestImportDiscipline::test_collectors_import_under_the_bare_lib_package_root` |

- **Confidence-pattern check:**
  - *Asymptote (depth):* the risky axis is the **claim** each state makes, not the plumbing. Four
    states (never / unknown / partial-only / checked) are each pinned in both renderings, and the
    two ways to make a false claim — collapsing absent into unknown, and letting a partial run
    stand in for a full one — are exactly the two bugs the external reviewers found. Both are now
    fixed and pinned by regressions, including the negative cases.
  - *Coverage (breadth):* all five documents are exercised through the real `collect_all` (not a
    synthetic `ComplianceData`), so a break in either collection or rendering fails; the CLI is
    driven as a subprocess so dropping the recording call fails; all four grandfathered renderers
    are verified against the anti-ratchet baseline.
  - *Integration composition:* not applicable — `cross_component` does not fire (no merge/churn
    resolver, hooks, phase validator or campaign machinery in the diff). Confirmed by inspection
    of `risk_detectors.CROSS_COMPONENT_FILE_PATTERNS` against the changed-file list.
  - *Residual risk (stated, not hidden):* two concurrent writers of
    `shipwright_compliance_config.json` are still last-writer-wins (O3, pre-existing property of
    `update_compliance.py`); and `--only` values are sanitized for rendering but not validated
    against the audit's canonical group letters, so a typo'd group records as a partial run over
    nothing rather than being rejected.
