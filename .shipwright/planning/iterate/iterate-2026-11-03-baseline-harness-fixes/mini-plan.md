# Mini-plan: baseline harness fixes
1. board-ui.ts: `listRow` (visible `[data-k]` by key) and `visibleText`; use them in checks-board.ts and openThread.
2. checks-static.ts: B31 hosts anywhere in backend/services/; B30 ignores the brief's mandated 409 sentence.
3. checks-runs.ts: `plain` joins string lists (no JSON escaping of quotes).
4. checks-board.ts: B37 case-insensitive labels; B39 element handle. tour-baseline.ts: case-insensitive marker, platform for Expired.
5. tests/recheck.spec.ts + `recheck` project/script + README; unit tests in tests/unit/baseline-harness-fixes.spec.ts.
