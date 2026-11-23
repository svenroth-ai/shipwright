# P4: release CLI part 2 (sync, commit-and-tag, record-event, close-phase)

Run: iterate-2026-11-23-p4-cli-sync-commit-close. Campaign dfp-pilot-changelog-p3-p8, unit P4. Complexity: operator-accepted-large (classifier), complexity_override operator-accepted-large.

## Architecture Review
External: glm approve, openai approve (no findings blocking). Internal (architecture-internal-reviewer, opus): approve with gaps: release_state.json ownership and untracked state (done: written under `.shipwright/runtime/`, close-phase asserts a clean tree), run-state keyed on project root (done in the P3 fix list), subprocess scripts explained (shared `lib` must not be imported into the plugin's own `lib` package; programme P16).

## External-Plan-Review-Findings
| Finding | Disposition |
|---|---|
| P3 fix list missing from the plan | accepted-and-fixed: done first, one re-pin, one delta set |
| F1b vs B4 guided tag-on-origin tension | accepted-and-fixed: verify is mode-aware (`waits_for_merge`), a guided release on a feature branch passes `tag_remote` while waiting |
| Two subprocess scripts duplicate importable code | rejected-with-reason: the plugin's `lib` shadows shared `lib`; each runs the shared helper in its own process |
| Run state per git directory | accepted-and-fixed: keyed on project_root |
| Squash or rebase changes the release commit before the tag is pushed | rejected-with-reason for this unit: the tag push stays a literal command by decision (F1a/F1b); listed as an open item for the operator |

## External-Code-Review-Findings
| Finding | Disposition |
|---|---|
| Pipeline mode still writes phase_history, dashboard and handoff (F10) | rejected-with-reason: F10 keeps C2, C3 and phase_history in a dispatched run; single-session-apply never writes phase_history |
| verify re-derives shared root | accepted-and-fixed: release_paths.shared_root |
| PR state and release page only trust the reported values | rejected-with-reason: verify is git-only by design (no gh in a read-only check); the page status comes from the page step |
| tree_clean informational only | accepted-and-fixed: a failed check in a hand-invoked release |
| canon writer failure does not stop the later writers | accepted-and-fixed: break at the first failure |

## Internal reviews
opus-plan-reviewer: close-phase must fail closed without run state (fixed), tree_clean enforced (fixed), commit-and-tag re-run after a failed audit (fixed: HEAD already `chore(release): vX` and clean is verified and tagged), sync_not_run guard (fixed). Spec, code and doubt reviewers ran on an earlier tree; their findings were fixed (pr_url_missing, written list, remote exit, restore only after a release commit, stored run id first) and the cascade is delegated to the orchestrator for the final tree.

## Confidence Calibration
Boundaries: release_run.json, release_state.json, the event and tag round trip. Probes: real-git tests (test_release_event_real_git.py, tests/golden/test_p4_decisions.py through both drivers) covering F1a, F1b, F4, F6, F10, F7, B1, B4 including a remote tag deleted after the release (verify must fail). Findings from probes: B4 first failed on the scratch fake origin (fixed with the push URL), then on legacy events without a run id (fixed with a type/phase/detail match). Two consecutive probes without a finding, asymptote reached. Not probed: a squash merge changing the release commit (open item), a develop trunk in the merge check.

## Self-Review
7 items pass (see self-review-payload.json).
