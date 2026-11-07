Goal: A stack profile can name the folders that hold its tests, so a vite-hono project's tests are linked without a hand-written setting
Reason: Nested test folders (server/tests, client/e2e) were scanned by nothing, so every requirement read as untested and the merge gate asked for tests that exist
Reference: .shipwright/planning/iterate/2026-11-02-profile-declared-test-roots.md (GitHub issue #972, items 1 and 2)
