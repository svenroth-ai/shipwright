# Constitution enforcement register

> GENERATED from `shared/config/conventions.json` (section `constitution`) by
> `shared/scripts/tools/constitution_register.py --write`. Edit the JSON, never this file.
> It says, per rule of `shared/constitution.md`, how the rule is enforced. A rule that needs judgement
> is recorded as such; this register never turns judgement into a gate and carries no coverage number.

## pre-phase (4)

| id | enforcement | mechanism | note |
|---|---|---|---|
| `think-before-coding` | prompt-only (judgement) | - | Drift test only. |
| `simplicity-first` | prompt-only (judgement) | - |  |
| `surgical-changes` | prompt-only (judgement) | - |  |
| `goal-driven-execution` | prompt-only (judgement) | - | Pre-build AC record (ac_decision.py) covers part of this in iterate; the rule itself needs judgement. |

## always (24)

| id | enforcement | mechanism | note |
|---|---|---|---|
| `tests-before-commit` | prompt-only (mechanisable) | - | Iterate F0 runs the suite; no commit-time gate. |
| `down-sql-rollback` | prompt-only (mechanisable) | - | A commit-time check that every up.sql has a down.sql is possible. |
| `apply-migrations-before-tests` | prompt-only (mechanisable) | - |  |
| `conventional-commits` | prompt-only (mechanisable) | - | A commit-msg hook could check the prefix. |
| `parameterized-queries` | prompt-only (judgement) | - |  |
| `validate-at-boundaries` | prompt-only (judgement) | - |  |
| `new-commit-after-hook-fail` | prompt-only (mechanisable) | - |  |
| `self-review-before-commit` | validator | `shared/scripts/tools/verifiers/review_record_check.py` | Iterate only; checked at F11 after the commit, build and run are ungated. |
| `review-in-stages` | validator | `shared/scripts/tools/verifiers/review_record_check.py` | Iterate only; F11 checks the stage order and the code-review floor after the commit. |
| `browser-verify-frontend` | prompt-only (mechanisable) | - |  |
| `log-deviations` | prompt-only (judgement) | - |  |
| `compliance-after-phase` | prompt-only (mechanisable) | - | The Stop audit hook is diagnostic and never blocks; the per-phase update is the orchestrator calling update_compliance.py (run pipeline only). |
| `file-size-caps` | hook | `shared/scripts/hooks/check_file_size.py`<br>`shared/scripts/hooks/bloat_gate_on_stop.py`<br>`scripts/hooks/pre-commit`<br>`shared/scripts/lib/anti_ratchet.py` | check_file_size.py is advisory; the hard block is the pre-commit anti-ratchet on allowlisted entries. |
| `ac-at-falsifying-layer` | prompt-only (mechanisable) | - | Parts are mechanisable (a criterion with no test); which layer can falsify it needs judgement. The drift test test_constitution_ac_layer_rule_drift.py only pins the wording. |
| `fix-code-not-test` | prompt-only (judgement) | - |  |
| `never-weaken-rls` | prompt-only (judgement) | - |  |
| `service-role-setup-only` | prompt-only (mechanisable) | - |  |
| `integration-localhost-only` | prompt-only (mechanisable) | - |  |
| `diagnose-before-skipping` | prompt-only (judgement) | - |  |
| `generate-missing-prerequisites` | prompt-only (judgement) | - |  |
| `verify-after-edits` | prompt-only (mechanisable) | - |  |
| `reread-in-long-sessions` | prompt-only (judgement) | - |  |
| `state-truncation` | prompt-only (judgement) | - |  |
| `read-authoritative-state` | prompt-only (judgement) | - |  |

## ask-first (10)

| id | enforcement | mechanism | note |
|---|---|---|---|
| `ask-destructive-db` | hook | `plugins/shipwright-build/scripts/hooks/check_destructive_migration.sh` | PostToolUse reminder on Write/Edit of migration-path .sql (DROP TABLE/COLUMN, ALTER TYPE, TRUNCATE, DELETE without WHERE): the file is already written; SQL run through Bash is not covered; fails open without Python. |
| `ask-mixed-migration` | prompt-only (mechanisable) | - |  |
| `ask-prod-deploy` | validator | `plugins/shipwright-deploy/scripts/lib/release.py` | release.py refuses target prod without confirm_prod; other deploy paths are not gated. |
| `ask-rollback` | prompt-only (judgement) | - |  |
| `ask-skip-test-layer` | validator | `plugins/shipwright-run/scripts/lib/phase_validators_late.py` | Run pipeline only; severity is ask, not a stop; a pgTAP skip is not checked for a reason. |
| `ask-migration-apply-failure` | prompt-only (judgement) | - |  |
| `ask-override-gates` | validator | `plugins/shipwright-run/scripts/lib/orchestrator_pkg/cli_update_step.py`<br>`plugins/shipwright-run/scripts/lib/orchestrator_pkg/phase_gate.py`<br>`plugins/shipwright-run/scripts/lib/orchestrator_pkg/validation_record.py` | Force needs a non-blank reason; only guided or autonomous runs may override. |
| `ask-profile-change` | prompt-only (judgement) | - |  |
| `ask-after-3-failed-fixes` | prompt-only (judgement) | - |  |
| `ask-plain-language` | prompt-only (judgement) | - |  |

## never (16)

| id | enforcement | mechanism | note |
|---|---|---|---|
| `never-recursive-delete-root` | hook | `plugins/shipwright-build/scripts/hooks/validate_command.sh` | Matches the literal form rm -rf followed by / ~ or $HOME only; other flag spellings and orders pass, and any absolute path is over-blocked. The copy under shared/scripts/hooks is registered nowhere. |
| `never-force-push-main` | hook | `plugins/shipwright-build/scripts/hooks/force_push_guard.py`<br>`plugins/shipwright-build/scripts/hooks/validate_command.sh` |  |
| `never-reset-hard` | prompt-only (mechanisable) | - | No hook found that blocks it. |
| `never-no-verify` | prompt-only (mechanisable) | - | The pre-commit hook exists, but nothing stops bypassing it. |
| `never-drop-database` | hook | `plugins/shipwright-build/scripts/hooks/validate_command.sh` | Reads Bash commands only; the statement inside a .sql file run by a tool is not seen. |
| `never-skip-or-weaken-tests` | prompt-only (judgement) | - |  |
| `never-yagni` | prompt-only (judgement) | - |  |
| `never-hardcode-secrets` | hook | `shared/scripts/hooks/check_secrets.sh` | PostToolUse on Write/Edit (file already written); skips fixtures; pattern-based; fails open without Python. |
| `never-commit-env` | prompt-only (mechanisable) | - |  |
| `never-sensitive-detail` | prompt-only (judgement) | - |  |
| `never-triage-own-work` | prompt-only (judgement) | - |  |
| `never-bare-python-stdin` | hook | `plugins/shipwright-iterate/scripts/hooks/bare_python_stdin_guard.py` | Bash tool only; the PowerShell tool is not guarded. |
| `never-blind-retry` | prompt-only (judgement) | - |  |
| `never-amend-blocked-commit` | prompt-only (mechanisable) | - |  |
| `never-loop-over-3` | prompt-only (judgement) | - |  |
| `never-claim-all-pass` | prompt-only (judgement) | - |  |

## escalation (6)

| id | enforcement | mechanism | note |
|---|---|---|---|
| `esc-two-same-root` | prompt-only (judgement) | - |  |
| `esc-three-failed` | prompt-only (judgement) | - |  |
| `esc-e2e-groups` | prompt-only (judgement) | - |  |
| `esc-missing-dependency` | prompt-only (judgement) | - |  |
| `esc-prod-deploy` | validator | `plugins/shipwright-deploy/scripts/lib/release.py` | Same gate as ask-prod-deploy. |
| `esc-destructive-sql` | hook | `plugins/shipwright-build/scripts/hooks/check_destructive_migration.sh` | PostToolUse reminder on Write/Edit of migration-path .sql (DROP TABLE/COLUMN, ALTER TYPE, TRUNCATE, DELETE without WHERE): the file is already written; SQL run through Bash is not covered; fails open without Python. |

## test-layer (5)

| id | enforcement | mechanism | note |
|---|---|---|---|
| `layer-unit` | validator | `plugins/shipwright-run/scripts/lib/phase_validators_late.py` | Run pipeline only; severity is ask. |
| `layer-integration` | validator | `plugins/shipwright-run/scripts/lib/phase_validators_late.py` | Checks the final outcome only; the autofix retries are prose; run pipeline only. |
| `layer-pgtap` | validator | `plugins/shipwright-run/scripts/lib/phase_validators_late.py` | Checks the final outcome only; the autofix retries and a pgTAP skip reason are not checked; run pipeline only. |
| `layer-smoke` | validator | `plugins/shipwright-run/scripts/lib/phase_validators_late.py` | Run pipeline only; severity is ask. |
| `layer-e2e` | validator | `plugins/shipwright-run/scripts/lib/phase_validators_late.py` | Run pipeline only; severity is ask. |

## question-discipline (2)

| id | enforcement | mechanism | note |
|---|---|---|---|
| `question-stop-after-ask` | prompt-only (mechanisable) | - |  |
| `question-use-askuserquestion` | prompt-only (mechanisable) | - |  |

