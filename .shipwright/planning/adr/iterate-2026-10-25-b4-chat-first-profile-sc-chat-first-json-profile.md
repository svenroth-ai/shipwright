# Bundled chat-first-json stack profile (B4)

Run: iterate-2026-10-25-b4-chat-first-profile-sc. Campaign brief-driven-run-b-intake-design-e2e, unit B4.

## Decision
Add `shared/profiles/chat-first-json.json` (Python app serving a pane, local JSON data, pytest + Playwright, no deploy) as data only; no loader learns about `ux_shape`. `test_runner.py` (321 lines, no baseline entry) was split: `parse_test_output`/`run_tests` moved to `command_runner.py` and re-exported.

## F17 blockers
Browser Verify, smoke default, `_DEFAULT_SERVICE` and journey coverage are cleared by the profile declaring `dev_server` and `@playwright/test`; the `reason`/`skip_reason` mismatch was already tolerated. Prompt guidance now routes the smoke URL and `browser_verify.py --url` through the profile's port. `profile_config.py` (301 lines) is untouched.

## Adopt matching
`stack.backend` is empty on purpose: the python-cli fixture declares fastapi, so listing it made this profile outrank `python-plugin-monorepo` (found by running the matcher tests). FastAPI is named in `notes`.

## Architecture Review
Both external reviewers approved (glm approve, openai approve); no findings beyond a request to pin the data contract, done in the test (exact-dict assertion).

## External-Plan-Review-Findings
| Finding | Disposition |
|---|---|
| Register a bloat baseline instead of splitting test_runner.py | rejected-with-reason: the brief mandates extraction first; the monkeypatch target `test_runner.run_tests` is still looked up in the module globals (test passes) |
| Verify every import site of the moved functions | accepted-and-fixed: grep done, only `lib.test_runner` imports and one monkeypatch, all green |
| Smoke/Browser Verify port is a docs promise | accepted-and-fixed: confirmed prompt-resolved (smoke_test.py takes `--url`; `browser_verify.py` defaults to 3000); prompts now pass the profile port; playwright.config baseURL and `dev_url` named in step-7 guidance |
| Pin that no default-service value leaks | accepted-and-fixed: exact-dict assertion on the declared service |
| Comment that the empty backend is load-bearing | accepted-and-fixed: `_comment_backend` in the profile |
| Add a generated-project end-to-end acceptance test | rejected-with-reason: that is campaign unit B7 (real run through the WebUI); installing uvicorn/Playwright in a unit test is out of scope here |

## Doubt-review dispositions
| Doubt | Disposition |
|---|---|
| medium: step-7 left Playwright webServer at the template's npm run dev / :3000 and the json reporter unspecified | accepted-and-fixed: guidance now names webServer command/url and the e2e-results.json reporter |
| low: bundled e2e always goes through playwright_runner, so the declared command is not selected | accepted-and-fixed: noted in the profile `notes` |
| low: chat-first-json could win a python repo if python-plugin-monorepo is shadowed by an invalid project file | rejected-with-reason: edge case on a deliberately broken override; scores 1/(n+1) vs 1/n otherwise, and generic is the alternative |
| low: bare-name command_runner import and two stale nosemgrep docstring pointers | rejected-with-reason: mirrors existing _SHARED hygiene, no collision today; pointers are comments |
