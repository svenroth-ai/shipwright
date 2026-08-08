# ADR-127 — Decision-log and decision-drops indexes, ADR-index pattern extended

> **Premise revised by iterate-2026-08-08-track-decision-drops.** This ADR
> was written on "this directory is permanently gitignored" (Context,
> Decision's `decision_drops_index.py` bullet, Consequences). That premise
> no longer holds: the `decision-drops/` directory is now TRACKED (only its
> local `INDEX.md` render stays gitignored), each worktree resolves its own
> copy directly against `project_root` (no more "every parallel iterate
> worktree resolves the SAME shared main-repo directory"), and it now needs
> no `CHURN_ALLOWLIST` entry for a different reason than stated here
> (uniquely-named per-run files, not git's inability to see an ignored
> path). This note supersedes those passages in place; the historical
> record below is left as written, not rewritten.

## Self-Review: scope exceeded the iterate threshold; operator's brief chose to continue

Stage-1 complexity classification returned `large` (confidence 0.6) on scope
keywords ("producer", "byte-equality drift guard", "churn allowlist entry").
Per the Escape Hatch protocol this normally hands off to
`/shipwright-project` + `/shipwright-build`. The operator's `--autonomous`
invocation supplied a fully-scoped, bounded brief (extend one existing,
well-understood pattern to two more artifacts, with explicit instructions on
review cascade and model), which is Option 2 of the Escape Hatch ("Force
iterate") rather than a project handoff: full test suite + full code review
mandatory, recorded here per that option's requirement.

## Context

The ADR spec folder's `INDEX.md` already has a producer since ADR-116/ADR-118:
a pure `render_adr_index` + a writing `rebuild_adr_index`, a byte-equality
drift guard, a `CHURN_ALLOWLIST` entry, and regeneration triggered by a change
to the source rather than by an unrelated event. Two collections had no index
at all: `.shipwright/agent_docs/decision_log.md` (328 entries in one file) and
`.shipwright/agent_docs/decision-drops/` (202 pending JSON files, gitignored).
Measured: reading both in full costs ~276k tokens against ~11k for an index —
a 25x compression that is what turns "read all architectural decisions" from
an instruction nobody can follow into one that is followable.

## Decision

Extended the same pattern to both, reusing existing primitives
(`durable_atomic_write`, `file_lock`) rather than inventing new ones:

- `shared/scripts/lib/decision_log_index.py` — pure `render_decision_log_index`
  (regex-parses `### ADR-NNN[: Title]` headings, fence-aware so a verbatim
  quote inside a fenced code block is never mistaken for a live entry) + a
  locked/atomic `rebuild_decision_log_index`, written to a sibling
  `decision_log_index.md`. Refreshed by BOTH producers that can write
  `decision_log.md`: `write_decision_log.py` (the direct-append path
  plan/build/deploy use) and `aggregate_decisions.py` (the release-time fold,
  every non-dry-run pass, drops or not — mirroring the ADR-index fix).
  Registered in `churn_merge.CHURN_ALLOWLIST` as `DECISION_LOG_INDEX`: the
  index is a pure function of `decision_log.md`'s own already-merged content,
  so a merge conflict on it is always correctly resolved by re-deriving
  rather than picking a side — exactly the ADR-index reasoning.
  `current-status` (`— superseded by ADR-NNN`) is derived from a
  `(supersedes ADR-NNN)` marker in a LATER entry's title, never from the
  `**Status**` field: that field covers only 16 of 328 entries (95% empty),
  so a column read from it would be mostly blank. Only one such marker exists
  in this log today (ADR-307 supersedes ADR-042) — the parser handles
  however many more accrue, without building machinery for a link graph the
  corpus does not yet have.
- `shared/scripts/lib/decision_drops_index.py` — same render/rebuild split
  for the pending decision-drops directory, refreshed by `write_decision_drop.py`
  (a new drop was added) and `aggregate_decisions.py` (drops were folded and
  deleted). Deliberately DIVERGES from the ADR-index pattern on two points,
  both because the directory is gitignored (`.gitignore` /
  `.shipwright/agent_docs/decision-drops/`, documented in `glossary.md`):
  no `CHURN_ALLOWLIST` entry (git can never see a conflict on a path it never
  tracks — an allowlist entry would be exercised by nothing) and no CI
  byte-equality drift guard against a committed copy (there is never one in a
  clean checkout). The real hazard instead is LOCAL: every parallel iterate
  worktree resolves the SAME shared main-repo directory
  (`resolve_main_repo_root`), so two sessions can race to refresh the same
  local `INDEX.md` — guarded by the same `file_lock` + `durable_atomic_write`
  pair the ADR index already uses for its own two-producer race.

`write_decision_drop.py`'s and `aggregate_decisions.py`'s own pre-existing
(duplicated) `drop_dir()` resolvers were left untouched rather than
centralized into the new lib module: `test_decision_drop_ssot.py` pins those
two files' own `resolve_main_repo_root` usage by name, and a real
centralization would need to update that registry for no functional gain —
the SSoT meta-test already tolerates independent per-site resolvers as long
as each is worktree-aware.

`integrate_regenerate.py`'s ADR-index-only inline post-merge refresh/stage
block was factored into a shared `_refresh_and_stage_index` helper
(parameterised by label/path/refresh function/regen hint) reused by both the
ADR index and the decision-log index, preserving the exact pre-existing step
tokens (`adr-index-refreshed`, `adr-index-stage-failed`, …) that
`test_adr_index_churn_integration.py` asserts on. Net effect: the file shrank
despite gaining a second artifact to regenerate.

**Post-push CI catch (ADR-045 `lib` package collision, not the earlier
bootstrap bug).** The PR's `Python (lint + test)` check failed:
`plugins/shipwright-build/tests/test_integration.py` and `test_tools.py`
import `tools.write_decision_log` **in-process**, in the same pytest session
that has already bound `sys.modules['lib']` to the build plugin's own
`scripts/lib` package — the exact ADR-045 shadowing trap `shared_lib_loader.py`
exists to survive, and the sys.path bootstrap added for the earlier bug does
NOT fix it (inserting a path earlier in `sys.path` cannot change what an
ALREADY-cached `sys.modules['lib']` resolves to). Fixed by routing
`write_decision_log.py`'s two `lib.decision_log_index` / `lib.agent_doc_shape`
call sites through `shared_lib_loader.load_shared_lib()` (the same mechanism
`triage_promote.py` already uses for `triage_defer`), and by changing
`decision_log_index.py`'s and `decision_drops_index.py`'s own internal
`from lib.atomic_write import …` / `from lib.file_lock import …` /
`from lib.repo_root import …` imports to relative (`from .atomic_write import
…`) — required because the loader's private-package fallback gives the module
a working RELATIVE import context, but an absolute `lib.X` inside it would
still resolve against whichever `lib` collided. `lib/adr_index.py` carries the
same absolute-import style and is therefore equally exposed in principle, but
nothing imports it in-process from a colliding plugin test today, so it is
left as a pre-existing, out-of-scope condition rather than fixed here — noted
for whoever next touches that file. Verified by reproducing the exact CI
failure locally (`cd plugins/shipwright-build && uv run pytest tests/
test_integration.py::test_setup_and_track_section tests/test_tools.py::
test_write_decision_log tests/test_tools.py::test_write_decision_log_creates_dir`)
before and after the fix, then running every plugin's own test suite plus the
full `shared/tests` suite to confirm no other in-process collision exists in
this diff.

The bootstrap regression test (ledger row 43) was split into its own
`test_write_decision_log_bootstrap.py` after adding it crossed
`test_write_decision_log.py`'s 300-line bloat-gate ceiling — a real seam
(subprocess/CLI-shape test vs. that file's in-process unit tests), not a
budgetary slice.

**Second post-push CI catch (canon-lint false positive, caught locally via a
fresh full `shared/tests` run before re-pushing).** The new
`decision_log_index.md` re-renders each `decision_log.md` entry's own title
verbatim as a link label, so ADR-259's title ("Re-tag mis-filed
compliance/security features...") reproduces the literal substring
`compliance/` in the generated index — tripping
`test_artifact_path_canon.py`'s `compliance` migration check, which already
allowlists `decision_log.md` itself for exactly this reason (arbitrary
historical prose legitimately naming legacy directory tokens). Fixed by adding
`.shipwright/agent_docs/decision_log_index.md` alongside `decision_log.md` in
all four `ALLOWLIST` blocks in `shared/scripts/lib/artifact_migrations.py`
(`planning`/`designs`/`agent_docs`/`compliance`) — the new file is a generated
sibling of an already-allowlisted source and inherits the same exempt class,
not a one-off carve-out for the single migration with a current finding. That
edit grew `artifact_migrations.py` from 632 to 641 lines, inside its existing
ADR-091 bloat exception (`state: "exception"`, limit 300, prior `current:
632`); bumped `current` to 641 in `shipwright_bloat_baseline.json` in this
same commit per ADR-091's own sanctioned remediation ("bump `current`
deliberately in the same commit"), rather than writing a new exception ADR for
a single-migration-family edit to an already-excepted file.

`write_decision_log.py`'s unused `status` kwarg (`append_decision`) and
`--status` CLI flag were removed — confirmed dead via a repo-wide grep (no
call site, no test) — to make room for the new refresh call within the
file's frozen bloat-baseline ceiling (`shipwright_bloat_baseline.json`:
`current: 377`, zero headroom before this change).

`docs/hooks-and-pipeline.md` gained rows for both new artifacts in the Merge
Reconciliation table and the Artifact Write Matrix, matching the doc-sync
registry test's forward+reverse requirement
(`test_churn_merge_doc_sync.py`).

`shared/templates/shipwright-gitignore.template` (and this repo's own
`.gitignore`, kept congruent by `test_gitignore_template_congruent.py`) gained
one line, `/.shipwright/agent_docs/*.tmp`: `decision_log_index.md` is written
through the same same-directory temp-then-rename `durable_atomic_write` uses
for the ADR index, and `agent_docs/` is re-included wholesale in the managed
block, so a hard-killed refresh would otherwise leave that temp file
committable in every adopted repo, not only this one.

## Consequences

- `decision_log_index.md` and the decision-drops `INDEX.md` are always
  fresh — refreshed at every write, not only as a side effect of folding
  drops (the exact defect the ADR-index fix closed for its own artifact).
- The decision-log index carries the same two-producer commit-boundary
  guarantee the ADR index does: whichever of `write_decision_log.py` /
  `aggregate_decisions.py` last touches `decision_log.md` also ships the
  refreshed index in the same commit.
- The decision-drops index is explicitly NOT a committed artifact and NOT a
  churn-resolvable path — a future contributor extending the pattern to a
  THIRD gitignored collection should look here first rather than reflexively
  adding a `CHURN_ALLOWLIST` entry that would never be exercised.
- `write_decision_log.py`'s public `append_decision()` signature dropped the
  `status` parameter and `main()` dropped `--status`; no caller passed it (a
  backwards-compat kwarg that was never wired to compact-format output).
- Two doubts raised by the Stage-3 `doubt-reviewer` were answered with a
  reasoned rebuttal rather than a code change (full reasoning in the iterate
  spec's `## Doubt Review` section): the decision-log index inherits
  whatever git-staging contract each calling skill (plan/build/deploy)
  already has for `decision_log.md` itself, rather than gaining a new,
  index-specific staging step; and `append_decision()`'s unlocked write to
  `decision_log.md` (as opposed to the new index's locked write) is a
  pre-existing source-level race this change does not introduce and does not
  extend — locking the source would need to span every writer that touches
  it, a different fix than "give this collection an index."

## Rejected alternatives

- Centralizing `drop_dir()`/`DROP_DIRNAME` into the new lib module — see
  Decision section; rejected to avoid touching a hand-maintained SSoT
  registry for no functional gain.
- A full IETF-RFC-index-style bidirectional obsoletes/obsoleted-by graph
  with derived multi-state `current-status` (accepted/rejected/deprecated/…)
  — the corpus has exactly ONE supersession marker today; building a general
  link-graph engine for one data point is speculative (YAGNI). The chosen
  design (regex-match `(supersedes ADR-NNN)`, annotate the superseded row)
  scales to however many more accrue without a rewrite.
- Rebuilding a "context register" filtering decisions by relevance area —
  raised in the operator's brief as a related-but-different card
  (trg-c7ef6eac); a plain table of contents delivers the token-compression
  value on its own and does not depend on the register existing first.
- Dropping the decision-drops index entirely, keeping only the decision-log
  index — one external architecture reviewer's suggestion (`revise`,
  proportionality concern: a producer-maintained index for transient,
  gitignored data is a second standing mechanism to explain). Not taken: the
  operator's own opening brief named both artifacts together, with the
  measured token cost of the drops directory (202 pending drops, ~4,085
  tokens) as part of the stated rationale — see the iterate spec's
  `## Architecture Review` section for the full reconciliation.
