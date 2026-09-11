# Mini-Plan: keystone gate post-merge detective arm (ruling Q5)

Full design: `.shipwright/planning/iterate/2026-09-10-keystone-detective-arm.md`.
Revised after external Architecture Review (§3.5) and external plan review (both `revise`,
2026-09-10) — see "Revisions from plan review" below.

## Approach chosen

Build ONE new, additive module that COMPOSES with existing frozen modules rather than editing
them. No CLI, no `ci.yml` touch (§3.5).

`shared/scripts/tools/verifiers/_keystone_detective_core.py`:

- `build_verified_manifest(committed_manifest, evidence) -> dict` (pure, no I/O): per-requirement-
  key, per-link substitution of `status`/`executed` from `ExecutionEvidence.requirements`, matched
  by link `id` WITHIN the same requirement key; unmatched links become `executed: "not_run"`.
  Returns a manifest whose substituted nodes are freshly built dicts (no shared mutable state with
  `committed_manifest` — a genuine per-link copy, not a reference into the original, so a caller
  mutating the result cannot corrupt the manifest that was read from git). Raises `ReadError`
  (reused from `_keystone_base_manifest`) if the evidence's own per-requirement `tests[layer]`
  list carries two links with the same `id` within one requirement — an ambiguous, hand-editable
  shape this reader refuses to silently resolve one way.
- `classify_commit(commit: str, *, project_root: Path) -> DetectiveResult` (I/O-driving
  orchestration, no CLI wrapper): resolves the commit's FIRST parent internally
  (`git rev-parse --verify "<commit>^1"`) — never accepts a caller-supplied parent, closing the
  mismatched/malicious-pair risk plan review flagged. A root commit (no `^1`) or an unresolvable
  `commit` raises `ReadError` naming the reason. Then: `resolve_ci_verification(commit, ...)` →
  short-circuit to `no_qualifying_run` / `run_not_verified` / `verification_query_failed` per
  design §4.2; only on `verified` does it call `resolve_execution_evidence(...)`, read both
  manifests via `read_base_manifest` (target commit AND its first parent), build the change set
  via `ac_change_set`, build the verified manifest, and call `evaluate_keystone` — all five reused
  UNEDITED (imported, not copied).

## Revisions from plan review (both external reviewers: `revise`, 2026-09-10)

1. **Dropped the CLI entirely** from this plan — the original draft still described
   `check_keystone_detective.py` with `--commit`/exit codes despite spec §3.5 already reducing
   scope to a module-only deliverable. Reconciled: this plan now matches §3.5 exactly. (Both
   reviewers, high/medium.)
2. **Renamed "six-way" to "seven-way"** throughout the spec and this plan — the table always had
   seven rows; only the prose label was wrong. (Both reviewers, low/medium.)
3. **`classify_commit` no longer takes a caller-supplied `parent`.** It resolves the first parent
   itself and rejects root commits / merge-parent ambiguity with a documented `ReadError` rather
   than trusting an externally-supplied SHA that could name the wrong lineage. (Both reviewers,
   medium — merge-commit / root-commit edge case.)
4. **Duplicate test `id`s within one requirement's verified evidence now fail closed**
   (`ReadError`), rather than silently picking one via last-write-wins dict construction. (openai,
   medium.)
5. **PR-merged commits are named, explicitly, as a possible `no_qualifying_run` case.** Design
   §4.2 originally claimed this was the dominant real-world outcome once the P3.6 drift is fixed;
   **that claim was corrected in Plan Review Round 2** (§3.5.2) — this repo's `ci.yml` triggers on
   every push to `main`, so an ordinary merge DOES get its own push-event run, making
   `no_qualifying_run` the edge case, not the steady state. AC-D13 still pins a fixture for the
   scenario (a commit whose only run is `pull_request`-event), correctly framed. (glm, medium;
   corrected round 2, both reviewers, high/medium.)
6. **`classify_commit` canonicalizes `commit` to a full SHA before any resolver call**, closing
   the window where a mutable ref could move between the parent lookup and the resolver/manifest
   reads. (Round 2, openai, medium.)
7. **Either resolver returning a status outside its own documented contract now fails closed**
   (`ReadError`) rather than silently falling through to the "next" branch. (Round 2, openai,
   medium.)

## Alternative considered and rejected

**Extend `ExecutionEvidence` to also carry `acs` (AC-level bindings) from the downloaded
artifact**, so the detective module could read AC-level execution data directly instead of
reconstructing it from the FR-level `tests` list plus the committed manifest's own AC→test-id
map. Rejected: `ci_execution_evidence.py` is a frozen, heavily-reviewed, content-binding-critical
module (P3.5 restart, 2 external review rounds); adding a field changes its public contract for
every existing caller (`promote_required_layers.py`) and reopens a security-relevant module for a
consumer that doesn't need to — the FR-level `tests` list already contains every link id an AC
binding could possibly reference (verified empirically: `acs[ac].tests[layer]` entries are a
structural subset of the requirement's own top-level `tests[layer]` list, same `id` values,
confirmed against the live `test-traceability.json`). Matching by id is sufficient and touches
nothing frozen.

## Files touched

- NEW `shared/scripts/tools/verifiers/_keystone_detective_core.py` — orchestration half
  (`classify_commit`, the seven outcome constants, `DetectiveResult`).
- NEW `shared/scripts/tools/verifiers/_keystone_detective_manifest.py` — pure half
  (`build_verified_manifest`, no I/O). Split from the combined module after code review (low —
  crossed 300 LOC once the plan-review-round-2 fixes were added), same pure/orchestration split
  already used for this feature's own test modules.
- NEW `shared/scripts/tools/tests/test_keystone_detective_core.py` — classification/short-circuit
  half (AC-D1..D5, D10, D12..D15). Split from a single 346-line file at build time, crossing the
  300-LOC guideline, same discipline `_keystone_ac_digest_never_silent.py` used against its
  sibling.
- NEW `shared/scripts/tools/tests/test_keystone_detective_greenness.py` — greenness-recomputation
  half (AC-D6..D9, AC-D11, plus the `build_verified_manifest` mutation contract), split out of the
  same file for the same reason.
- `shared/scripts/tools/tests/_keystone_repo.py` — extended with three small shared helpers
  (`make_verification`, `make_evidence`, `repo_with_ac01_edit`) used by both new test files, after
  code review (low) found them copy-pasted verbatim between the two.
- Triage: `trg-a05c4aba` closed on merge, referencing this run_id, noting the Architecture
  Review's scope reduction (pure module, no CLI/wiring — a future card if a real consumer
  emerges).

## Risks

- Windows path length on `git show <sha>:<long-path>` — already solved by reusing
  `read_base_manifest`/`git_blob_read.read_committed_text` (blob-OID read, no path in the
  argument), not re-implemented.
- `resolve_execution_evidence` signature requires `committed_manifest` — must be the manifest AT
  the target commit, not at its parent; a swapped argument would silently content-bind against
  the wrong commit's structure and always error. Guarded by a dedicated unit test (AC-D7's fixture
  uses distinguishable base/head structures).
- First-parent resolution on a merge commit only inspects that one lineage — documented as
  intended in design §4.2's added note (a merge commit's OTHER parent's changes are not this
  control's concern; the merge commit's OWN CI-verified evidence is what is being judged, and
  first-parent is the standard "what would ordinarily have been reviewed" lineage), not silently
  assumed.
