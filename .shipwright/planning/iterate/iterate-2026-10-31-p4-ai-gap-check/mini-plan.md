# Mini-plan: P4 independent AI gap check

Goal (WHAT): before the commit, a fresh-context non-Claude model reads the diff, the catalog's acceptance criteria and the change's own declaration and tells the PR reader whether the declaration is a fair account (agree/disagree) and whether a catalog gap exists (yes/no). Advisory, never blocks.
Reason (WHY): the package measurement found that "no requirement affected" is wrong on about 15 to 20 of 100 PRs, and the author cannot be the only judge of it.

Changes:
1. `shared/scripts/lib/ai_gap_check_core.py`: prompt (framed as wrong-"none" and catalog-gap check), one-pass template, reply parser, the PR-body block and the visible "not run" note, diff trimming (finalization records out, whole files cut past a cap).
2. `shared/scripts/tools/ai_gap_check.py`: CLI; reuses `external_review.review_with_openrouter` (same route, key check, pinned models, retries); free text only through files; exit 0 always; writes `ai-gap-check.json` and `ai-gap-check.md`.
3. `shared/scripts/tools/verifiers/ai_gap_check_record.py`: F11 claim check, WARNING only, strict-exempt, registered.
4. `shared/scripts/tools/ai_gap_check_replay.py`: measurement over merged PRs.
5. FOLD one WHAT/WHY AC into FR-01.11 (AC49). Docs: F5b.md, F11.md, sub-iterate-runner.md, hooks-and-pipeline.md. Tests: `shared/tests/test_ai_gap_check.py`.
6. Measure record: `2026-10-31-baseline-package-P4-MEASURE.md` (35 PRs, two prompt versions, fresh 10 for the operator, pending).
Not changed: no new required check, no blocking F11 check, no new provider client, no PRs outside iterate.
