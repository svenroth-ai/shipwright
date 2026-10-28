# Mini-plan: E2 stack profile for the skill-backed app

1. Add `shared/profiles/skill-companion-app.json` (host, delivery, companion, data_folder carried as a comment-key convention `_skill_companion`, NOT top-level keys; dev_server on 127.0.0.1:3901 /api/health; pytest+Playwright; deploy null; plugin-shaped folder_structure).
2. NO schema change (operator decision, architecture review: glm revise / openai reject -> glm's trim). host/delivery/companion/data_folder are not added to `stack_profile.schema.json` because nothing reads them; the unit that first adds a reader adds the keys with tests. The profile validates against the unchanged schema.
3. Tests: `shared/tests/test_skill_companion_app_profile.py` (resolve, host/delivery/companion, dev_server block via the real `dev_server._get_services`, deploy/CI/CodeQL registries, scaffold folders); no schema-mutation tests (no schema change); `plugins/shipwright-test/tests/test_test_runner_skill_companion.py`.
4. Docs: `docs/stack-profiles.md` section incl. the per-phase table and a short Decision note; `docs/guide.md` profile row; project `step-7-scaffolding.md` scaffold paragraph.
5. Keep `chat-first-json` bundled; retiring the chat-first design path is E3.
6. Report in result.json whether FR-01.03 and FR-01.08 can leave scope_frs.
