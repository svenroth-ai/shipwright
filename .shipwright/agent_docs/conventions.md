# Conventions — shipwright

## Linter / Formatter

- **Linter**: _none detected_
- **Formatter**: _none detected_
- **TypeScript strict**: no
- **.editorconfig**: _none_

## Project-specific rules

Python 3.11+ with uv as package manager. All scripts are invoked via uv run. Hooks resolve plugin paths via ${CLAUDE_PLUGIN_ROOT}. Config files written to target projects use the prefix shipwright_ (e.g. shipwright_run_config.json) and environment variables use SHIPWRIGHT_ (e.g. SHIPWRIGHT_SESSION_ID, SHIPWRIGHT_PLUGIN_ROOT). Commits follow Conventional Commits with the plugin name as scope (e.g. fix(adopt): ..., feat(security): ...). Branches for self-monorepo work follow iterate/<short-kebab-description>. After any push that touches plugin-side files, scripts/update-marketplace.sh syncs the runtime plugin cache. Linting uses ruff; type-checking uses pyright; tests use pytest. The canonical user-facing documentation is docs/guide.md; the canonical hook + pipeline reference is docs/hooks-and-pipeline.md. CLAUDE.md captures operational rules; generated agent_docs link back rather than duplicating these sources of truth.

## Commit messages

- Use Conventional Commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`, `chore:`
- Scopes should reflect module boundaries (e.g., `feat(auth): ...`)

## Files

- Keep files under 300 lines; split larger modules.
- Tests live alongside implementation with `.test.*` / `_test.*` suffix OR in a `tests/` directory — whichever is consistent with the rest of the codebase.

## Learnings

- **Always quote `uv run <placeholder>` path arguments in shell snippets.** Any documented or installed shell command of the shape `uv run ${CLAUDE_PLUGIN_ROOT}/...`, `uv run {plugin_root}/...`, `uv run {shared_root}/...`, etc. must wrap the path in double quotes: `uv run "${CLAUDE_PLUGIN_ROOT}/..."`. Without quoting, target projects on paths containing spaces (OneDrive-synced "AI Backup - Documents", Windows usernames with spaces, paths under "Program Files") get word-split by the shell and uv exits non-zero. For the suggest_iterate UserPromptSubmit hook this exit non-zero blocks every user prompt. Same risk class for the documentation snippets the agent renders into shell at runtime. Add `--no-project` to `uv run` for hook commands so a corrupt target-project `.venv` cannot stall uv on resolution. Out of scope for this rule (today): `plugins/*/hooks/hooks.json` between-phase commands — different blast radius (only fail when the *plugin install path* contains spaces, which today only happens on Windows usernames with spaces). See ADR-020.
- **Hook-installer-style code that detects "already-present" must also upgrade legacy forms in place, not just refuse to add a duplicate.** Recognition without rewrite leaves an already-broken installation broken on re-run. Tests should assert the canonical literal after run, not just absence of duplicates. When BOTH the carrier shape (Shape A vs Shape B per ADR-019) and the command literal can be wrong, the upgrade must fix both — recognizing one without rewriting the other still produces a broken hook. Surface the rewrite via an `upgraded: true` field in the return dict so callers/telemetry can observe that re-running adopt actually fixed something.
- **Drift-protection tests across two SSoTs use AST + source-position sort, not substring grep.** When one module hardcodes a list that mirrors logic in another module (e.g. `_SHIPWRIGHT_FRAMEWORK_VARS` vs `is_external_review_enabled`), a substring-based test only catches removal, not reordering or insertion. Parse the source-of-truth file via `ast.parse`, walk to extract the calls/keys, then sort by `(node.lineno, node.col_offset)` because `ast.walk` order is unspecified. Compare ordered list-vs-list with a clear failure message naming both sources. Reviewer caught this on iterate-2026-05-03-adopt-env-local-scaffold; the original test only asserted names appeared somewhere. See ADR-021.
- **`.env.local` is the single secrets surface; `.gitignore` enforcement is a hard-stop.** Anything writing to `.env.local` must first ensure `.gitignore` matches it. If enforcement fails (OS error, permission), abort the write — never stage secrets in a repo where the ignore rule could not be locked in. Implementations should return an explicit `{action: "skipped", reason: "gitignore_enforcement_failed"}` so the caller can surface a loud handoff message rather than half-completing. See ADR-021.
- **Producer/consumer round-trip is the only test that catches format drift.** Unit tests that probe each side against a stub representation of a serialized format pass even when the producer and consumer disagree on the format on disk. The 2026-05-03 env-iterate's BOM and inline-comment bugs both shipped past 47 unit tests + two external LLM reviews because no test fed real-producer-output through the consumer. Rule: every change touching a serialized format that another module reads must include a producer→file-on-disk→consumer round-trip assertion. The `touches_io_boundary` risk flag (file-pattern + keyword detection) gates this automatically — see `references/boundary-probes.md` and `references/round-trip-tests.md`. When the same parser/serializer logic exists in N places, add a parametrized test across all N as drift protection. See ADR-024.
- **Default permissive on missing-marker guardrails.** Push/lint guards that key off an opt-in marker file should exit 0 when the marker is absent — most projects run single-session and shouldn't be gated. The marker is the active signal; absence means "this rule does not apply here". Hard-fail on missing marker would punish the common case for the rare race. See ADR-026 (`check_session_role.py`). Edge cases (canonical/secondary, env-override) only apply when the marker is present.
- **Idempotent writes preserve audit-trail fields.** When re-writing a marker/state file with a "no-op when key fields match" rule, preserve original timestamps and identity fields (`set_at`, `set_by_session_id`, etc.) — overwriting them on every call destroys the provenance the file was supposed to capture. Test the idempotent path explicitly (assert mtime + bytes unchanged on second call). See `session_role.write_role()` and ADR-026.
- **"Are you confident?" is unfalsifiable; the asymptote heuristic replaces it.** Self-attestation of confidence in a diff is uncorrelated with bug presence — the same brain that wrote the bug is being asked if it sees the bug. The stopping rule is empirical: probe until the marginal probe returns no finding. If a probe finds a bug, run one more — the base rate of "this was the only bug class" is empirically low. Encoded as Step 7.5 (Confidence Calibration) in the iterate skill, mandatory at medium+, Safety-enforced at small with `touches_io_boundary`. Probes themselves can have bugs — when scoping a probe to a section of a doc, anchor on the section heading first, not the keyword (a keyword-only match in Probe 3 of this iterate hit the Override Classes table instead of the Phase Matrix; SKILL.md was correct, the probe wasn't). See ADR-025 and `plugins/shipwright-iterate/skills/iterate/references/confidence-anti-patterns.md`.
- **`${CLAUDE_PLUGIN_ROOT}` is plugin-context-only.** Any hook command that references this variable MUST be registered in a plugin's own `hooks/hooks.json` — Claude Code does not expand it in project-level `.claude/settings.json` and now surfaces an explicit "hook is not associated with a plugin" error. Distribution-channel choice is structurally constrained, not stylistic: project-level installation works only with `${CLAUDE_PROJECT_DIR}`, which scopes to the user's repo (so any cross-repo dependency the script imports — e.g. `suggest_iterate.py` → `classify_intent.py` via path arithmetic — must also live in the repo, not in a Shipwright cache shared across projects). For framework-owned hooks that need cross-repo scripts, the only viable channel is plugin-hooks.json registration. See ADR-030.
- **Subprocess tests on Windows must forward `SystemDrive`/`LOCALAPPDATA`/`APPDATA` alongside `SystemRoot`/`USERPROFILE`/`HOME`.** A test that runs `uv run` in a tightly-controlled env without `SystemDrive` causes uv to compute its data-dir path as a literal `%SystemDrive%/ProgramData/Microsoft/Windows/Caches/...` directory under `cwd` — gitignore the pattern as belt+suspenders. Surfaced empirically by `test_round_trip_*` in `plugins/shipwright-iterate/tests/test_hooks_json_registration.py` during iterate-20260505-plugin-hook-registration.
- **Pre-push test gates that depend on the marketplace cache must skip pre-push, not fail.** When a test asserts properties of `~/.claude/plugins/cache/shipwright/...`, the cache content is determined by `git push && bash scripts/update-marketplace.sh` — pre-push the cache is by-definition stale. The right pattern is `pytest.mark.skipif` keyed on a content-equality probe between source and cache (`_cache_hooks_json_in_sync_with_source()` in `test_hooks_json_registration.py`), so the test runs hard post-sync and silent pre-sync. Hard-failing pre-push would block F0 of every iterate that touches a plugin file. See ADR-030.
- **Markdown is also a producer/consumer boundary.** The env-iterate's round-trip pattern (ADR-024) applies one-for-one to spec.md and similar markdown the framework writes for its own consumption. Two FR-table formats co-exist in the wild — 3-data-column Greenfield (`| ID | Text | Priority |`) from `/shipwright-project` and 5-data-column Adopt (`| ID | Name | Priority | Description | Source |`) from `/shipwright-adopt` — with the FR's semantic body in different columns (col 2 vs col 4). Parsers must accept both and select `body = group(4) or group(2)`; tests must run real-spec round-trip + parametrized drift protection across every duplicated parser. Of the 8 boundary-probe categories, 3 are N/A for machine-written markdown (POSIX export prefix, inline `# comment`, quoted `#`) — justify inline. Adopt specs may also append further columns past Source (e.g. an inference Confidence score); the FR-table parser tolerates any number of trailing columns and `body` stays `group(4)`. See ADR-031 + ADR-048.
- **End-to-End Verification: spec-only authorship counts as no test.** The Phase Matrix's "always" at medium+ for E2E means `author AND run`, not `author OR run`. F0.5 is the single normative gate; Steps 9 and 11a/11b produce early signal but are not authoritative. Four fail-closed conditions enforced both at production time (`shared/scripts/surface_verification.py`) and post-commit (`check_surface_verification` in `iterate_checks.py`): (1) missing `surface_verification` block at medium+, (2) `tests_run == 0` (greedy-filter trap — Playwright `--grep` mismatch silently exits 0), (3) `exit_code != 0` after 3-retry cap, (4) `surface == "none"` without justification. **Backend-affects-Frontend rule:** API/store/SSE/WS diffs trigger `surface = web` even when no `client/**` file changed — the matrix's "always at medium+" subsumes file-path detection. Surfaceless iterates use `surface = none` with a justification recorded in the iterate ADR. The 2026-04 webui regression that motivated this rule shipped because backend-only diffs dodged file-path-gated browser verify. ACs at medium+ MUST be assertion-shaped, not story-shaped, so the runner can verify them mechanically.
- **Marker scanners need comment-context recognition, not "match anywhere on line".** A regex like `\b(TODO|FIXME)\b:?` self-matches its own marker tuple (`_MARKERS = ("TODO", "FIXME", ...)`), regex literal definitions, rendered output strings, and Python docstrings. The structurally correct fix is a per-line predicate that requires the marker to appear after a recognised comment opener (`#`, `//`, `/*`, `<!--`), or as a JSDoc continuation (`^\s*\*\s*` — anchored at line start to reject inline multiplication `a * TODO`), or as a markdown list bullet (`^\s*-\s+` — single-dash, rejects horizontal rules `---`). Tightening the regex alone (e.g. requiring the colon) is cosmetic and still matches tuple elements with quote suffix. Belt-and-suspenders: dynamic self-skip via `Path(__file__).resolve().relative_to(project_root)` with hardcoded fallback for tests under `tmp_path`. SQL/Lua/Haskell `--` is intentionally NOT in the allowlist when no `.sql`/`.lua`/`.hs` extension is in the scanner's source-suffix list. See ADR-041.
- **Claude Code hook schemas are per-event, not uniform.** The Stop and SubagentStop `hookSpecificOutput` schemas permit only `hookEventName` — `additionalContext` is valid only for SessionStart/Setup/UserPromptSubmit/UserPromptExpansion/PreToolUse/PostToolUse*/PostToolBatch. Emitting `additionalContext` on Stop fails the harness validator with "Hook JSON output validation failed — (root): Invalid input" and surfaced 35 errors per session before this fix. Diagnostics for events with restrictive `hookSpecificOutput` schemas (Stop, SubagentStop, SessionEnd) must route to stderr — Claude Code surfaces hook stderr to the user, so visibility is preserved without violating the schema. For SubagentStop **error** sites, use top-level `decision: "block"` + `reason` to halt the subagent — stderr alone would silently let the failed run be marked successful. Drift-protection: `shared/tests/test_hook_output_schema_compliance.py` discovers every hook in every `plugins/*/hooks/hooks.json`, runs each with a realistic stdin + seeded fixture + `CLAUDE_PLUGIN_ROOT`, and validates per-event schema. Empty `{}` stdin only caught 1/27 violations; realistic env caught all 27 — when testing hook scripts, replicate production env (cwd seed, plugin-root env), not just exit protocol. See ADR-042.

- **Orphan-file detection requires consumer-grep, not git history.** A file that has commits and looks alive may have zero callers. `git log -- path/to/file` shows the original author + later refactors, but the only authoritative "is this code reachable?" probe is `grep -r '<basename>' plugins/ shared/scripts/ docs/` (excluding the file itself). Iterate-20260510-adopt-ci-scaffolders found that `ci-nextjs.yml.template` (authored 2026-03-20 by `c3a6d2f`) and `claude-review.yml.template` (authored 2026-03-23 by `8aac61d`) were both zero-caller orphans — the original wiring intent was abandoned and only `security.yml.template` ever got scaffolded. The "intentional out-of-scope" comment in `plugins/shipwright-compliance/scripts/audit/group_a.py:19-21` ("requires the adopt-iterate to scaffold the workflow template first") is the canonical signal pattern for tracked-but-deferred follow-ups. When picking up such a follow-up: probe both the file and its expected callers; if a callsite-shaped function exists nowhere, the feature was never wired. See ADR-043.

- **PyYAML loses comments — drift tests on workflow files must require ABSENT, not "commented or absent".** GitHub Actions YAML often uses `# pull_request:` to communicate dormant intent. PyYAML's `safe_load` erases all comments, so a drift test cannot distinguish "commented out" from "absent" via the parsed structure. Make the contract testable with the parser by requiring `pull_request` and `push` to be absent from parsed `on:` triggers. Header-comment text can be asserted separately against the raw file string if needed, but mixing the two checks against the same parsed structure produces a false-positive class. External-review #O5 caught this in iterate-2026-05-10-adopt-ci-scaffolders. See ADR-043 + `shared/tests/test_ci_workflow_convention.py::TestCITemplatesDormantTriggers`.

- **Pytest `conftest.py` name collision across plugin dirs.** Two `tests/conftest.py` files (one per plugin) can't be loaded in a single pytest session — both get the module name `tests.conftest` and pluggy raises `ValueError: Plugin already registered under a different name`. Workarounds tried + outcome: (1) `--import-mode=importlib` — still fails because pluggy registers by basename before importlib resolves. (2) Running both files through `pytest <path1> <path2>` from repo root — fails. The working pattern: chain two separate pytest invocations via `bash -c "cd plugin1 && pytest tests/... && cd ../plugin2 && pytest tests/..."` so each gets its own session-scope. F0.5's surface_verification.py runner must accommodate this when verifying tests across multiple plugins. See `.shipwright/runs/iterate-2026-05-10-adopt-ci-scaffolders/runner.sh` for the canonical wrapper-script pattern.

- **Silent `pytest.skip` on missing binary/import paths must hard-fail in CI.** A `@pytest.mark.skipif(not shutil.which("X"), ...)` decorator OR `try: import X except: pytest.skip(...)` block silently degrades the test count without anyone noticing — both for missing-tooling cases (semgrep/gitleaks/trivy/npx/uv) AND cross-plugin sys.path-pollution cases (the `lib/`/`tools/` namespace collision is structural, every plugin defines its own). The fix: keep the local-dev skip but gate it with `if os.environ.get("CI", "").lower() in ("true", "1"): pytest.fail(<actionable install hint>)`. The hint must name a concrete remediation (`actions/setup-node@v4`, `astral-sh/setup-uv@v3`, plugin-session invocation). Canonical helper: `_ci_truthy() -> bool` (duplicated per file until AC-6 centralizes). Module-level `pytest.fail()` works in practice (raises `_pytest.outcomes.Failed` = collection error = non-zero exit) but is undocumented — pin via source-level regex (`test_silent_skip_ci_discipline.py`), not runtime. See ADR-044 + `references/test-hygiene` rules in `plugins/shipwright-iterate/skills/iterate/SKILL.md` Step 6.

- **Registry → disk mappings need BOTH directions of drift protection.** A registry like `TEMPLATE_BY_PROFILE: dict[str, str]` mapping profile names to template paths needs (a) forward — every value resolves to a real file (existing `test_ci_workflow_convention.py`), AND (b) reverse — every file matching the registry's namespace pattern (`ci-*.yml.template`) has a registry entry (new `test_ci_template_registry_completeness.py`). Without the reverse test, orphan files accumulate undetected — the ADR-043 zero-caller pattern repeats. Apply to any future SSoT registry. See iterate-2026-05-11-test-hygiene-and-skill-rules AC-4 + ADR-044.

- **F0.5 cli-surface `--runner` commands must pass `--color=no`.** `surface_verification.py`'s `parse_tests_run` extracts the executed-test count with `\b(\d+)\s+passed\b`. pytest under `uv run` can still emit ANSI color even with output captured (no TTY) — the escape `\x1b[1m` ends in `m` (a word char), so the colored summary `\x1b[1m7 passed` has no word boundary before the digit, the regex matches 0, and the gate false-fails with `EXIT_ZERO_TESTS` (exit 2) despite all tests passing. Append `--color=no` to every pytest/CLI runner command handed to `--runner`. The `--tests-run N` override also works but bypasses the empirical parse — prefer `--color=no` so the real count is verified. Surfaced empirically in iterate-2026-05-15-rtm-adopt-worktree-fix F0.5. See ADR-048.

- **Test-Update-Klausel: when an iterate changes test infrastructure (skip semantics, hygiene rules, conventions), the iterate skill's reference rules MUST be updated in the same diff.** Test fixes that don't codify the underlying rule re-introduce the same anti-pattern on the next iterate. Codified in SKILL.md Step 6. Drift-protection probe lives at `plugins/shipwright-iterate/tests/test_skill_step_6_rules_present.py` (anchors on Step 6 heading + named rule keys per ADR-021/ADR-025 pattern). See ADR-044.

- **`pytest.fail`-raising helpers should be annotated `NoReturn`.** When a helper unconditionally raises (`pytest.fail`/`pytest.skip` both raise), `return None` after the call is dead-but-defensive code. The dead-code idiom hides risk: a future refactor that adds a conditional path silently makes the return reachable and downstream `spec_path = write_spec(...)` etc. get skipped while the test still "passes". Use `from typing import NoReturn` + `def _import_or_fail_in_ci(...) -> NoReturn:` so pyright/mypy enforce the contract. Drop the `return  # unreachable` lines. See `shared/tests/test_setup_writes_canonical.py::_import_or_fail_in_ci` for the canonical pattern + ADR-044.

- **OneDrive-synced repos + uv hardlink mode = hook subprocess hell.** When the repo or `AppData\Local\uv\cache\` is under OneDrive (or any file-sync agent), uv's default hardlink install mode fails with `os error 396: The cloud operation cannot be performed on a file with incompatible hardlinks`. Every `uv run` from a hook then fails, blocking the entire session (PreToolUse/Stop hooks loop). Permanent fix: `[Environment]::SetEnvironmentVariable("UV_LINK_MODE", "copy", "User")` + restart Claude Code. Faster recovery once stuck: delete the broken plugin venv + `uv cache clean`. Mid-session there's no clean recovery from inside the agent — the auto-mode classifier blocks recursive `.venv` deletes without explicit per-call approval, so the user must run the PowerShell command in a separate window. Surfaced during iterate-2026-05-11-test-hygiene-and-skill-rules.

- **Cross-cutting Python helpers go under `shared/scripts/<name>.py`, NOT `shared/scripts/lib/<name>.py`.** The repo has a structural conflict at the `lib` namespace: `shared/scripts/lib/` is a regular package (has `__init__.py`), every `plugins/*/scripts/lib/` is a namespace package (no `__init__.py`). When a plugin test session imports its own `lib.X` first, `sys.modules['lib']` is pinned; subsequent `from lib.shared_helper import` from another test file in the same session fails with ModuleNotFoundError. Verified empirically in iterate-2026-05-11-test-hygiene-helper-and-self-review-wiring when test_aikido_client.py (alphabetically first) blocked test_oss_backend_smoke.py's `from lib.test_hygiene import`. **Rule:** any helper that must be importable from BOTH `shared/tests/` AND `plugins/*/tests/` must live OUTSIDE the `lib/` namespace. Existing examples that work: `from lib.ci_workflow import` (only used by shared/tests). New cross-cutting helpers: place at `shared/scripts/<helper>.py` and import as `from <helper> import`. See ADR-045 + test_hygiene.py as the canonical pattern.

- **AST + tokenize hybrid for source-pattern detection that respects comments.** `ast.parse` strips comments — fine for structural analysis but useless for suppression-marker semantics (`# foo: bar` on the line above an offending call). Pair `ast.walk` for the structural detection with `tokenize.tokenize` for comment-token line numbers. Suppression: walk upward from the offending line through CONTIGUOUS comment lines (`stripped.startswith('#')`), stop at the first non-comment, check if any line in that block carries the marker. Single-line N-1 check misses multi-line rationale blocks (operators write 3-4 line explanations); contiguous-block walking is the natural pattern. See `shared/scripts/test_hygiene.py::_line_is_suppressed`.

- **Static-probe scope topology, not line geometry.** When deciding "is the skip CI-gated?", do NOT use line proximity (`pytest.fail within ±N lines of pytest.skip`) — formatters can spread them arbitrarily; an unrelated upstream `pytest.fail` can falsely whitewash. Use AST scope topology instead: the skip's enclosing `FunctionDef` body must contain BOTH a `CI-guard If` (test is `is_ci()` / `not is_ci()`) AND a `pytest.fail` co-located with it (in the If's body, in the If's orelse, or as a sibling statement after the If). A scope with `pytest.skip` + bare `pytest.fail` and NO `If` is NOT accepted — that's just two bailouts, not CI semantics. Code-review HIGH-1 of ADR-045 caught the prior implementation's permissive fallback before merge.

- **Pre-backlog buffer keeps the WebUI task list curated.** Findings emitted by hooks/scans/audits should NOT land directly in `sdk-sessions.json` ExternalTask records. They flood the operator's view (same C1/W3 re-fires every session; same compliance finding persists across runs) and conflict on dedup-key shape (finding_code vs task_id). The triage pattern (ADR-046) absorbs the noise in a separate per-project `.shipwright/triage.jsonl` store with operator-driven `promote` as the bridge. **Rule for new producers** (security/CI/performance/F0.5/drift in Iterate 2): call `append_triage_item_idempotent(source=<x>, dedup_key=<stable code>, match_commit=<true for per-commit re-fire, false for cross-commit dedup>, window_seconds=<int for daily re-flag, None for indefinite>)`. Choose `match_commit` and `window_seconds` per the producer's semantics — Phase-Quality uses `match_commit=True, window=24h` so the daily re-flag fires until the operator promotes/dismisses; Compliance uses `match_commit=False, window=None` so a finding stays as ONE inbox item indefinitely until resolved.

- **Concurrency-correct idempotent append: dedup-scan + write under the same lock.** When a helper has a "skip if recent duplicate exists" rule, the scan and the append MUST run inside the same critical section. Otherwise two concurrent producers can both pass the dedup check and both append. The first version of `append_triage_item_idempotent` scanned BEFORE the lock — external code review (Gemini + OpenAI via OpenRouter) caught it before merge. Tested via `test_idempotent_concurrency_under_lock` (8 threads race, exactly 1 winner expected). See ADR-046 + `shared/scripts/triage.py:append_triage_item_idempotent`.

- **Cross-session dedup needs an explicit "no window" mode.** A default time-based window (e.g. 24h) silently mis-fires for producers whose findings persist across sessions for weeks/months. Compliance audit findings stay valid until resolved — re-emitting on day 2 would create N copies of the same finding. Support `window_seconds=None` for indefinite dedup against currently-`triage` items; document the choice per producer. See ADR-046 + Gemini HIGH finding in iterate-2026-05-11-triage-inbox-1a code review.

- **Gitignored test fixtures are absent in fresh worktrees/clones.** Fixture files whose names match a repo-wide gitignore pattern are untracked — e.g. `plugins/shipwright-adopt/tests/fixtures/nested-shipwright/webui/shipwright_run_config.json` is ignored by the `shipwright_*_config.json` rule. Such a file survives in a long-lived working copy but is NOT carried into a freshly-created `git worktree` (nor a fresh `git clone` / CI checkout). `test_nested_project_detector::test_detects_nested_shipwright_subproject` consequently fails in every iterate worktree until the fixture is re-hydrated (copy from the main repo, per the SKILL B1a re-hydration rule). Surfaced in iterate-2026-05-16-fix-adopt-review-config. Proper fix (out of scope there): force-track the fixture with `git add -f`, or rename it so the ignore rule misses it.

- **A triage `source` is not always a unique producer identity — an auto-resolve pass must scope by the dedup-key shape it owns.** `check_drift.py` and `artifact_sync.py` both emit `source="drift"`. The `auditResolved` pattern in `audit_detector.py` is safe only because `source="compliance"` has exactly one producer; a resolve pass keyed on `source` alone would cross-dismiss the other producer's open `triage` items. Scope the resolve to the key shape the producer owns — `check_drift` → keys ending `:timestamp`/`:content`; F0.5 → prefix `f0.5:{run_id}:{surface}:` (the surface segment matters: a re-run on a different surface must not retract a genuine failure from the original one). Companion rule: triage dedup keys built from filesystem paths must be canonicalized in the **producer** — `os.path.abspath` does NOT normalize Windows drive-letter case (`c:\` vs `C:\`), so `os.path.normcase(os.path.realpath(path))` is required; it must NOT be applied inside `triage.py::append_triage_item_idempotent`, which also dedups non-path keys (`A5.0`, `B7`, `E1`, `G2`) that must stay case-sensitive. See iterate-2026-05-16-fix-triage-dedup-resolve.

- **A load-bearing "always" step enforced only by prose gets skipped — convert it to a gate.** The iterate "Step 2: Spec Update (always)" was marked `always` in the Phase Matrix and reinforced with "skipping is NOT an option" prose, yet ~27 of 28 iterates never touched `spec.md` — whole subsystems landed with no FR. Prose cannot enforce; a gate can. The fix pattern: (a) a write-time gate — `record_event.py` exits 1 (nothing written) for a feature/change iterate event that records no FR and no justified `spec_impact=none`; (b) a verify-time gate — `check_spec_impact_recorded` fails F11 if the commit touched no `.shipwright/planning/**/spec.md`; (c) a detective backstop — Group D5 surfaces the historical backlog. The gate tolerates legacy events (no `spec_impact`) by falling through to a git-diff check, so it composes with un-migrated history rather than retroactively failing it. See iterate-2026-05-16-spec-impact-gate.

- **Bash hooks must resolve a Python interpreter — never hardcode `python3`.** On a default Windows 11 install `python3` resolves to the Microsoft Store App-Execution-Alias stub (`%LOCALAPPDATA%\Microsoft\WindowsApps\python3`): it prints "Python was not found" and exits non-zero **without running anything**. A hook doing `VAL=$(echo "$INPUT" | python3 -c ... 2>/dev/null || echo "")` then gets an empty value and exits 0 — a silent no-op. For the security hooks (`check_secrets.sh`, `check_file_size.sh`, `validate_command.sh`, `check_destructive_migration.sh`) this meant the control never fired on Windows: no secret was ever blocked. Fix: a `_resolve_python()` helper that probes `python3` → `python` → `py` and rejects any candidate failing `"$cand" -c "import sys"` (the Store stub fails that probe). Also pipe the extracted value through `tr -d '\r'` — Windows `python`'s `print()` emits CRLF and the trailing `\r` survives `$(...)` command substitution, corrupting `[ -f "$PATH" ]` and integer comparisons. The 6 hook subprocess tests passed the "allow" cases by accident (hook exits 0, which they expect) and failed only the "block" cases — an all-`exit 0` hook is the tell. See iterate-2026-05-18-fix-launch-blocker-tests.

- **Test fixtures must not use bare migrated-path words as content markers.** `test_artifact_path_canon.py::test_no_legacy_artifact_paths` scans every `.py` file with `text-regex` patterns for legacy pre-`.shipwright/` path references. A spec-body marker like `"## FR-1: planning\n"` is flagged because the `\n` supplies the trailing backslash the `(?<![\w/.\\])planning\\` pattern needs; a bare quoted `"planning"` assertion literal is flagged too. `pathlib` joins (`tmp / ".shipwright" / "planning" / "01-x"`) are SAFE — the pattern carries a `(?<!/ )` lookbehind that excludes `/ "planning"`. Rule: in test fixtures, use a neutral marker word (`splitlevel`, `canonical`, `splitspec`) for spec/artifact body content and assertions — never the literal `planning` / `designs`. The meta-test is a leaf in `shared/tests/`, so F0's full-suite run is what catches it; a `-k`-scoped run will not. Surfaced in iterate-2026-05-18-phase-quality-check-fixes F0.

- **`check_secrets.sh` flags any `secret`/`password`/`token`-named variable assigned a string literal — test files are NOT exempt.** The PostToolUse hook's heuristic (`(password|secret|api_key|access_token|auth_token)\s*[=:]\s*['"][^'"]{8,}['"]`) plus its `SKIP_PATTERNS` exempt only `fixtures/` directories and `.env.example`-style files — never `test_*.py` files. A test fixture written as `_LEAKED_SECRET = "<value>"` (variable name carrying a trigger word, RHS a ≥8-char literal) soft-blocks the write. Rule: in test fixtures, name secret-ish variables WITHOUT a trigger word (`_SENTINEL`, not `_LEAKED_SECRET`) and use a low-entropy, non-credential-shaped sentinel value — no `ghp_` / `sk-` / `AKIA` prefix, no long hex/base64 run (those trip the prefix + high-entropy patterns separately). Surfaced in iterate-2026-05-19-github-triage-importer.

- **A Learnings entry that quotes a legacy-path pattern trips the path-canon lint it describes — and F0 runs before F3a, so the trip lands undetected.** `test_no_legacy_artifact_paths` text-scans `.md` files too; a learning quoting a migrated dir-name followed by a backslash (an escaped-newline literal, or a regex literal) matches the legacy-path pattern. `conventions.md` was missing from `ALLOWLIST['planning'|'designs'|'agent_docs']` in `artifact_migrations.py` — present only in the `compliance` block, while its sibling agent_docs `architecture.md` / `decision_log.md` were allowlisted everywhere. Because F3a (Reflection) appends to `conventions.md` AFTER F0, a self-referential learning escapes that run's F0 and only fails the NEXT iterate's F0. Fixed by adding `conventions.md` to all four allowlist blocks. Surfaced in iterate-2026-05-19-github-triage-importer.

- **An auto-resolving triage producer MUST distinguish a failed fetch from an empty one.** A producer that imports findings and then dismisses stale items (the ADR-052 auto-resolve pattern) computes "stale" as "open item whose dedup key left the current finding set". If a data-source fetch FAILS and is coerced to an empty list, every previously-imported item from that source is mass-dismissed as falsely "resolved". The fix: fetchers return `None` on failure and a list (possibly empty) on success; the resolve pass is scoped to only the key-prefixes whose fetch returned non-`None`. `shared/scripts/github_api.py` returns `None` on any `gh` failure for exactly this reason, and `github_triage.import_findings` builds `resolvable_prefixes` only from succeeded fetches. Origin: iterate-2026-05-19-github-triage-importer.

---

## Imported from `CONTRIBUTING.md`

_Copied verbatim by /shipwright-adopt during onboarding. Edit in place; future adopt re-runs back this file up to `.shipwright/adopt/backups/`._

# Contributing to Shipwright

Thanks for your interest in contributing to Shipwright! This document explains how to set up your environment, the rules for code contributions, and our trust model.

> **Early Access Beta:** Shipwright is currently in Early Access. Breaking changes are possible. Please open an issue before investing significant time in a large contribution.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Before You Contribute](#before-you-contribute)
- [Development Setup](#development-setup)
- [Running Tests Locally](#running-tests-locally)
- [Running Security Scans Locally](#running-security-scans-locally)
- [Pull Request Process](#pull-request-process)
- [Commit Guidelines](#commit-guidelines)
- [Graduated Trust Model](#graduated-trust-model)
- [High-Sensitivity Areas](#high-sensitivity-areas)
- [Reporting Security Issues](#reporting-security-issues)

---

## Code of Conduct

Be kind. Be patient. Assume good intent. Critique ideas, not people. If a discussion turns hostile, take a break. The maintainer reserves the right to close issues and block users who violate this.

## Before You Contribute

**Small changes (typos, docs, tests for existing code):** Open a PR directly.

**Bug fixes:** Open an issue first or reference an existing one. This helps track context and avoid duplicate work.

**New features, refactors, or changes to skills/hooks/agents:** **Open an issue first** to discuss the approach. Shipwright has strong opinions about its architecture, and we want to save you effort by aligning upfront. PRs that modify core behavior without prior discussion may be closed.

**Changes to security scanning, prompt injection detection, or the orchestrator:** These are high-sensitivity areas. See [High-Sensitivity Areas](#high-sensitivity-areas).

## Development Setup

Follow **[docs/guide.md §2 — Prerequisites and Installation](docs/guide.md#2-prerequisites-and-installation)** for the canonical setup. It covers required tools (Claude Code, Python 3.11+, uv, Git), optional tools (`gh`, Node.js 22.x, Supabase CLI), and platform-specific notes for Windows, macOS, Linux, and WSL.

Short version for contributors who already have the base setup:

```bash
git clone https://github.com/svenroth-ai/shipwright.git ~/shipwright
cd ~/shipwright && uv sync
```

### Additional requirements for contributors

Working on a specific plugin additionally requires that plugin's own dependencies:

```bash
cd plugins/shipwright-build && uv sync
# or any other plugin under plugins/
```

Working on the **WebUI** is done in the separate
[`shipwright-webui`](https://github.com/svenroth-ai/shipwright-webui) repository
— not in this repo. See its own `CONTRIBUTING.md` for setup.

Working on **`shipwright-security`** additionally requires the OSS scanners (see [Running Security Scans Locally](#running-security-scans-locally)).

Working on **`shipwright-deploy`** additionally requires the Jelastic setup described in [docs/setup-guide-jelastic-infomaniak.md](docs/setup-guide-jelastic-infomaniak.md).

## Running Tests Locally

### Python tests

```bash
# Run all tests for one plugin
cd plugins/shipwright-security
uv run pytest tests/ -v

# Run the integration test suite
cd /path/to/shipwright
uv run pytest integration-tests/ -v
```

### Linting

```bash
# Python
uv run ruff check .

# Type-checking
uv run pyright
```

(WebUI test/lint commands live in the separate
[`shipwright-webui`](https://github.com/svenroth-ai/shipwright-webui) repo.)

## Running Security Scans Locally

Shipwright uses its own `shipwright-security` plugin to scan every contribution. You can (and should) run the same scans locally before pushing:

### Install OSS scanners (one-time)

```bash
# macOS
brew install semgrep trivy gitleaks

# Linux
pip install semgrep
# trivy: https://aquasecurity.github.io/trivy-repo/deb/
# gitleaks: https://github.com/gitleaks/gitleaks/releases

# Windows
pip install semgrep
winget install AquaSecurity.Trivy
winget install Gitleaks.Gitleaks
```

### Run the scans

```bash
# Semgrep + Trivy + Gitleaks
uv run plugins/shipwright-security/scripts/tools/scan.py \
  --path . --output /tmp/findings.json

# Shipwright Prompt Injection Scanner (custom)
uv run plugins/shipwright-security/scripts/tools/prompt_injection_scan.py \
  --full --path . --output /tmp/prompt_risks.json

# Combined Markdown report
uv run plugins/shipwright-security/scripts/tools/generate_security_report.py \
  --input /tmp/findings.json \
  --prompt-risks /tmp/prompt_risks.json \
  --output /tmp/security_report.md
```

Fix anything flagged as `critical` or `high` before submitting your PR. `medium` and `low` findings are reviewed during merge.

## Pull Request Process

1. Fork the repository and create a feature branch from `main`:
   ```bash
   git checkout -b fix/descriptive-name
   ```
2. Make your changes with clear, atomic commits (see [Commit Guidelines](#commit-guidelines)).
3. Add or update tests for any code changes.
4. Run tests and security scans locally.
5. Push to your fork and open a PR against `main`.
6. Fill out the PR template completely — the checklist is there for a reason.
7. Wait for automated checks (CI, security scan) to complete.
8. Address review comments and iterate.

**Automated checks your PR must pass:**
- Unit tests (Python + TypeScript)
- Type checks (pyright, tsc)
- Linting (ruff, oxlint)
- `shipwright-security` scan (Semgrep + Trivy + Gitleaks + Prompt Injection Scanner)
- CodeQL analysis

## Commit Guidelines

### Conventional Commits

All commits must follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Types:** `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`, `perf`, `ci`, `build`

**Examples:**
```
feat(shipwright-build): add retry loop for flaky tests
fix(security): resolve false-positive in prompt injection scanner
docs(contributing): explain graduated trust model
test(security): add fixture for typosquatting detection
```

### DCO Sign-off

All commits must be signed off with the [Developer Certificate of Origin](https://developercertificate.org/). Add the `-s` flag to your commit:

```bash
git commit -s -m "feat(scope): your message"
```

This adds a `Signed-off-by:` line confirming you have the right to contribute the code.

### Signed Commits (GPG/SSH)

Signing commits with GPG or SSH keys is **strongly encouraged**. For the main branch, signed commits will eventually become required.

## Graduated Trust Model

Shipwright uses a graduated trust model to balance openness with security. Different levels of access unlock different types of contributions:

### Level 1 — First-time contributor

**You can contribute:**
- Typos and grammar in docs
- Clarifications in comments
- Tests for existing code
- Examples in `references/` folders
- Bug reports and reproduction cases

**You cannot yet contribute:**
- Changes to skills, hooks, or agents
- New scripts or refactors of existing ones
- New dependencies
- CI/workflow changes

### Level 2 — Established contributor

After 3+ merged PRs with no security concerns:

**Additionally, you can contribute:**
- Bug fixes in scripts (`plugins/*/scripts/`)
- New test fixtures
- Documentation expansions
- Performance improvements with benchmarks

**Still require pre-discussion:**
- Changes to skills, hooks, or agents (must have an issue first)
- New dependencies (must be justified in an issue)

### Level 3 — Trusted contributor

By invitation only, for contributors who have demonstrated consistent quality and alignment with the project's direction.

**Additionally, you can contribute:**
- New skills, hooks, or agents (after design discussion)
- Architecture changes with maintainer approval
- Direct reviews from the maintainer

There is no formal promotion process — the maintainer simply starts treating your PRs with less scrutiny once you've proven yourself.

## High-Sensitivity Areas

These parts of the codebase require extra care and will be reviewed more strictly:

| Path | Why |
|------|-----|
| `plugins/*/hooks/` | Hooks run shell commands — malicious changes could compromise any user's machine |
| `plugins/*/skills/` | Skill definitions are Claude instructions — prompt injection risks |
| `plugins/*/agents/` | Agent definitions share risks with skills |
| `plugins/shipwright-security/` | The security scanner itself — must remain trustworthy |
| `plugins/shipwright-run/` | The orchestrator controls the entire pipeline |
| `.github/workflows/` | CI/CD — could be abused to leak secrets or compromise releases |
| `shared/` | Shared code affects every plugin |

**Rules for high-sensitivity changes:**
- Must have a prior GitHub issue with design discussion
- Must be reviewed by the maintainer (no auto-merge)
- Must include tests covering the security-relevant behavior
- Cannot introduce new external dependencies without justification
- Cannot add shell commands, `eval()`, `exec()`, or similar dynamic execution

## Reporting Security Issues

**Do not file public issues for security vulnerabilities.** See [SECURITY.md](SECURITY.md) for the disclosure process.

---

Thanks for contributing! If anything in this guide is unclear, please open an issue with the `docs` label.

## Convention Updates

- **ADR-017** (2026-05-02): Repo cleanup post self-adoption: webui drift, legacy plans, FR populate

- **ADR-018** (2026-05-02): Adopt plugin: drift detection, test-fixture filter, compliance fallback fix

- **ADR-019** (2026-05-02): Hook installer writes canonical matcher-group shape

- **ADR-020** (2026-05-03): Quote uv-run path placeholders + upgrade legacy hook entries (Shape + command) in place

- **ADR-021** (2026-05-03): Adopt scaffolds .env.local with profile + framework keys (Layer-3 SSoT)

- **ADR-022** (2026-05-03): Quote ${CLAUDE_PLUGIN_ROOT} in plugins/*/hooks/hooks.json

- **ADR-023** (2026-05-03): Detect Git-Bash MSYS path-mangling in changelog drop bullets

- **ADR-026** (2026-05-03): Multi-Session Discipline — session-role marker + push guardrail (campaign iterate-skill-hardening Sub-Iterate C)

- **ADR-030** (2026-05-05): suggest_iterate hook is plugin-registered, not project-installed (retire hook_installer)

- **ADR-031** (2026-05-05): FR-table parser accepts 5-col adopt format + drift protection

- **ADR-037** (2026-05-06): F0.5 End-to-End Verification Gate (surface taxonomy + schema-enforced evidence)

- **ADR-038** (2026-05-06): F0.5 empirical-test backfill: drift-schutz + real subprocess probes + CLI audit chain

- **ADR-041** (2026-05-09): known-issues scanner requires comment context; remove dead save_session_config

- **ADR-042** (2026-05-10): Stop and SubagentStop hooks emit schema-compliant stdout

- **ADR-043** (2026-05-11): Adopt scaffolds profile-aware CI + Claude-Review workflows with cross-platform OS matrix default

- **ADR-049** (2026-05-16): Unconditional worktree isolation for /shipwright-iterate

- **ADR-050** (2026-05-16): Worktree-aware event-log resolution
