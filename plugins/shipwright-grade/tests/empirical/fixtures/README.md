# Empirical replay fixtures

Recorded payloads for the empirical calibration suite (`-m empirical`).

Each file is `record/replay` output keyed by `<repo>@<sha>` — the **projected
`GradeInputs` + report-extras + a redacted gh audit log** for a pinned commit of a
real OSS repo. The suite **replays** from these so it stays deterministic and
offline: the engine (`compute_grade`) runs on every replay, so a rubric
regression is still caught, but no network / repo checkout is needed. Network is
only used to **refresh** a payload (`run_empirical.py --refresh`).

## Determinism note

The git-derived signals are SHA-deterministic (same commit → same tree → same
inputs). The **network** tiers (CI test-health via recent merged PRs, security
via code-scanning) are a *snapshot at record time* — re-recording months later
may shift them as a repo's recent PRs change. That is precisely why we freeze the
snapshot into a fixture and replay it; a `--refresh` diff is the calibration
review signal, not a live moving target.

## What is NOT stored

The gh audit log is **redacted** — only `{args, ok, error, returncode,
stdout_len}`, never a raw response body (no URLs/headers/payloads). The rendered
HTML report gallery is a transient CI artifact (gitignored), not committed here.

## Current state (G5)

The proof subset (`pallets/flask`, `expressjs/express`, `request/request`) is
recorded and committed. The full curated set + edge cases (`ci-only`: `ky`,
`babel`, `arrow`, `linux`) are recorded live by the CI launch-gate job
(`.github/workflows/grade-empirical.yml`). **The `-m empirical` gate is currently
RED by design** — the recorded fixtures show the cold-repo projector mis-grades
`flask` (F) below deprecated `request`; calibrating the projection heuristics is
the follow-up (see the campaign G6 sub-iterate / triage anchor). A red launch gate
correctly blocks launch until the grader ranks real repos sensibly.
