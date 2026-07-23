# Mini-Plan: iterate-2026-07-21-review-record

## Chosen approach — one record, one writer, one uniform gate

**1. `shared/scripts/lib/review_marker.py` (new, ~70 LOC, pure extraction)**
The marker payload + filename selection currently inlined in
`shared/scripts/checks/mark-review-state.py`. Behaviour unchanged; the script
becomes a thin CLI over it. Exists so the new tool can write the legacy marker
*without duplicating its shape* — the plan plugin (Step 5) keeps its tool and
its contract untouched.

**2. `shared/scripts/lib/review_record.py` (new, ~230 LOC)**
The record: `REVIEW_TYPES` (`self, plan, code, doubt, external_code`), the closed
status vocabulary, `materialize()` (all five as `pending`), `upsert_review()`
with the terminal-status immutability guard, `read_record()`, and a durable
atomic + `file_lock`ed write (repo convention — never temp-file+rename alone).

**3. `shared/scripts/lib/review_findings.py` (new, ~200 LOC)**
Four adapters onto the normalized finding shape. Three are trivial dict
mappings, because the sources are already structured:
- `code-reviewer` JSON → direct
- `doubt-reviewer` JSON → `lens`→category, `claim_under_doubt` + `disproof_attempt`→finding, `what_would_resolve_it`→suggestion
- self-review result JSON → one finding per failed checklist item
- external reviewer **prose** → the only real parser: splits on the
  `Category / Severity / File:line / Finding / Suggestion` layout that
  `shared/prompts/*/system` already mandates, tolerating both observed
  renderings (`- Category:` and `**Category:**`). Unparseable prose degrades to
  ONE finding carrying the raw text — never zero, never a crash.

**4. `shared/scripts/tools/record_review_pass.py` (new, ~180 LOC)**
`init` (create-if-absent), `record` (upsert one type), `close-missing` (close
every still-`pending` type in one command — the escape hatch for runs that
predate this change). For `plan` / `external_code` it also writes the legacy
marker via (1), so each call site makes ONE call instead of two.

Two files are **not** transactional, so the ordering is explicit: validate and
run the immutability check *before* touching anything, write `reviews.json`
first (it is authoritative), then dual-write the marker — shared path exactly as
today, plus a run-scoped copy. Both writes happen under one per-run lock, and
the marker write is idempotent so a partial failure is repairable by re-running.

**5. `shared/scripts/tools/verifiers/review_record_check.py` (new, ~130 LOC)**
`check_review_record` — modelled on `integration_coverage.py`: complexity from
the iterate entry, skip at trivial, explicit-corruption branch, actionable
remediation. Wired into `iterate_checks.run_all_checks`.

**6. Verifier `iterate_compliance` W2 (~+15 LOC)** — also resolve the marker at
`<run_id>/external_review_state.json`. Additive; the shared-file and
`{run_id}-external-review.json` paths keep resolving unchanged. Because the
markers are **dual-written** rather than moved, no existing consumer changes
behaviour at all — this check simply gains the ability to credit a run-scoped
marker, which is the run-specific evidence it has wanted since it labelled the
shared file "run-agnostic".

**7. Prompt contract** — `iteration-reviews.md` (the recording step per pass),
iterate `SKILL.md` (Step 7 / 7.5 / 8 anchors + F11 line), `F11.md`, and
`agents/sub-iterate-runner.md` (campaign parity). Call sites switch
`--planning-dir` to the run-scoped dir.

**8. Tests** — `test_review_record.py` (shape, immutability, materialization),
`test_review_findings.py` (four adapters + both prose layouts + degradation),
`test_review_record_roundtrip.py` (AC4 boundary probe: newlines, quotes,
non-ASCII, null severity), `test_review_record_gate.py` (AC6, all four gate
branches), and one integration test (AC8) — CLI across five types → gate passes.

## Alternative considered — extend `mark-review-state.py` in place

Add `--review-type self|code|doubt` and a `--findings-file` to the existing
tool, writing one marker file per type into the run dir. No new record file, no
new lib.

**Cheaper, and rejected.** The marker is a *gate state* consumed by verifiers
("did this branch run?"); the record is an *artifact* consumed by a UI ("what
did it find?"). They have different lifetimes, different immutability rules, and
different readers. Overloading one file with both means the Mission view reads
five files and reconstructs "which types are missing" itself — the reconstruction
step is precisely what the pinned contract ("missing types represented
explicitly") exists to remove. It would also put the immutability guard on a file
that `/shipwright-plan` overwrites on its own schedule, coupling two lifecycles
that are deliberately independent.

The extraction in (1) keeps the *cheap* part of that alternative: no duplicated
marker shape, one writer per artifact.

## Risks

- **The hard gate lands on every future iterate in every adopted project.** If
  the prompt contract is not followed, runs block at F11. Mitigated by: the file
  auto-creates on first `record`, the failure message names the exact command per
  outstanding type, and `not_applicable` is a legitimate one-line close.
- **Prose splitting is best-effort by nature.** Bounded by degrading to one
  raw-text finding, and by `findings_count` always equalling `len(findings)` so a
  partial split can never overstate what was found.
