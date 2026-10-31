# Mini-plan: P3 spec chain

Goal (WHAT): every feature/change/bug iterate leaves a plan stub whose path rides on its recorded event, and "which runs shaped AC X" has a one-command answer including older runs.
Reason (WHY): a rebuild must keep the WHAT/WHY and its provenance; the measurement found plan files in five shapes, the PR only via commit grep, and AC history for 13% of ACs.

Changes:
1. `shared/scripts/lib/spec_chain.py`: stub shapes (tiny/three/full), plan finder (field, convention, legacy, ADR), PR finder (field, then Run-ID commit), catalog AC parser, `ac_history`.
2. `shared/scripts/tools/write_plan_stub.py`: writes `.shipwright/planning/iterate/<run_id>/plan.md`.
3. `finalize_iterate.py`: stamps `plan_path` when the stub exists (2 lines; file under its grandfathered cap).
4. `verifiers/plan_stub_check.py`: F11 claim check, WARNING only, strict-exempt; registered.
5. `tools/spec_chain_cli.py`: `lookup --ac`, `coverage`, `replay --seed`.
6. Docs: F5b.md, hooks-and-pipeline.md. Tests: `shared/tests/test_spec_chain.py`.
Release already regenerates the traceability matrix (changelog Step 5.5, `refresh_compliance_docs.py`); no new schedule added.
Not changed: no write-time gate, no tracked index file (computed on demand so it cannot go stale), PR number not required (known only after push).

Decisions after plan review (both reviewers revise, both architecture reviewers approve):
- `pr` stays optional; it can be added after the PR opens with an event_amended (the lookup applies amendments), and is otherwise found from the squash commit carrying the Run-ID (13 of 20 sampled legacy runs resolved this way).
- Stub scope: every feature/change/bug iterate in any project (the event carries no complexity, so tiny runs write the one-line stub); the F11 check only warns.
- Legacy plan lookup matches the exact name or a mini-plan suffix, never a bare prefix; a recorded plan_path is read only under .shipwright/planning/.
- Lookup by AC and by FR (`--fr`, runs by affected_frs).
- The release already regenerates the traceability matrix (changelog Step 5.5); the matrix was stale because no release ran, not because the step is missing. Not changed here.
