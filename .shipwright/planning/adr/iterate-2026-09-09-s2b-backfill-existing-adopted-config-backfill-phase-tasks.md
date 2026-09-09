# Backfill phase_tasks[] into already-adopted configs

**Run-ID:** iterate-2026-09-09-s2b-backfill-existing-adopted-config
**Campaign:** p4-04-retire-write-once-steps, sub-iterate s2b (backfill-existing-adopted-config)

## Context

Sub-iterate s2 made adopt seed `phase_tasks[]` entries marked
`establishedAtAdoption: true` for every NEW adoption. That only serves
future adoptions: a repo adopted before s2 landed (2026-09-09) has
`completed_steps` and `phase_history` but no `phase_tasks[]` at all, and
readers migrated to no longer consult `completed_steps`
(`plugins/shipwright-compliance/scripts/lib/mermaid.py`'s
`_get_phase_status`, once such a repo is later picked up by
`/shipwright-run` for a new feature and its run-level `status` leaves
`complete`) would render its adoption-era phases as pending. This
sub-iterate gives that already-on-disk gap an owner. `leadwright`
(`C:\01_Development\leadwright`, a sibling checkout on this machine) is
the spec's named live case; no other pre-existing `/shipwright-adopt`
output was reachable from this monorepo's own fixtures, docs, or tests —
Shipwright keeps no registry of the repositories it has onboarded.

## Decision

`plugins/shipwright-adopt/scripts/lib/adopted_phase_tasks.py` (the module
s2 already owns for the `PhaseTask` shape) gains a pure function,
`backfill_missing_phase_tasks(run_config, *, now)`: for each
`completed_steps` phase not already represented in `phase_tasks[]` (by its
`phase` key, from any writer), build one entry via the same
`build_adopted_phase_task` s2 uses, and return a NEW config dict — the
input is never mutated. A new CLI,
`plugins/shipwright-adopt/scripts/tools/backfill_phase_tasks.py`, is the
I/O wrapper: read `shipwright_run_config.json`, call the pure function,
write back only when something was actually added.

Chosen mechanism: re-run the seed logic against the existing config file
in place. `shared/scripts/tools/convert_configs_to_events.py` (the spec's
other named option) was examined and rejected — it derives
`shipwright_events.jsonl` from `completed_steps`/build-config sections, an
unrelated event-log format; it has no `phase_tasks[]` concept and touching
it would not address this gap at all.

Guarded to configs with a JSON-object `adoption` key (shipwright-adopt's
own writer marker) — see Rejected Alternatives for why no broader
discovery was built. A phase name outside the schema's `Phase` enum (old
configs never validated `completed_steps`) is skipped and reported, not
fatal to the rest of the backfill.

## Consequences

- A repo adopted before 2026-09-09, once backfilled, reads identically to
  one s2 wrote fresh through every reader that already trusted s2's output
  (AC1) — proven against the real leadwright config, not only a synthetic
  fixture (AC3): `tests/fixtures/backfill_phase_tasks/leadwright_run_config.json`
  is a verbatim copy of its on-disk `shipwright_run_config.json`, run
  through the CLI and then through the real `mermaid._get_phase_status`
  (file-path load, ADR-045) and, via subprocess-isolated real imports in
  `integration-tests/test_adopt_phase_tasks_read_by_shared_readers.py`,
  through `handoff_pipeline.render_pipeline_phases` and
  `phase_quality._engagement.has_phase_tasks`.
- `--dry-run` was additionally run against the ACTUAL live leadwright
  checkout on disk (not a copy) and produced exactly the four phases the
  fixture predicted, with zero write — confirmed the fixture has not
  drifted from the real repo's current state. The live file was
  deliberately left untouched: writing it is an operator decision this
  sub-iterate documents and enables, not one it performs unattended
  against a repository this monorepo does not own.
- Idempotent (AC2): a phase already represented in `phase_tasks[]` is
  never re-added; the CLI does not even call `write_text` on a no-op run
  (proven structurally via a monkeypatch, not only by an mtime check,
  after external review flagged mtime-only proof as filesystem-dependent).
- `plugins/shipwright-adopt/skills/adopt/references/backfill-phase-tasks.md`
  documents when/how to run it, linked from `SKILL.md`, mirroring the
  existing `backfill-iterate-config.md` precedent.

## Rationale

Reusing `build_adopted_phase_task` (rather than a second, independent
entry-builder) guarantees a backfilled entry's `status` always agrees with
`write_run_config`'s own `phase_history[phase].outcome` for any config
this codebase produced — both are keyed by the identical phase-NAME rule
(`test` -> skipped, else done), so nothing needs to be read back out of
`phase_history` at call time to reconcile them; pinned directly with
`test_the_test_phase_backfills_as_skipped_matching_phase_history`.

## Rejected Alternatives

- **A fleet-wide `--scan <root>` discovery mode**, raised by both the
  external plan review and the external code review (twice, independently
  landing on the same gap) — rejected: this monorepo keeps no registry of
  repositories `/shipwright-adopt` has onboarded, so there is nothing to
  enumerate against from inside it; an unbounded filesystem walk would
  also reach directories no operator asked this tool to touch. The tool
  takes one explicit `--project-root`, the same operational model as the
  pre-existing `backfill-iterate-config.md` precedent (a manual one-liner,
  no scanner at all) and every other adopt CLI in this plugin
  (`record_inherited_baseline.py`, `seed_adopt_compliance.py`).
- **Deriving the backfill through `convert_configs_to_events.py`** — the
  spec's other named option; rejected as a wrong-shape fit (see Decision):
  that script builds an unrelated event-log artifact and has no
  `phase_tasks[]` concept.
- **Reading `phase_history[phase].outcome` explicitly** to choose
  done/skipped, instead of relying on the shared name-keyed rule — external
  review raised this; rejected as unnecessary complexity given the
  Rationale above (both are the same rule by construction), but reduced to
  a residual risk (see External-Code-Review-Findings) that the shared rule
  could someday diverge; addressed by pinning the equivalence in a test
  rather than by adding an indirection with no current behavioral payoff.

## External-Plan-Review-Findings

GLM and OpenAI reviewed the sub-iterate spec text (`--mode iterate`,
before any implementation existed) and both returned `revise`.

| Finding (severity) | Disposition |
|---|---|
| GLM/OpenAI: no mechanism chosen between "re-run the seed" and "route through `convert_configs_to_events.py`" (HIGH) | accepted-and-fixed — chose re-run-the-seed; `convert_configs_to_events.py` rejected as the wrong artifact entirely, documented above |
| GLM: a naive re-seed may reset/duplicate `completed_steps` or overwrite user edits; must preserve prior completion state (MEDIUM) | accepted-and-fixed — the pure function returns a NEW dict and only ever ADDS to `phase_tasks[]`; `completed_steps`/every other field is untouched, pinned by `test_backfills_the_real_leadwright_config`'s byte-for-byte field comparison |
| GLM: "leadwright is not the only one" has no discovery step (MEDIUM) | rejected-with-reason — see Rejected Alternatives; verified against the one repo reachable from this monorepo, dry-run against the live checkout, explicitly documented that no other is known |
| GLM/OpenAI: idempotency asserted but not designed for or tested (MEDIUM/HIGH) | accepted-and-fixed — idempotent by construction (phases already represented are skipped); tested at the pure-function level, the CLI file level (byte-identical + mtime unchanged), and structurally (monkeypatched `write_text` proves no call on a no-op run) |
| GLM: the read-time tolerance "belt" — who owns it? (LOW) | rejected-with-reason — out of this sub-iterate's scope by the spec's own framing ("acceptable as a defensive belt, not the fix"); this sub-iterate is the source-side fix, not a parallel read-time patch |
| OpenAI: no mapping defined between legacy `completed_steps` and `phase_tasks[]` shape (HIGH) | accepted-and-fixed — identical shape to s2's own writer, via the shared `build_adopted_phase_task`; inherits that function's own schema-shape test coverage |
| OpenAI: "reads correctly" not operationalized; verify through the migrated reader path with legacy/migrated/mixed-shape coverage (MEDIUM) | accepted-and-fixed — boundary probes against the real `mermaid.py`, `handoff_pipeline.py`, `phase_quality._engagement.py`; a mixed-shape test (`test_only_the_gap_is_filled_when_phase_tasks_already_partially_present`) pins a real entry surviving alongside a backfilled one |
| OpenAI: bulk migration could expose/alter unrelated repositories if target discovery is too broad (LOW) | rejected-with-reason — no bulk discovery exists in the shipped tool; single explicit `--project-root` only |

## External-Code-Review-Findings

| Finding (severity) | Disposition |
|---|---|
| GLM/OpenAI: no discovery/enumeration for other pre-s2 configs; deployment leaves them unchanged unless an operator already knows the path (MEDIUM/HIGH) | rejected-with-reason — same as the plan-review row; additionally ran `--dry-run` against the real live leadwright checkout (not only the fixture) as the concrete instance of "run it for the known live config" |
| GLM: AC3 evidence is fixture-based only; no record of running against the live leadwright repo (MEDIUM) | accepted-and-fixed — ran `--dry-run` against `C:\01_Development\leadwright` directly; output matched the fixture-predicted `added_phases` exactly; file left unmodified (writing a sibling repo's live config is an operator decision, not this sub-iterate's to make unattended) |
| GLM: backfill derives status from phase name only, ignoring `phase_history` outcome; could misrepresent a phase if the two ever disagree (MEDIUM) | accepted-and-fixed — added `test_the_test_phase_backfills_as_skipped_matching_phase_history` pinning the leadwright fixture's `test` phase backfills as `skipped`; documented in Rationale why the two cannot disagree for any config this codebase produced |
| GLM: a `phase_tasks` value that is present but not a list was silently discarded and overwritten with a fresh array (LOW/bug) | accepted-and-fixed — now left entirely untouched (no-op) rather than replaced; `test_a_malformed_existing_phase_tasks_value_is_left_untouched` |
| GLM: idempotency test relied on `st_mtime_ns`, which can pass spuriously on coarse-mtime filesystems (LOW) | accepted-and-fixed — added `test_a_second_run_never_calls_write_text_at_all`, a monkeypatch-based structural proof, alongside (not instead of) the existing mtime/byte checks |
| GLM: subprocess script built via `%`-interpolation into `-c` source is fragile if a path contained a quote (LOW) | rejected-with-reason — mirrors the pre-existing, already-reviewed `_adopt_write_all` pattern in the same integration-test file (from s2); test-only, `tmp_path`-controlled inputs, not exploitable; kept for consistency with established precedent rather than diverging in a follow-up sub-iterate |
| OpenAI: duplicate values in `completed_steps` produce duplicate `phase_tasks[]` entries for the same phase on the first backfill (MEDIUM/bug) | accepted-and-fixed — `seen` is now updated as entries are accepted, not only seeded from what already existed; `test_duplicate_completed_steps_produce_only_one_entry_per_phase` |
| OpenAI: `"adoption": null` passes the presence guard, then `.get("adopted_at")` crashes with `AttributeError` (MEDIUM/bug) | accepted-and-fixed — both the pure function and the CLI now require `adoption` to be a JSON object, not merely present; `test_a_malformed_adoption_value_is_treated_as_not_adopted` (pure fn) and `test_a_config_with_adoption_null_does_not_crash` (CLI) |

## Self-Review

1. Spec Compliance: pass — AC1 (reads correctly, real leadwright fixture
   through real readers), AC2 (idempotent, pure-fn + file-level +
   structural proof), AC3 (real leadwright config, plus a real dry-run
   against the live checkout; no other reachable repo, stated above).
2. Error Handling: pass — fails closed on missing/corrupt/non-object
   config; a malformed `adoption` or `phase_tasks` value is a no-op, never
   a crash or silent data loss (both were real findings, both fixed).
3. Security Basics: pass — single operator-supplied `--project-root`, same
   pattern as every sibling adopt CLI; no secrets touched.
4. Test Quality: pass — 12 pure-function tests, 12 CLI tests (including
   three empirical boundary probes: BOM, CRLF, non-ASCII), 4 cross-plugin
   integration boundary probes.
5. Performance Basics: pass — one JSON read/write per invocation,
   O(completed_steps) work.
6. Naming & Structure: pass — mirrors s2's own lib/tool split and the
   `record_inherited_baseline.py` CLI precedent.
7. Affected Boundaries (ADR-024): pass — producer (this backfill) and
   three consumers (`mermaid._get_phase_status`,
   `handoff_pipeline.render_pipeline_phases`,
   `phase_quality._engagement.has_phase_tasks`) identified; real
   round-trip probes run against all three, including through the real
   leadwright fixture.

## Confidence Calibration

Fired: `touches_io_boundary` risk flag set (Step 3.4 diff-driven re-check,
`diff_loc=759`). Boundary: `shipwright_run_config.json`, a human-editable
JSON file (the "adoption": null finding above is direct evidence operators
or tools DO hand-touch it). Probes run, per `boundary-probes.md`'s
human-edited-format list (the POSIX-`export`/inline-`#`-comment/quoted-`#`
categories don't apply — this is JSON, not `KEY=VALUE` `.env` syntax):

1. **UTF-8 BOM** (Notepad-style save) — FINDING: `json.loads` raised
   `JSONDecodeError` on a BOM-prefixed file instead of parsing it. Fixed:
   read with `encoding="utf-8-sig"` (strips a BOM when present, identical
   behavior to `"utf-8"` when absent). Re-probed clean.
2. **CRLF line endings** — clean on first probe (JSON's own
   structural parsing does not line-split; unlike hand-rolled
   `KEY=VALUE` `.env` parsing, there is nothing for `\r` to corrupt).
3. **Non-ASCII values** (umlauts, em-dash) — clean on first probe;
   round-tripped byte-for-byte through `json.dumps`/`json.loads`.

Two consecutive clean probes (CRLF, non-ASCII) after the one fix (BOM) —
asymptote reached, boundary calibrated. Edge cases not probed: deeply
nested/pathological JSON structures (not applicable — this config's shape
is small and flat), filesystem permission errors on write (not
format-boundary-specific, out of this gate's scope).

## Delegated-Review-Findings (3f-bis)

Campaign orchestrator delegated review cascade (ADR-029), against the
merge-base diff (`origin/main`..HEAD, 759 loc, risk flags
`touches_io_boundary` + `touches_migrations`).

**Stage 1 (spec-reviewer): PASS.** Verified AC1/AC2/AC3 against the diff
directly — including reading the real `C:\01_Development\leadwright\shipwright_run_config.json`
on disk and confirming it is byte-identical to the committed fixture and
still lacks `phase_tasks[]`, corroborating the ADR's dry-run claim rather
than merely trusting it. No spec citations; no scope creep found.

**Stage 2 (code-reviewer): PASS**, 2 non-blocking low findings — both
already true of the pre-existing `config_writer.py` write pattern this
tool mirrored (non-atomic write; ADR-prose-only live-repo verification
evidence), not new divergences. See Delegated-Doubt-Review below: the
write-safety finding was independently re-raised at HIGH severity by
Stage 3 with a concrete clobber scenario this stage's framing (generic
crash-safety) had not identified, and is fixed there.

## Delegated-Doubt-Review (3f-bis, Stage 3)

Stage 3 (doubt-reviewer), adversarial, biased to disprove. Verdict:
"blocking doubt" (2 doubts) — both fixed before merge, per the
advisory-must-address gate.

| Doubt (severity) | Resolution |
|---|---|
| The tool's unlocked, non-atomic, whole-document read-modify-write reintroduces a specific, previously-audited clobber hazard: `shipwright_run_config.json` already has dedicated lock+atomic-write infrastructure (`plugins/shipwright-run/scripts/lib/run_config_store.py`'s `run_config_lock`/`atomic_write_json`, honored by `phase_task_lifecycle.py`) that this tool participated in none of — and its own stated trigger scenario ("picked up by `/shipwright-run` for a new feature") is exactly when a live, lock-holding orchestrator session could be concurrently writing the same file, so a backfill run in that window would silently revert every field the orchestrator had just advanced, not merely fail to add `phase_tasks[]` (HIGH) | accepted-and-fixed — the CLI now acquires the SAME advisory lock (same lock-file PATH as `run_config_store.py`, not the same imported module: importing it directly would collide with this plugin's own `lib` namespace under ADR-045, so the fix imports `atomic_write`/`file_lock` straight from `shared/scripts/lib`, the identical pattern `run_config_store.py` itself uses) around the ENTIRE read-modify-write, not just the write — reading first and locking only the replace would still leave the clobber window open. Writes go through `durable_atomic_write` (tmp+fsync+os.replace) instead of `Path.write_text`. A lock that cannot be acquired within 30s (module constant `LOCK_TIMEOUT_SECONDS`, monkeypatchable) fails loudly (`SystemExit`) rather than racing past it. Proven with a real concurrency test, `test_a_held_lock_blocks_the_backfill_instead_of_racing_it`: an external holder acquires the identical lock-file path via `file_lock` directly, the CLI's own run fails with the expected `SystemExit` while it is held, and succeeds once released — proving both that the CLI contends for the real lock path (not a no-op) and that contention fails safe. |
| A non-string `completed_steps` entry (a nested dict/list from a hand-edited or corrupted config — the ADR's own "old configs never validated this list" caveat) is UNHASHABLE, so the `step in seen` / `seen.add(step)` dedup check raises `TypeError` before ever reaching `build_adopted_phase_task`'s enum validation, crashing the whole CLI instead of the "skipped, not fatal" behaviour the docstring promises for garbage entries — contradicting Confidence Calibration's dismissal of "nested/pathological structures" as not applicable to this exact boundary (MEDIUM) | accepted-and-fixed — a non-`str` entry is now caught and routed to `skipped_phases` BEFORE the hash-membership check, in `backfill_missing_phase_tasks` itself (`adopted_phase_tasks.py`). Pinned by `test_an_unhashable_completed_step_entry_is_skipped_not_a_crash` (a dict entry alongside two valid phases: the valid ones still backfill, the garbage one is reported, nothing crashes). |

## PR-Review-Gate Findings (PR #701, `openai/gpt-5.6-luna`)

The doubt-review's `completed_steps`-side fix above did not cover the SAME
hazard on the existing-`phase_tasks[]`-side: the automated PR-review gate
(sensitive-path Tier-3, mandatory) caught it before merge.

| Finding (severity) | Disposition |
|---|---|
| `seen = {t.get("phase") for t in existing_list if isinstance(t, dict)}` raises `TypeError` when an ALREADY-PRESENT `phase_tasks[]` entry has an unhashable `phase` value (a list or dict from a hand-edited/corrupted config) — the mirror image of the doubt-review's `completed_steps` finding, on the other side of the same set (BLOCKING) | accepted-and-fixed — the comprehension now only admits `isinstance(t.get("phase"), str)` entries into `seen`; a malformed existing entry is simply not represented there (and is left untouched in `phase_tasks[]`, same as every other malformed-data case this function treats as "stop, don't guess"). Pinned by `test_an_existing_entry_with_an_unhashable_phase_value_is_not_a_crash`. |
| (comment) The docstring says the pure function returns a NEW dict, but a no-op path returns the original `run_config` object itself (LOW) | accepted-and-fixed — docstring clarified: "never mutated" is about in-place writes, not identity on every return path; a no-op has nothing to protect a copy from. |
| (comment) `adoption.adopted_at` is used as `now` without validating it is a string; a malformed human-edited value would propagate into every generated task record's `createdAt`/`completedAt` (schema `format: date-time`) (LOW) | accepted-and-fixed — a non-string `adopted_at` now falls back to `_utc_now_iso()` instead of propagating. Pinned by `test_a_non_string_adopted_at_falls_back_to_now_instead_of_propagating`. |

## Delegated-Re-Verification (3f-bis, code re-verify after PR #701 gate)

Orchestrator re-ran code-reviewer against the updated diff (a fresh set of
eyes, not just confirming the three fixes above). One finding:

| Finding (severity) | Disposition |
|---|---|
| `test_a_second_run_never_calls_write_text_at_all` monkeypatched `pathlib.Path.write_text`, but the doubt-review's own earlier fix (lock + `durable_atomic_write`) already stopped the code from ever calling `Path.write_text` on ANY run — the monkeypatch never triggers either way, so the "structural no-op-write proof" this test's docstring claims was vacuous (MEDIUM) | accepted-and-fixed — repointed the monkeypatch at `backfill_cli.durable_atomic_write` (the primitive actually used), renamed to `test_a_second_run_never_calls_the_write_primitive_at_all`. |
