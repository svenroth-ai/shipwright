# Mini-plan: R1d-1 — silent-failure gates read a moving file where it lives, per commit

Run: `iterate-2026-11-28-r1d-silent-gates`. Campaign BRIEF `.shipwright/planning/campaigns/2026-11-14-root-files-into-shipwright-dir-BRIEF.md`, items 4.1, 11.7.4, 14.4; result recorded as 12.14.

## Split
R1d is split (the BRIEF allows it). R1d-1 = everything that reads a moving file through git history or skips on a missing file. R1d-2 = the `.gitignore` work, `inline_suppressions` in `SENSITIVE_PATH_RE`, the `pr-review-run.yml` regex / A4, and the consumer workflow templates.

## Steps
1. `shipwright_layout.locate_at(root, commit, new_rel, legacy_rel)`: commit `None` → working tree (`isfile(new)`); else `git cat-file -e <commit>:<new_rel>`; any failure → legacy. Non-moving key → legacy.
2. `shipwright_paths.rel_at(key, commit, root)` delegates to it (root becomes a required argument; every caller already has its repo).
3. Callers pass their repo: `events_layout_ci._layout_at`, `ci_supplychain_ack_store._read_legacy`, `_project_gate_rollout_snapshot._rollout_declared_split_names` (both keys), `test_results_backfill_check` (commit and parent reads; its working-tree status check accepts `known_rels`).
4. `_ac_baseline_growth.baseline_grown_since_parent`: when the given baseline is the registry's AC baseline (either place), read the parent at `rel_at(..., parent, root)`.
5. `anti_ratchet_check.py --require-baseline`: absent baseline → exit 1 (JSON `missing-baseline`). Default stays fail-open for consumers.
6. `scripts/hooks/pre-commit`: run the anti-ratchet whenever the checker script exists, with `--require-baseline`. `bloat-check.yml`: `--require-baseline`; base baseline read at `shipwright_rel_at.py bloat_baseline --commit <base>`; `--head` via the same tool.
7. New `shared/scripts/tools/shipwright_rel_at.py` CLI (exit 2 on unknown key).
8. Docs: guide bloat table note, hooks-and-pipeline pre-commit paragraph, stale "twelve" derived-snapshot counts (now thirteen paths).

## Tests (`shared/tests/test_shipwright_paths_silent_gates.py`)
Real git histories with the file moved: `rel_at` per commit / working tree / unknown commit / non-moving key; CLI parity; AC growth across a move; events-layout CI; rollout manifest; anti-ratchet fail-closed and found-in-new-place; the workflow and hook call the required mode. Negative control on `origin/main`: all fail.

## Risks
- `bloat-check.yml` is a required check: `uv run` of the new tool before `uv sync`? The workflow already runs `uv run` scripts in later steps; the base-capture step now needs uv set up first (check step order).
- The pre-commit hook now runs whenever the checker exists, so a worktree whose baseline was deleted blocks: intended.
