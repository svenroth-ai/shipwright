# Mini-plan: B4 chat-first profile (iterate-2026-10-25-b4-chat-first-profile-sc)

Goal: add bundled `shared/profiles/chat-first-json.json` so a chat-first project builds, tests (pytest + Playwright on the served pane), previews and needs no deploy.

Steps
1. Extract `parse_test_output`/`run_tests` from `plugins/shipwright-test/scripts/lib/test_runner.py` (321 lines, no baseline entry) into `command_runner.py`, re-exported; test_runner.py 235 lines, zero behaviour change.
2. Add the profile: ux_shape chat-first, ui_host served-pane, stack.frontend vanilla-js, backend deliberately empty (FastAPI named in notes) so adopt scoring of existing fixtures is unchanged, dev_server block `uv run uvicorn app.main:app --port 3900` (no shell metacharacters), /api/health, testing unit pytest + e2e @playwright/test, deploy null. No CI/CodeQL registry entry (explicit none, comment in ci_workflow.py).
3. F17 blockers: browser-verify.md note; smoke default doc (profile dev_server before :3000); journey coverage cleared by @playwright/test *.spec.ts; `_DEFAULT_SERVICE` not reached (profile_config.py untouched, 301 lines); skip_reason key mismatch already tolerated by phase_validators_late._skip_reason.
4. Project step-7 scaffolding guidance for ux_shape chat-first; docs (stack-profiles, README, guide).
5. Tests: shared/tests/test_chat_first_json_profile.py (resolver+schema, dev_server block, testing, no CI mapping), plugins/shipwright-adopt/tests/test_profile_matcher_chat_first.py (existing fixtures unchanged), plugins/shipwright-test/tests/test_test_runner_chat_first.py.

Alternative approach considered: loader branches keyed on ux_shape - rejected, no loader needs to know the shape; the declared dev_server/testing blocks already carry it.
