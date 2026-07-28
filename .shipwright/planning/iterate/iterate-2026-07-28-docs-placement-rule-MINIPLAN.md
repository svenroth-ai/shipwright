# Mini-Plan — iterate-2026-07-28-docs-placement-rule

Spec: `iterate-2026-07-28-docs-placement-rule.md`

## Order, and why this order

The rule lands first, the measurement lands last. Everything between is a
deletion or a redirect that the rule already justifies.

| # | Step | Why here |
|---|---|---|
| 1 | `CLAUDE.md` — placement rule (AC1) | Every later deletion cites it. A cleanup whose reason lives only in a commit message is a cleanup that gets undone. |
| 2 | `gate_catalog.json` — remove the personal name (AC5) | Must precede the render, or the render carries it. |
| 3 | Move the render: `docs/gate-catalog.md` → `shared/config/gate_catalog.md` (AC2) | `git mv`, then regenerate — the file embeds its own regeneration command, so a plain move leaves a wrong instruction inside it. |
| 4 | Retarget the drift test + the five reference sites (AC2, AC3) | `test_gate_catalog_doc_sync.py`, `gate_policy.py`, `resolve_gate_policy.py`, `single-session-gate-discipline.md`, `hooks-and-pipeline.md`, `gate_catalog.json` description. |
| 5 | `guide.md` — the three gate policies (AC4) | The instruction half of what the moved file used to imply. |
| 6 | REQ-3 DESIGN — new render path (AC11) | The template a future campaign copies must name a file that exists. |
| 7 | Delete the five finished records (AC6) | Rule from step 1 applies. |
| 8 | Clean their references: `.gitignore` ×4, `claude-md-template.md`, `artifact_migrations.py` docstring, `stale_artifact_detector.py` docstring, `hooks-and-pipeline.md` (AC6) | A deletion is not done while a live file still points at it. |
| 9 | Delete `print_next_migration_prompt.py` + test + 8 allowlist lines (AC8) | Depends on step 7 — the tool exists to announce the deleted doc. |
| 10 | **Measure** the path-canon exemption (AC7) | Only meaningful once the files are actually gone. Remove `docs/migrations/**` ×4, run the check, keep the result. |
| 11 | Verify: full suite per test root + ruff (AC12), `docs/` inventory (AC9), surviving code references (AC10) | |

## The alternative that was not taken

**Do steps 7–10 only; leave `gate-catalog.md` in `docs/`.** Smaller diff, no
contact with the gate-catalog machinery at all, and the migrations cleanup —
which is uncontested — ships today.

Rejected because it leaves `docs/` containing exactly the file the new rule is
written against, which makes the rule advisory on the day it is written. The
gate-catalog work is also cheap now that the destination is settled: a move plus
six string retargets, with the drift test proving the move landed.

## Risk, and what catches it

| Risk | Catch |
|---|---|
| The render's embedded regeneration hint keeps the old path | Step 3 regenerates rather than moves; AC3 re-runs the drift test. |
| Path-canon goes red because a surviving guide holds a legacy path | Step 10 measures instead of assuming; the exemption returns with a stated reason if red. |
| A shipped runtime prompt keeps a dead path | `single-session-gate-discipline.md` is in step 4; `update-marketplace.sh` after push. |
| A deleted doc is still referenced by live code | Step 8 + AC6 enumerate the sites; a repo-wide grep for the five basenames is the check, not memory. |
| Deleting the dormant tool breaks path-canon | Its 8 allowlist entries go in the same step (9); the full suite in step 11 is the proof. |
