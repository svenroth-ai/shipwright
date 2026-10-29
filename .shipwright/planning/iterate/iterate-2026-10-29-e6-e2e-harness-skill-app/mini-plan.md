# Mini-plan: E6 harness and fixture for the skill-backed app class

1. Fixture: `integration-tests/fixtures/social-engagement-board/` (profile skill-companion-app, ux_shape classic, ui_host served-board, no chat-map, five kit-free board mockups sharing one nav, token lines `--color-bg: #f6f7f9` in visual-guidelines.md) plus answer key `social-engagement-board-expected-result.md`. Legacy `social-engagement/` stays for the legacy chat-first tests.
2. Harness modules (each <= 300 lines, pure over injected readers so unit tests need no browser): `board-api.ts` (H06-H11 over the companion HTTP API, replaces chat.ts), `board-dom.ts` + `tokens.ts` (S01, S02, S04 over a DOM snapshot), `project-checks.ts` (H12 plugin structure, H13 screens vs mockup copy, S05 seed and external calls, S06 test results), `gates.ts` (S08 by meaning), `resume.ts` (resume plan from an earlier run folder), `follow.ts` (moved out of the spec), tour rewritten for the board.
3. Report template: new placeholders for the composed-screens check and the resume note; report.ts fills them.
4. Tests: Playwright unit specs for every module; Python in-process tests: the package validates, passes the intake content check and has zero token warnings, passes the dry harness, mockups share one nav, answer key ids.
5. Docs: README of e2e-webui, docs/stack-profiles.md pointer, decision drop, changelog drop.
