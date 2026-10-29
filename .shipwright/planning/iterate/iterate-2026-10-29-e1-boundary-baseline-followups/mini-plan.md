# Mini-plan: design boundary baseline follow-ups (campaign e2e-run-findings, E1)

Files: `plugins/shipwright-design/scripts/lib/boundary_baseline.py`, `scripts/checks/setup-design-session.py`, tests, `integration-tests/test_design_takes_package.py`, `docs/hooks-and-pipeline.md` row.

1. HEAD move within a run: keep old entries and salt, add nothing.
2. Record `run` (SHIPWRIGHT_SESSION_ID); another run's baseline is rewritten on write, strict on read.
3. `at_repo_root()`: a non-toplevel `--project-root` writes nothing and reads strict (`not_written`).
4. Drop the backslash replace in `dirty_paths`.
5. Brief integration test: real repo + baseline, boundary gate included.

Risk: `touches_io_boundary` (the baseline JSON gains a `run` key; old files read as another run, i.e. strict, when SHIPWRIGHT_SESSION_ID is set). Alternative considered: `git rev-parse --show-prefix` mapping for subdirectories - rejected, fail-closed was requested.
