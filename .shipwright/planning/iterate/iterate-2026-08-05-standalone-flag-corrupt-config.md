# Iterate Spec: standalone-flag-corrupt-config

- **Run ID:** iterate-2026-08-05-standalone-flag-corrupt-config
- **Type:** bug
- **Complexity:** medium
- **Status:** draft
- **Card:** trg-8b5f8f40 (P2.16 `[GUIDED]`), split from anchor trg-040223fe
- **Predecessor:** ADR-114 § Rejected — *"Fixing the corrupt-config standalone
  demotion … Real, but it predates ADR-113, its blast radius is every v1 caller,
  and fixing it means deciding what a corrupt config should do to a run. Its own
  iterate."* This is that iterate, and the decision is recorded below.

## Goal

`orchestrator_pkg.config_io.load_run_config` answers `{}` for **two different
questions** — *"there is no config"* and *"there is a config but I cannot use
it"*. The v1 step-advance path reads that single answer as the first, so an
unusable config silently demotes a real run to `standalone` and then overwrites
it.

Make the two answers distinguishable, and make everything that would **advance
or change a run** refuse on the second while everything that only **reads to
display** keeps degrading gracefully.

## Measured behaviour (pre-fix, reproduced 2026-08-05)

Against a truncated config whose content says `standalone: false`,
`mode: single_session`, `completed_steps: ["project","design"]`:

| Probe | Healthy config | Unusable config |
|---|---|---|
| `_read_standalone_flag` | `False` | **`True`** |
| `get_next_step` | `plan` | **`project`, "no config found, start from beginning"** |
| `update_step(force=True, force_reason=None)` (library) | `ValueError` | **accepted** |
| config after one `update_step` | intact | **`runId`/`mode`/`phase_tasks`/`validation_overrides` gone** |

Three guarantees switch off together, exactly as the card states: the phase gate
is skipped (`if not is_standalone:` in `step_planning.update_step`), `--force`
stops demanding a recorded reason (`normalise_override_reason` is never
reached), and no `validation_overrides[]` entry is written (`if force and not
is_standalone:`). FR-01.01's evidence rule therefore stops applying precisely in
the degraded state where evidence matters most. The follow-up
`_load_or_bootstrap` then atomically replaces the file, so the bytes that could
have been hand-repaired are gone.

**Second door — non-object JSON (found during this run's Repo Scout).**
`load_run_config` never checks that the parsed JSON is an *object*:

```
'null'    -> standalone = True   (SILENT — parses fine, no warning printed)
'[]'      -> standalone = True   (SILENT)
''        -> standalone = True   (warns)
'123'     -> AttributeError: 'int' object has no attribute 'get'
'"hello"' -> AttributeError
'[1,2]'   -> AttributeError
```

The `null` / `[]` shapes are strictly worse than the reported case because
`json.loads` succeeds, so the existing "Corrupt orchestrator config" warning
never fires and the demotion is invisible. The truthy non-object shapes crash
with a bare `AttributeError` and no actionable message. `orchestrator_pkg.events
._run_id_of` already guards this exact case with an explicit `isinstance(cfg,
dict)` check and says so in its docstring; `config_io` does not. Folded into
this fix: same function, same question, same tests.

**Third door — a PRESENT but empty object (external plan review, OpenAI, high).**
The review objected that a `(config, present)` distinction is needed because
truthiness cannot separate *absent* from *present-and-empty*. Verified:

```
file containing exactly "{}"  ->  _read_standalone_flag  = True   (demoted)
                              ->  _load_or_bootstrap bootstraps OVER the present file
```

`_load_or_bootstrap`'s `if config else bootstrap` and `_read_standalone_flag`'s
`if not config: return True` are **truthiness** tests, so a real file containing
`{}` is indistinguishable from no file at all. A fix that only distinguishes
"parsed vs did not parse" would leave this door open and would not satisfy AC4.
Presence must come from the read itself.

**Fourth door — `standalone` that is not a boolean (same review, finding 6).**
Verified, and worse than the review supposed: `_read_standalone_flag` is
annotated `-> bool` but returns `config.get("standalone", False)` **raw**:

```
standalone: "false"  ->  returns  'false'   (a truthy string -> treated as standalone)
standalone: "no"     ->  returns  'no'      (truthy -> standalone)
standalone: 0        ->  returns  0
standalone: null     ->  returns  None
```

So a config explicitly recording `"false"` switches the phase gate **off**. This
is fixed in the fail-safe direction only (`is True`), *not* by adding schema
validation — see Out of Scope.

**Non-UTF-8 bytes.** Confirmed to raise `UnicodeDecodeError`, which is a
`ValueError` and not a `JSONDecodeError`, so it escapes `config_io`'s handler and
fails loudly today. `durable_read_text`'s docstring documents this deliberately
and `test_read_gives_up_loudly_rather_than_inventing_an_empty_config` pins it.
**The tolerant path must keep propagating it** — swallowing it into `{}` would
regress that pin. Only the strict path re-wraps it, and still loudly.

## Decision (the one ADR-114 deferred)

**An unusable run config stops anything that would advance or change a run, and
is never overwritten. Reads that only display something stay tolerant.**

Three supporting findings made this cheap rather than sweeping:

1. **The blast radius is not "every v1 caller".** All nine production call sites
   were checked. The v2 / driven paths already fail closed —
   `phase_task_lifecycle._read_config` **raises** on the identical file and
   leaves it on disk; `single_session_apply` returns `mode_unsupported`;
   `single_session_loop` / `single_session_recovery` return `no_config`. Only the
   v1 step-advance path fails open, and it is four functions in two files plus
   one CLI guard. This change converges the two halves of the plugin on the
   behaviour the newer half already has.
2. **Corruption is never transient.** `atomic_write.durable_atomic_write` uses
   `tmp + fsync + os.replace`, which rules out torn reads by construction, so a
   parse failure always means genuinely bad bytes (crash-truncated, empty after
   power loss, hand-edited, merge markers, an external non-atomic writer). A hard
   stop therefore cannot spuriously fire on a healthy run — the usual objection
   to fail-closed does not apply here.
3. **The repo already decided this once.** `test_anti_ratchet_check.py` pins
   *"a present-but-corrupt baseline must NOT silently disable the gate"*
   (fail-closed exit 1). Fail-closed on unreadable governance state is house
   style.

**Why `create_config` / `write-config` is deliberately NOT made to refuse.** It
does not advance an existing run — it creates a new one, and it is the documented
escape hatch the error message points at (*"delete it and re-run
/shipwright-run"*). Guarding it would strand exactly the people who need to
recover. This follows from the policy, not merely from the scope choice.

## Acceptance Criteria

- [ ] **AC1** — A new strict reader `read_run_config(project_root, *,
  migrate=True) -> tuple[dict, bool]` returns `(config, present)` and is
  **total at the read boundary**: for the read-decode-parse-shape sequence it
  either returns a usable dict or raises `RunConfigUnreadable`. Presence is
  derived from the read itself (`FileNotFoundError` ⇒ absent), never from a
  separate `path.exists()` probe, so a concurrent delete cannot straddle a
  check/read pair. *Migration is outside that boundary — see AC11.*
- [ ] **AC2** — `RunConfigUnreadable` carries `path`, `detail` and a `category`
  of `parse` (bad JSON) · `shape` (valid JSON, not an object) · `decode` (not
  UTF-8) · `io` (`OSError`). Each category raises with the advice that actually
  applies to it — "repair or delete and re-run" is wrong for a permissions
  error, so `io` says to check permissions instead. **`RecursionError` from
  deeply nested JSON classifies as `parse`**, not as an unclassified crash:
  `json.loads` raises it instead of `JSONDecodeError`, which would otherwise
  bypass the taxonomy *and* defeat the recovery path. `MemoryError` and other
  process-level failures are deliberately **not** caught.
- [ ] **AC3** — `load_run_config`'s **signature is unchanged** (no new keyword),
  and the only behaviour change for its tolerant callers is that a non-object
  payload now warns and returns `{}` instead of returning the non-object for the
  caller to crash on. `UnicodeDecodeError` and `OSError` keep propagating **as
  their own concrete types**, not wrapped — swallowing *or* re-typing them would
  regress `test_read_gives_up_loudly_rather_than_inventing_an_empty_config`.
  Since the shared helper (AC13) raises `RunConfigUnreadable` for all four
  categories, the tolerant reader re-raises `exc.__cause__` for `decode` / `io`;
  tests assert the caller sees `UnicodeDecodeError`, `PermissionError` and
  `IsADirectoryError` themselves.
- [ ] **AC4** — `_read_standalone_flag` returns a real `bool` and answers
  `True` **only** for an absent config or an explicit `standalone: true`
  (`is True`). Every other value — `"false"`, `"no"`, `0`, `null`, a present
  `{}` — answers `False`, so the phase gate **runs**. On an unusable config it
  raises `RunConfigUnreadable` instead of answering at all.
- [ ] **AC5** — `_load_or_bootstrap` bootstraps **only** when the config is
  absent, decided by `present`, not by truthiness — so a present `{}` is
  returned as-is rather than replaced by a synthesised standalone config. On an
  **unusable** config it raises and the file on disk is byte-identical
  afterwards. **This is the anti-data-loss guarantee**, and it is stated
  precisely: *a config observed unreadable by the in-lock read is never
  overwritten by that operation.* `_load_or_bootstrap` runs **inside**
  `run_config_lock`, so the read and the subsequent `save_run_config` are
  serialised against our own writers. It is deliberately **not** a claim about a
  file replaced by an outside process between that read and the write — no new
  locking is introduced for a race the existing design already accepts (external
  review round 3).
  *Scope note (external review, finding 1):* a present `{}` is a **usable**
  config, so `update_step` legitimately proceeds to mutate it. Byte-identity is
  asserted for the *unusable* shapes only; for `{}` what is asserted is that no
  bootstrap was injected. Treating `{}` as unusable would be the semantic-
  validation decision this iterate explicitly declines (see Out of Scope).
- [ ] **AC6** — `update_step` refuses on an unusable config for **every** status
  (`complete`, `in_progress`, `failed`): nothing is written, no compliance
  subprocess is spawned, and the phase gate / force-reason / override-record
  guarantees are never reached in a demoted state. It refuses on its **first
  executable statement**, before any mutation.
  *Residual window, stated like AC5's (Stage-3):* `is_standalone` is decided by
  that first unlocked read and consumed again after `run_phase_gate` and the
  compliance subprocess (~30 s). A config that is ABSENT at the first read and
  created by a concurrent `write-config` before the second is still completed
  under the standalone rules. Pre-existing, unchanged here, and **not** fixed by
  this iterate — closing it means restructuring `update_step`'s lock scope, which
  is a different change from teaching the reader to tell absent from unusable.
- [ ] **AC7** — `get_next_step` reports `blocked: true` +
  `reason: "config_unreadable"` + the path instead of `"no config found, start
  from beginning"`, and is distinguishable from the all-steps-complete case
  (which also carries `next_step: None`). It carries the CLI payload's own keys
  verbatim — `category` / `detail` / `path` / `message` — from the **same
  bounded, content-free formatter**, so a library consumer that serialises the
  result itself is not the leak AC10 closes. (There is deliberately no separate
  `error` alias: one formatter, one set of key names.)
- [ ] **AC8** — the driven-run inert guard (`cli_update_step.py`, extracted from
  `cli.py` for the file budget) reads strictly, so an unusable config can no
  longer switch it off. The CLI emits the actionable payload **exactly once, on
  exactly one stream**, and exits `2` rather than mutating:
  - the **mutating** arms propagate to the outer `except RunConfigUnreadable`,
    which writes the payload to **stderr** (they have no result to report);
  - **`get-next-step`** catches inside `get_next_step` — so it can never reach
    that handler — and prints its blocked result to **stdout** like every other
    arm, with the exit code carrying the failure. It is deliberately *not*
    echoed to stderr as well: that emitted one diagnostic twice to anything
    aggregating both streams (external code review).
- [ ] **AC9** — Every entry point that can advance or change a run reaches one of
  the two strict chokepoints; the inventory below is pinned by a test, and the
  deliberately exempt recovery writer (`create_config` / `write-config`) is named
  in it rather than merely omitted.
- [ ] **AC10** — The error detail is built from the exception **type and message
  only**, bounded in length, and never echoes file content. The CLI payload is
  emitted as structured JSON with bounded `detail` and `path` fields, so a
  project root containing a newline or quote cannot corrupt machine-consumed
  output. `RunConfigUnreadable` initialises its `RuntimeError` base with the
  formatted message (so a bare `str(exc)` anywhere is still useful) and is raised
  `from` the original exception, preserving the traceback.
- [ ] **AC11** — The shape check runs on the parsed value **before** migration,
  so migration only ever sees a dict. Migration's own failures (a `KeyError` in
  `_migrate_legacy_pipeline_if_needed`, or an `OSError` from the write it
  performs) **propagate unchanged** and are NOT re-wrapped as
  `RunConfigUnreadable` — those are defects in our code or a genuine disk fault,
  and disguising them as "your config is corrupt" would send the operator to
  delete a perfectly good file. Pinned by a test.
- [ ] **AC12** — The recovery path stays open **by category**. `write-config` /
  `create_config` replaces a config whose *content* is bad — `parse`, `shape`
  **and `decode`** — exiting `0` without the unreadable payload, warning only
  that prior `completed_steps` could not be merged. A genuine **`io`** failure
  (permissions, path-is-a-directory) still propagates loudly, because it will
  defeat the write anyway and "delete the file and re-run" is the wrong advice
  for it. The strict reads are scoped per call site to commands that advance or
  change an *existing* run, never a pre-dispatch guard that would have to
  remember to exempt this one.
  *Note (external review round 3, high):* this is a deliberate five-line
  widening of the agreed scope. Without it the chosen recovery story is false —
  the tolerant reader propagates `UnicodeDecodeError` (AC3), so `write-config`
  on a non-UTF-8 config would crash instead of recovering, and the operator
  would be told to re-run a command that cannot work.
- [ ] **AC13** — `load_run_config` and `read_run_config` share **one** private
  read-decode-parse-shape helper, so the tolerant and strict readers can never
  drift on what counts as absent, malformed or usable. The two differ only in
  how they *dispose* of a failure, not in how they *detect* one. Migration is
  invoked outside that shared helper (AC11).

## Caller inventory (AC9)

| Entry point | Reaches strict via | Behaviour on an unusable config |
|---|---|---|
| `update_step` — **every** status | `_read_standalone_flag`, its first statement | raises, nothing written |
| `_load_or_bootstrap` (the in-lock read) | `read_run_config` | raises; pinned *directly*, since `update_step` never reaches it |
| CLI `update-step` | `cli_update_step.py` driven-run guard → `read_run_config` | stderr payload, exit 2 |
| CLI `get-next-step` | `get_next_step` → `read_run_config` | blocked payload, exit 2 |
| `get_next_step` (library) | `read_run_config` | blocked payload, no raise |
| **`router.dispatch_lifecycle`** — the v2 ADVANCING commands (claim / complete / mark-failed / freeze-splits / plan-next-phase) | `read_run_config` | stderr payload, exit 2 |
| **`create_config` / `write-config`** | *best-effort, by decision (AC12)* | **replaces bad content (`parse`/`shape`/`decode`) — the recovery path; `io` still propagates** |
| `single-session-apply` / `-next` / recovery | already fail closed on their own | unchanged (`mode_rejection` / `no_config`) |

Two corrections the reviews forced, recorded rather than quietly fixed:

- Row 2 previously attributed the `in_progress` / `failed` statuses to
  `_load_or_bootstrap`. False — `_read_standalone_flag` runs first for *every*
  status, so `_load_or_bootstrap` is never the refusing chokepoint *via*
  `update_step`. It is now pinned directly instead (Stage-2).
- `router` was absent, and the old last row claimed the v2 path "fails closed
  upstream". It failed closed **downstream**, and only by accident:
  `phase_task_lifecycle._read_config` raised a bare `JSONDecodeError` (or
  `AttributeError` for a non-object) that `cli.main` cannot recognise, so the
  operator got a traceback and exit 1 instead of the payload. That guard was the
  same defect as `cli_update_step`'s, in the file family this change already
  touched — so it is fixed here rather than deferred (Stage-3).

## Spec Impact

- **Classification:** none
- **NONE justification:** behaviour-preserving defect fix to an internal
  orchestrator I/O helper. FR-01.01's *rule* is unchanged — this restores its
  reach into a degraded state where it silently stopped applying. No product-
  facing FR describes run-config parse-failure handling, and no phase, artifact
  or command surface is added or removed.

## Out of Scope

- **The same two doors in the OTHER readers of this file.**
  `phase_task_lifecycle._read_config` and `append_phase_history` still lack an
  `isinstance(dict)` check, and `gate_policy.read_run_config_mode` guards only
  `(JSONDecodeError, OSError)` so `shape` / `decode` crash it instead of reading
  INERT_MODE as its docstring promises (**trg-406d7c3c**). All are read-only or
  already-fail-closed paths, so no gate is weakened — the cost is a traceback
  instead of a readable answer. "The four doors are closed" is therefore a claim
  about `config_io` and the v1 advance path, **not** repo-wide (Stage-3).
- **Semantic validation of a well-formed config object** (missing required
  fields, wrong types beyond `standalone`, a `mode` that is not a known literal).
  One narrow exception was made after Stage-3 showed it *crashes* rather than
  merely misvalidates: `pipeline: null` / `completed_steps: null` pass the shape
  gate and then raised `TypeError` out of `get_next_step`, a reporter that
  promises not to crash. Both now use the null-tolerant form `update_step`
  already used. Wrong *types* beyond that stay deferred.
  Raised by the external plan review (finding 6). **Consciously deferred, and the
  decision is narrowed accordingly: "unusable" here means SYNTACTIC — the file
  cannot be parsed, decoded, read, or is not a JSON object.** A schema-validating
  strict reader is a materially different change (there is a
  `shared/schemas/run_config.v2.schema.json` to wire in, plus a migration story
  for every historical config that would newly fail it) and would turn a
  contained bug fix into a compatibility event. The one semantic hole closed here
  is `standalone` (AC4), because it is the exact field this defect turns on and
  the fix is a fail-safe one-liner rather than a validation pass.
- **Guarding `create_config` / `write-config`** — it stays able to overwrite,
  because it is the recovery path (rationale above). It is *touched* only to make
  that recovery actually work for every bad-content category (AC12), and the
  merge of `prior_completed` from an unusable config degrades to "not merged,
  warned" rather than crashing.
- **The wording of `single_session_loop` / `single_session_recovery`'s
  `no_config`** — misleading (a config exists, it is just unreadable) but *safe*:
  those paths already fail closed. Scope decision; no behaviour at risk.
- **Shared read-only consumers outside the plugin** —
  `generate_handoff_on_stop.py`, `suggest_iterate.py`, `update_build_dashboard.py`,
  compliance `mermaid.py`, `state.detect_current_phase`. Display-only; tolerant is
  the correct behaviour for them under the chosen policy.
- **A `repair-config` command** that salvages fields from a damaged file —
  considered and deferred as its own piece of work (new tool, new tests, new
  failure modes).
- **trg-be24ff6f / trg-8d52a965** (retiring the write-once `current_step` /
  `completed_steps` fields) — the anchor's other split, already owned.

## Design Notes

n/a — no UI surface. Pure Python error-handling and control-flow in the
orchestrator's config I/O layer.

## Affected Boundaries

**`shipwright_run_config.json` — the read side.** This change is entirely about
what the reader does with every byte-shape the file can hold, so the boundary is
the subject of the change rather than incidental to it. `touches_io_boundary` is
**elected** for that reason; the diff-driven detector does not fire on its own
(`IO_BOUNDARY_FILE_PATTERNS` matches `*_config.json` *files*, and this diff
changes `.py` readers of one). Boundary Probe is therefore run as a Safety-
enforced phase: the round-trip is `every JSON shape a file can contain -> the
reader's answer`, enumerated exhaustively rather than sampled.

Not affected: the write side (`save_run_config` / `atomic_write_json`)
is untouched, and the v2 `phase_task_lifecycle` reader already has the target
behaviour.

## Confidence Calibration

- **Boundaries touched:** the `shipwright_run_config.json` **read** side
  (`touches_io_boundary`, elected — see Affected Boundaries). The write side and
  the v2 `phase_task_lifecycle` reader are untouched.

- **Empirical probes run** (each against the real code, not reasoned about):
  - **Pre-fix reproduction.** Truncated config recording `standalone: false`,
    `mode: single_session`, two completed phases →
    `_read_standalone_flag: True`; `get_next_step: "project", "no config found,
    start from beginning"`; `update_step(force=True, force_reason=None)`
    **accepted**; file atomically replaced, losing `runId` / `mode` /
    `phase_tasks` / `validation_overrides`. All four card claims confirmed.
  - **Door 2 (non-object).** `null` / `[]` → `standalone=True` with **no warning
    printed at all** (they parse, so the JSONDecodeError arm never fires);
    `123` / `"hello"` / `[1,2]` → bare `AttributeError`.
  - **Door 3 (present-empty).** A file holding `{}` → `_read_standalone_flag:
    True` and `_load_or_bootstrap` bootstrapped **over the present file**.
    Truthiness cannot distinguish it from absence. (External review, high.)
  - **Door 4 (non-boolean).** `_read_standalone_flag` returned the RAW value
    despite `-> bool`: `"false"` → `'false'` (truthy → standalone), `"no"` →
    `'no'`, `0` → `0`, `null` → `None`. Worse than reported.
  - **Non-UTF-8.** Confirmed `UnicodeDecodeError` escapes the `JSONDecodeError`
    handler and fails loudly, as `durable_read_text`'s docstring documents —
    which is why the tolerant path must keep *propagating* it, not swallow it.
  - **Transience ruled out.** `atomic_write` uses `tmp + fsync + os.replace`, so
    torn reads are impossible by construction; a parse failure always means
    genuinely bad bytes. This is what makes fail-closed safe rather than a new
    way to wedge a healthy run.
  - **Blast radius measured**, not estimated: all nine production call sites
    read. The v2/driven paths already fail closed (`phase_task_lifecycle
    ._read_config` RAISES on the identical file and leaves it on disk); only the
    v1 step-advance path fails open.
  - **Post-fix, operator-facing.** Rendered the real message for a `parse`
    failure and an `io` failure — different advice per category, file confirmed
    byte-identical afterwards.
  - **cp1252 probe.** The first message drafted contained an em-dash, which
    would raise `UnicodeEncodeError` on a Windows console *while rendering an
    error*. Caught by rendering it, fixed to ASCII, pinned by a test.
  - **Mutation test of the AC9 pin.** Reverted `cli_update_step.py`'s guard to
    the tolerant reader: **134 tests stayed green, only the new pin went red.**
    That is the Stage-1 reviewer's finding reproduced and then closed — the pin
    now bites where behavioural tests structurally cannot (the downstream
    chokepoint masks the guard's own failure).

- **Test Completeness Ledger:** 135 new tests (57 reader · 54 fail-closed · 24
  CLI+recovery). 14 behaviours, 13 `tested`, 1 `untestable`, **0
  testable-but-untested.**

| # | Behaviour | Status | Evidence / `reason_code` |
|---|---|---|---|
| 1 | Strict reader returns `(config, present)`, total at the read boundary | tested | `test_absent_is_not_an_error`, `test_raises_on_every_unusable_shape`, `test_accepts_every_usable_shape` |
| 2 | Presence from the read, not a `path.exists()` probe | tested | `test_absence_comes_from_the_read_not_from_a_probe` |
| 3 | Four categories + `RecursionError`→`parse`; advice fits the cause | tested | `test_carries_a_category`, `test_deeply_nested_json_classifies_as_parse`, `test_io_does_not_tell_the_operator_to_delete_the_file` |
| 4 | Tolerant reader unchanged except shape→`{}`; decode/io propagate as concrete types | tested | `test_tolerant_reader_*` (incl. `IsADirectoryError`), `test_load_run_config_signature_is_unchanged` |
| 5 | `standalone` is a real bool and only the literal `true` | tested | `test_standalone_is_only_the_literal_true` (9 cases), `test_present_empty_object_is_not_standalone` |
| 6 | Bootstrap only when ABSENT; present `{}` returned as-is | tested | `test_present_empty_object_is_returned_not_bootstrapped`, `test_bootstrap_fires_only_when_the_file_is_absent` |
| 7 | An unusable config is never overwritten (incl. non-UTF-8) | tested | `test_the_unusable_file_survives_byte_for_byte`, `test_a_non_utf8_config_also_survives_byte_for_byte` |
| 8 | `update_step` refuses on every status, before any work | tested | `test_update_step_refuses_on_every_status`, `test_never_spawns_compliance_on_a_doomed_path` |
| 9 | The reasonless-`--force` hole is closed | tested | `test_a_reasonless_force_can_no_longer_slip_through` |
| 10 | `get_next_step` reports blocked, does not lie, does not crash, does not leak | tested | `test_no_longer_says_start_from_the_beginning`, `test_blocked_is_distinguishable_from_all_steps_complete`, `test_blocked_result_does_not_leak_file_content` |
| 11 | CLI exits 2 on both paths, payload printed once, guard not bypassed | tested | `test_runconfig_corrupt_cli.py` (subprocess: real exit codes) |
| 12 | No mutating module reaches a tolerant reader | tested | `test_no_mutating_module_imports_the_tolerant_reader` — **mutation-verified** |
| 13 | Recovery works for every bad-content category; `io` stays loud; warning announced | tested | `test_create_config_recovers_from_*`, `test_create_config_says_the_prior_steps_were_not_merged` |
| 14 | `docs/hooks-and-pipeline.md` describes the two-reader contract accurately | untestable | `requires-manual-visual-judgment` — prose accuracy; the behaviour it describes is covered by rows 1-13 |

- **Confidence-pattern check:**
  - **Asymptote (depth):** the four doors were found by *enumerating the byte
    shapes a JSON file can hold* rather than by sampling; rows 1-3 of the
    ledger's probe table are that enumeration, and each new door was found by
    the enumeration rather than by intuition. The last two doors came from the
    external review and Stage-1 review, both reproduced before being accepted —
    which is the signal that depth was still paying out, so the shape matrix is
    exhaustive by construction (absent · unreadable · undecodable · unparseable ·
    non-object · empty-object · usable) rather than by judgement.
  - **Coverage (breadth):** all nine production call sites were read and
    classified, and the inventory is pinned by a test rather than by the table
    alone. The one place breadth was genuinely thin — the CLI guard after its
    extraction — was found by Stage-1 review and closed with a pin proven to
    bite.
  - **Integration composition:** `cross_component` does **not** fire on this
    diff (no merge/churn/event-log resolver, no `hooks.json` or `hooks/*.py`, no
    `verify_phase`/`get_phase_context`, no campaign drain — checked against
    `CROSS_COMPONENT_FILE_PATTERNS`). The composition that *does* matter here —
    CLI process → orchestrator → config layer — is covered end-to-end by the
    subprocess suite and by `integration-tests/test_shipwright_run_e2e.py`,
    which drives `get-next-step` and stayed green.

## Verification (medium+)

- **Suites:** 524 shipwright-run · 470 integration (7 deselected) · 7933 shared
  (23 skipped, 26 deselected) · ruff clean · pre-commit anti-ratchet clean.
- **File budget:** every touched file ≤300 LOC. Two extractions were required
  and are recorded in their module docstrings (`step_config_access.py`,
  `cli_update_step.py`); no new bloat-baseline crossing.
- **Reviews:** external plan review — 4 rounds, every finding folded into an AC
  or explicitly declined (table in the mini-plan). Stage-1 spec-reviewer —
  REJECT then re-verified; three blocking findings fixed.
