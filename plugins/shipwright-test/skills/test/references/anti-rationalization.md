# Anti-Rationalization

Before accepting test results as sufficient, resist these justifications:

| Rationalization | Reality |
|---|---|
| "Tests pass, so the code is correct" | Tests are necessary but insufficient — they can't catch what they don't cover |
| "E2E tests are flaky, ignore failures" | Flaky tests hide real regressions. Fix the flakiness or investigate each failure |
| "We'll add more tests later" | Test debt compounds faster than code debt. Cover it now |
| "Manual testing is enough" | Manual testing doesn't run on every commit. Automated tests do |
| "100% coverage means no bugs" | Coverage measures execution, not correctness. A test that asserts nothing has coverage |
