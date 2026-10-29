# E6: harness and fixture for the skill-backed app class

Run: `iterate-2026-10-29-e6-e2e-harness-skill-app` (campaign e2e-run-findings, finding F8, scope_frs FR-01.06, FR-01.01).

## Decision

The operator end-to-end run (`integration-tests/e2e-webui/`) now builds the **skill-backed board app**
(`integration-tests/fixtures/social-engagement-board/`, profile `skill-companion-app`, `ux_shape: classic`,
`ui_host: served-board`) instead of the chat-first desk. The chat is the Claude app, so the harness replaces the chat
commands (H06-H11) with checks of the companion's JSON API, the served board in a browser and the project files.
The chat-first fixture stays only for the chat-first design tests and goes with them.

Operator decisions recorded here (brief section 7, decided by the orchestrator for this autonomous run):

- Target of the second run: the Social Engagement board look from a Brief package (Untitled UI kit plus the package's
  own brand tokens). The fixture's `visual-guidelines.md` therefore declares all 23 kit colour tokens and the font
  sizes as `--color-bg: #f6f7f9` lines and passes the E4 intake check with no issues and no warnings.
- Soft items that become hard checks: exactly S01, S02 and S04-S08. S03 (screenshot-check metric) stays soft. S07 is
  rewritten for a board (an unknown route answers a JSON 404), S01 for a board (no chat input or panel).
- Also hard: H12 (plugin shape) and H13 (no design screen left as the plain mockup copy, the gap no tool detects).
- Resume: `SHIPWRIGHT_E2E_RESUME_RUN` continues a stopped run only when the folder recorded the same fixture, package
  hash, profile and plugin commit; the report records the commit.

## Architecture Review

External GLM and OpenAI: approve option A (new fixture beside the old one, new check modules, resume). Internal
`architecture-internal-reviewer`: approve with three revisions, all accepted: resume refuses an earlier run that does not
match (identity manifest), the soft-item scope is recorded (above), the mockup-copy check is a named module (H13).

## Internal Plan Review

`opus-plan-reviewer`: accepted-and-fixed: API contract written into the package (`brief.md` Companion API, with a Python test
tying every route the harness calls to it); Origin header sent on state-changing calls and loopback only; S07 rewritten;
plugin commit in the report; S08 expected gates listed apart from the answering code; data reuse on the Test phase's
dev folder handled in H06/H07/H09 (threads still `new` are used, evidence says when the folder was not fresh); fixture
tokens run through the E4 checker (muted, success adjusted for contrast). Rejected-with-reason: a cross-origin POST
refusal check (profile hardening is not an acceptance item of this fixture; follow-up); static scan restricted to
network clients (the URL and key scan on `backend/` and `board/` is kept, comment lines skipped).

## External-Plan-Review-Findings

| Finding | Disposition |
|---|---|
| GLM/OpenAI: resume has no contract for stale or half-written folders | accepted-and-fixed: identity manifest, direct `run-*` child, no link, not finished |
| OpenAI: injected-reader tests do not prove the adapters work together | accepted-and-fixed: a stub companion served over real HTTP plus a real browser snapshot test |
| GLM: chat.ts replacement may break legacy tests | rejected-with-reason: only the spec and its own unit tests imported it; the legacy fixture is used by Python tests |
| GLM: cache-sync artifacts | rejected-with-reason: no plugin-side files change |

## External-Code-Review-Findings

| Finding | Disposition |
|---|---|
| GLM/OpenAI: resume pushes a synthetic gate that fails S08 | accepted-and-fixed (371e1a60a): recorded as a step |
| OpenAI: H08/H09 do not read stored state back | accepted-and-fixed (7bf8d9a03): GET after each mutation, `noPersist` stub flaw |
| OpenAI: S02 does not tie each card to its tab | rejected-with-reason: per-tab badge presence and valid values are checked; card identity needs app markup the package does not fix |
| OpenAI: a completed pipeline blocks resume after a crash in the checks | accepted-and-fixed (7bf8d9a03): resumable until `markFinished` |
| GLM: tab order enforced | accepted-and-fixed (7bf8d9a03): order is not required |
| GLM: unit test for a `..` path does not test what it claims | accepted-and-fixed (7bf8d9a03): test uses a foreign folder |
| GLM: route test misses template literals | accepted-and-fixed (7bf8d9a03) |

## Self-Review

1 spec compliance pass; 2 error handling pass (every adapter failure becomes a recorded fail); 3 security pass (loopback only, resume input untrusted, no file contents in the report); 4 test quality pass (each hard check has a passing and a failing stub case); 5 performance pass; 6 naming and structure pass (all files <= 300 lines); 7 affected boundaries pass (the package against the real intake check and dry harness; the board snapshot against a real browser).

## Confidence Calibration

Probes: the package against `brief_intake_checks.check_content` and `token_warnings` (first run found two missing optional tokens and two contrast misses, fixed, second run zero), the stub companion with each flaw, a real Chromium snapshot of a faithful and a flawed board. Not probed (needs the real WebUI and a real agent run, E8): the wizard's `stack-profile-card-skill-companion-app`, the preview button for a `deploy: null` profile, how the WebUI continues a resumed task, the real Test phase's data folder state.
