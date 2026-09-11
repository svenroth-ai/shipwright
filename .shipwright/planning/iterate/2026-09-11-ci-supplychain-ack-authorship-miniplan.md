# Mini-Plan: CI supply-chain ack authorship guard

- **Run ID:** iterate-2026-09-11-ci-supplychain-ack-authorship

## 1. Files to create/modify
- `shared/scripts/tools/record_ci_supplychain_ack.py` — edit: add
  `refuse_if_campaign_runner_context()`, `--commit` mode, `provenance` stamp.
- `shared/scripts/tools/verifiers/ci_supplychain.py` — edit: `_validate_fields`
  requires `provenance` for non-legacy sources.
- `plugins/shipwright-iterate/skills/iterate/references/campaign-mode.md` —
  edit: Step 3.4 prose now says the rule is enforced, names the mechanism.
- `plugins/shipwright-iterate/scripts/lib/diff_risk_recheck.py` — edit:
  docstring addendum, no behavior change (Step 3.4's own logic is untouched).
- `docs/hooks-and-pipeline.md` — edit: addendum to the existing CI
  supply-chain gate section.
- `shared/tests/test_record_ci_supplychain_ack.py` — edit: 8 new tests
  (guard × 2 modes, no-op when unset, `--commit` mode, provenance stamping
  × 2 modes, already-committed refusal message, missing-provenance rejection).
- `shared/tests/test_ci_supplychain_ack_per_run_home.py` — edit: `_ack()`
  helper gains a default `provenance`; 2 new tests (per-run rejection,
  legacy grandfather).

## 2. Work breakdown
1. Read `record_ci_supplychain_ack.py`, `verifiers/ci_supplychain.py`,
   `ci_supplychain_ack_store.py`, `campaign-mode.md` Step 3.4,
   `diff_risk_recheck.py` in full — done (this session).
2. Search for an existing operator/authorship-gate pattern to reuse
   (`isatty`, confirmation flags) — none found; env-var ambient check is the
   available primitive. Confirmed `SHIPWRIGHT_LOOP_UNIT_ID` is
   harness-injected around the campaign runner subprocess, not agent-typed
   per Bash call, via `capture_session_id.py`'s docstring + propagation code
   — done.
3. Implement `refuse_if_campaign_runner_context()` in the writer, called
   first in `main()`. Test: guard fires / no-op.
4. Implement `commit_ci_paths()` + thread `commit` through `build_ack()`,
   reusing `_iterate_changed_paths` (verifier's own view) and
   `committed_bytes_reader`. Test: `--commit` round-trips through the F11
   verifier.
5. Stamp `provenance`/`provenance_ref` in both modes. Test: correct value
   per mode.
6. `_validate_fields(ack, source)` requires `provenance` when
   `source` is not legacy. Test: per-run rejection, legacy grandfather.
7. Update `campaign-mode.md`, `diff_risk_recheck.py` docstring,
   `docs/hooks-and-pipeline.md` to match the enforced contract.
8. Full `shared/tests/` root + `plugins/shipwright-iterate/tests/` Step 3.4
   / contract tests — 0 regressions confirmed.
9. `uvx ruff@0.15.15 check` on every touched file — clean.

## 3. Component hierarchy
n/a — no UI.

## 4. Data model changes
n/a — no DB/RLS. The `ci_supplychain_ack.json` shape gains two new optional
top level fields (`provenance`, `provenance_ref`); no migration needed since
it's a per-run file, not a table.

## 5. Test strategy
Unit + integration tests only (see Test Completeness Ledger in the iterate
spec) — this is a CLI + verifier pair with git-fixture-backed tests
(`git_origin_repo`/`make_worktree` fixtures), which already exercise the
real writer→commit→verifier round trip. No E2E needed (no web/API surface —
see Verification section, surface: none).

## 6. Alternative approach — rejected

**Considered: bind authorship to `SHIPWRIGHT_SESSION_ID` instead of
`SHIPWRIGHT_LOOP_UNIT_ID`** (refuse when the session that would write the ack
matches the session recorded as having created the run's worktree, via the
`--session-id` already captured by `setup_iterate_worktree.py`'s pointer
file at `.shipwright/iterate_active/<run_id>.json`).

**Rejected because:** a Task-tool-spawned campaign sub-iterate runner and its
orchestrating session are plausibly the SAME `SHIPWRIGHT_SESSION_ID` (Claude
Code subagents commonly share the parent session's harness-level session
id), and — more decisively — the documented remedial flow has the OPERATOR
resolve a STRICT-STOP escalation from that SAME session/terminal the
autonomous loop was running in, not necessarily a fresh one. A
session-identity check would then refuse the legitimate operator action as
often as the violation it targets: false positives on the exact path the
gate must keep open. `SHIPWRIGHT_LOOP_UNIT_ID` avoids this because it is
scoped to the SPAWNED RUNNER's own process lifetime specifically (injected
around that subprocess, not the orchestrator's ambient shell) — confirmed via
`capture_session_id.py`'s docstring ("autonomous-loop env vars, only emitted
when set by the parent runner") and the fact that no `export
SHIPWRIGHT_LOOP_UNIT_ID` appears anywhere in the orchestrator's own
post-spawn/post-STRICT-STOP instructions.

## Known limitations
- The guard is env-var-based and therefore a mitigation, not a
  cryptographic guarantee (see the iterate spec's honesty note). Disclosed,
  not acted on further — building an unspoofable operator-identity check is
  out of scope (no signing infra exists in this repo) and was explicitly
  ruled out as disproportionate for this fix's threat model (an
  honest-but-noncompliant autonomous agent, not an adversarial one).
