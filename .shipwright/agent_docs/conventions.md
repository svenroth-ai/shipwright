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

- **The `check_security_scan` PreToolUse:Bash deploy-gate substring-matches its trigger words inside *argument prose*, not just argv[0].** `plugins/shipwright-compliance/scripts/hooks/check_security_scan.py` fires when any of `["deploy","jelastic","vercel","fly deploy","railway up"]` appears anywhere in `command.lower()`. On iterate-2026-06-10-status-projection the F0.5 `surface_verification.py --justification "…no status.json is produced in any deployed/UI flow…"` was soft-blocked ("24 unresolved findings exceed threshold 0") purely because the justification *prose* contained "deployed" — the 24 RTM findings were pre-existing and unrelated. Workaround: keep deploy-family words out of non-deploy command strings (reworded to "runtime/UI flow"). Real fix (follow-up, not S2 scope): the matcher should key off the resolved executable / a deploy-intent flag, not a substring scan of argument values. Same risk class for any agent-rendered shell that quotes user prose into a flag value.
- **Tune heuristic classifiers against a harvested real-input corpus, not synthetic guards.** When adjusting keyword/heuristic classification (scope vocabulary, risk patterns), harvest the real inputs from session transcripts (`--message` args + recorded outputs), hand-join them to the runs' ground truth (F5c finals), and pin them as a golden fixture with a hard-numbers improvement metric (here: under-classification 18→11, over 1→0 on 26 verified rows) — synthetic test prompts only enshrine the designer's intuition, and the corpus immediately falsified two "obvious" choices: naive `\b` word boundaries silently break filename-embedded keywords (`update_build_dashboard.py` — `_` is a `\w` char, no boundary) and real plurals (`Workflows`); the corpus-validated middle ground is alphanumeric lookarounds (underscore = separator) + an optional `s`/`es` suffix. Keep the fixture rows' provenance (date + join evidence) in the fixture itself, and keep the old baseline honest with a test that recomputes it from fixture content (iterate-2026-06-10-complexity-classifier-prior).
- **A module loaded by absolute file path (`importlib.util`) that defines a `@dataclass` under `from __future__ import annotations` must be registered in `sys.modules` BEFORE `exec_module`.** The dataclass machinery resolves PEP-563 string annotations via `sys.modules.get(cls.__module__).__dict__`; an unregistered module yields `None` → `AttributeError: 'NoneType' object has no attribute '__dict__'` at class-creation time. The `gitleaks_config_scaffolder` file-path-load pattern worked only because `security_workflow.py` is pure constants (no dataclass). Fix: `sys.modules[spec.name] = module` between `module_from_spec` and `exec_module` (iterate-2026-06-07-scaffold-churn-merge-machinery — the adopt `gitattributes_scaffolder` loads `gitattributes_union.py`, which has a `HealResult` dataclass). Corollary: a guarded fail-soft commit-path (modeled on `reconcile_main_triage`) must give the `git commit` a generous timeout (the bloat pre-commit hook's cold `uv run` exceeds the 15s default) AND catch `TimeoutExpired` → structured error + roll back the working tree/index, so it never crashes the caller's machine-readable stdout contract.
- **A silently-uncovered test directory hides real, pre-existing failures.** `shared/scripts/tests` was never referenced by any CI pytest invocation, and it had been hiding two genuinely failing `test_validate_env.py` tests for some time (non-hermetic: `validate()` does `available_vars.update(os.environ)`, so a host that exports `NEXT_PUBLIC_SUPABASE_*` clobbers the `.env.local` values the tests write). The CI-extension guard (`check_ci_gate_coverage.py`, iterate-2026-05-31-ci-gate-guard) now fails when any `plugins/*/tests` / `shared/**/tests` / `integration-tests/` dir is unreferenced. Corollary conventions: (1) when CI runs test dirs, run each as its **own pytest session** — `shared/tests` and `shared/scripts/tests` share basenames (`test_config.py`, …) that collide in one collection (mirror the per-plugin loop). (2) An accidentally-loose gate (`|| true` / `continue-on-error`) should be made **explicit** (documented allowlist entry, ideally `tracked-debt`) rather than silently tolerated — the guard distinguishes by-design non-gating from tracked debt and flags any new undocumented loose gate. (3) A security threshold gate must **fail closed** on a missing/unparseable input file (`findings.json`) — `2>/dev/null || echo 0` turns a scanner crash into a green pass. (4) **Empirical, hard-won:** bringing a Windows-developed test suite into a Linux-only CI surfaces real platform-portability debt — a leaked `monkeypatch.setattr("os.name","nt")` crashes pytest's OWN failure reporter on Linux (it builds a `WindowsPath`) with an `INTERNALERROR` that masks the underlying assertion; other tests assume gitignored main-tree staging a clean checkout lacks. Don't blanket-gate such a suite blind — verify against the REAL CI run (`gh pr checks` / `gh run watch`), and gate-as-tracked-debt (`|| true` + explicit allowlist entry) until the suite is cleaned, rather than asserting confidence. "Are you confident?" → run the CI and look.
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

- **F0.5 `surface_verification.py --surface cli --runner "..."` execs WITHOUT a shell — the runner must be a single executable, not a compound `cd … && …`.** A natural first attempt `--runner "cd plugins/shipwright-iterate && uv run … pytest …"` fails with `[orchestrator] command not found: [WinError 2]` (exit 127) because the orchestrator tries to exec `cd` as a binary. The runner runs with `cwd = --project-root` (the worktree root), so target the test path from there instead: `--runner "uv run --extra dev pytest plugins/<plugin>/tests/<file>.py -q"`. The repo-root `dev` extra carries pytest, and self-`sys.path`-inserting test modules resolve their imports regardless of cwd. Surfaced empirically on iterate-2026-06-07-campaign-expands-triage. **✓ FIXED iterate-2026-06-07-finalization-tooling-hardening:** `_tokenize` now rejects bare shell operators (`&&`/`;`/`|`) and leading builtins (`cd`) up front, and `run_with_retries` fails fast (0 attempts) with an actionable "F0.5 runs with NO shell …" message instead of the cryptic WinError-2 after 3 retries. (A single-executable runner is still required — the fix improves the *error*, not shell support.)
- **`test_architecture_md_reflects_arch_impact.py::test_arch_impact_drops_found_at_all` is born-fragile against the post-release main-tree state.** It `pytest.skip`s when `.shipwright/agent_docs/decision-drops/` is ABSENT (clean checkout) but hard-FAILs when the dir is PRESENT-but-holds-zero-`{component,data-flow,convention}`-impact drops — which is exactly the local main-tree state right after a `/shipwright-changelog` release aggregates + clears the drops (e.g. v0.24.0 `d5764ab7`). Two consecutive iterates (triage-gc-compliance-refreshed, campaign-expands-triage) recorded it as a pre-existing `degraded[]` condition. The robustness fix is to also skip (or downgrade to xfail) when the dir is present but empty-of-arch-impact. Until then, an iterate that touches neither `decision-drops/` nor `architecture.md` can treat this single shared-suite failure as environmental, not a regression. **✓ FIXED iterate-2026-06-07-finalization-tooling-hardening:** the sanity gate now classifies discovery via a hermetic `_discovery_sanity` helper — dir-absent → skip, present-but-empty → skip (legit post-release), present-with-any-drops → ok (resolution confirmed via *total* drop files; the arch-impact subset may legitimately be empty). The false-FAIL is gone; full `shared/tests/` is back to 0 failures.

- **Wiring a previously-CI-less test dir into CI: simulate a clean checkout, don't trust the dev tree.** When a test dir never ran in CI, individual tests can be "born red" the moment CI runs them, for reasons invisible locally: (a) **ambient-env leak** — a Shipwright dev session loads the repo's scaffold `.env.local` placeholders (e.g. `NEXT_PUBLIC_SUPABASE_URL=...`) into `os.environ`, and `validate()` correctly lets `os.environ` override `.env.local` (mirrors `load_shipwright_env`), so a non-hermetic test reads the placeholder as "missing" — red locally, green in clean CI; (b) **gitignored-data dependence** — a test asserting on `.shipwright/agent_docs/decision-drops/` (gitignored) passes locally but is born-red in a clean checkout where the dir is absent. An iterate **worktree** hides (b) too, because `resolve_main_repo_root` redirects to the main repo where the data exists. The authoritative probe is a **clean-clone CI simulation**: `git clone --single-branch --branch main file://<repo> /tmp/sim` + scrubbed env (`env -u VAR1 -u VAR2 pytest ...`). This distinguishes "stale-locally-only" from "real-in-CI" and finds born-red tests the named-candidate list misses (here: `test_arch_impact_drops_found_at_all`, not in the original 4). Fix non-hermetic tests with a dir-level `conftest.py` autouse `monkeypatch.delenv` (keeps a grandfathered test file from ratcheting the bloat baseline); fix gitignored-data tests with `if not <dir>.is_dir(): pytest.skip(...)` (skip on legitimate absence, still assert when present). See iterate-2026-05-31-ci-shared-tests.

- **Pytest `conftest.py` name collision across plugin dirs.** Two `tests/conftest.py` files (one per plugin) can't be loaded in a single pytest session — both get the module name `tests.conftest` and pluggy raises `ValueError: Plugin already registered under a different name`. Workarounds tried + outcome: (1) `--import-mode=importlib` — still fails because pluggy registers by basename before importlib resolves. (2) Running both files through `pytest <path1> <path2>` from repo root — fails. The working pattern: chain two separate pytest invocations via `bash -c "cd plugin1 && pytest tests/... && cd ../plugin2 && pytest tests/..."` so each gets its own session-scope. F0.5's surface_verification.py runner must accommodate this when verifying tests across multiple plugins. See `.shipwright/runs/iterate-2026-05-10-adopt-ci-scaffolders/runner.sh` for the canonical wrapper-script pattern.

- **Silent `pytest.skip` on missing binary/import paths must hard-fail in CI.** A `@pytest.mark.skipif(not shutil.which("X"), ...)` decorator OR `try: import X except: pytest.skip(...)` block silently degrades the test count without anyone noticing — both for missing-tooling cases (semgrep/gitleaks/trivy/npx/uv) AND cross-plugin sys.path-pollution cases (the `lib/`/`tools/` namespace collision is structural, every plugin defines its own). The fix: keep the local-dev skip but gate it with `if os.environ.get("CI", "").lower() in ("true", "1"): pytest.fail(<actionable install hint>)`. The hint must name a concrete remediation (`actions/setup-node@v4`, `astral-sh/setup-uv@v3`, plugin-session invocation). Canonical helper: `_ci_truthy() -> bool` (duplicated per file until AC-6 centralizes). Module-level `pytest.fail()` works in practice (raises `_pytest.outcomes.Failed` = collection error = non-zero exit) but is undocumented — pin via source-level regex (`test_silent_skip_ci_discipline.py`), not runtime. See ADR-044 + `references/test-hygiene` rules in `plugins/shipwright-iterate/skills/iterate/SKILL.md` Step 6.

- **Vestigial `|| true` from a dormant-CI era silently disables gating; sweep for it when hardening.** When CI is first stood up in a non-gating ("dormant" / early-access) posture, steps get trailing `|| true` (and/or `continue-on-error: true`) so red runs don't block. The later "activate + harden" pass must remove every one of those — but per-step swallows are easy to miss: the public-launch hardening (`d85210f`) added `set -e` to the plugin-test loop yet left the integration-tests step's `|| true`, so integration failures stayed swallowed and CI stayed green for weeks. Removing `|| true` is sufficient to gate on Linux runners because GitHub Actions' default shell is `bash --noprofile --norc -eo pipefail {0}` (i.e. `-e` is already on); no explicit `set -e` is needed for a single-command `run:`. Before removing a swallow, confirm the wrapped suite is currently green (else the un-swallow turns CI red on a real pre-existing failure) — integration was 136 passed / 0 failed here. The lint step's `|| true` (`ruff check . || true` + `continue-on-error: true`) is a separate, still-open item. See iterate-2026-05-31-ci-gate-f821.

- **Producer auto-resolve reason tokens and `triage_gc.MACHINE_REASONS` are a decoupled SSoT pair — a new producer reason silently escapes the dismissed-pile GC.** `triage_bundle.emit_compliance_backlog` emits three machine dismissal reasons (`complianceResolved`, `complianceRefreshed`, `supersededByBacklog`, all `by=complianceBacklog`) but `triage_gc.MACHINE_REASONS` listed only the first, so `complianceRefreshed` — regenerated every compliance run as the failing-finding signature shifts — accumulated as kept noise (`is_machine_churn()` requires reason ∈ `MACHINE_REASONS` AND dismisser ∈ `MACHINE_DISMISSERS`; the dismisser matched, the reason did not). This is the **second** miss of the same class (phaseQuality/testEvidence were the first, per the Codex-MEDIUM fix). Rule: when a background producer adds a machine dismissal reason, register it in `MACHINE_REASONS` in the same diff — or build the forward-drift meta-test that AST-enumerates every `_dismiss(..., reason=...)` literal across producers and asserts each *recurring* token is in the set. One-shot reasons (`supersededByBacklog`, emitted once at the 2026-05-31 backlog migration) are deliberately excluded — they do not accumulate, so GC-ing them buys nothing. **Corollary to the born-red learning above:** `test_arch_impact_drops_found_at_all` skips when `decision-drops/` is *absent* but not when *present-but-empty* — after a `/shipwright-changelog` release aggregates+clears the drops, the dev tree has the dir present and empty, so the sanity guard fires red again (observed in this iterate's F0). The skip predicate should widen to `not dir.is_dir() or not any(dir.glob("*.json"))`. See iterate-2026-06-07-triage-gc-compliance-refreshed.

- **F0.5 `surface_verification.py` runs `--runner` via `shlex.split` + `subprocess.run(shell=False)` — no shell builtins.** A runner of the shape `cd plugins/<plugin> && uv run pytest …` exits **127** (`cd` is not an executable; the orchestrator records `tests_run=0`, exit 3). For a single-plugin **CLI surface**, use one argv with uv's own directory switch: `uv run --directory plugins/<plugin> pytest tests/<file> -q` — uv changes into the plugin dir (resolving its `pyproject.toml`/`.venv`) before exec, and stdout's `N passed` is parsed for `tests_run`. Multi-plugin runs still need the chained wrapper-script pattern from the conftest-collision learning (entry above). Surfaced on iterate-2026-06-03-campaign-status-field.

- **A regression guard only counts if it lives in a directory CI actually runs.** `.github/workflows/ci.yml` invokes pytest against EXACTLY two roots — `plugins/*/tests` (per-plugin loop) and `integration-tests/`. **`shared/tests/` (2635 tests) is NOT executed by any workflow**, and the `Lint (ruff)` step is itself swallowed (`ruff check . || true` + `continue-on-error: true`). Consequence: a test added under `shared/tests/` passes locally but never fires in CI — a guard placed there against a CI-config regression (e.g. re-adding `|| true`) is theater. Put CI-invariant guards in `integration-tests/` (or a plugin's `tests/`). Discovered in iterate-2026-05-31-ci-gate-f821: the no-swallow guard was first written to `shared/tests/test_ci_self_gating.py`, then moved to `integration-tests/` after a confidence probe showed it would never run in CI. Import guaranteed root deps (e.g. `yaml`) unconditionally in CI-run tests, not via `importorskip`, so a missing dep hard-errors instead of silently skipping (ADR-044). **Open follow-up (out of scope here):** `shared/tests` has no CI coverage at all — a separate iterate should either run it in `ci.yml` or fold it into a covered root.

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

- **Triage producers importing from systems that already have a per-finding store MUST emit action-units, not finding-mirrors.** GitHub's Security tab is already the per-finding database; mirroring it 1:1 into `.shipwright/triage.jsonl` (PR #39's original shape — 32 findings → 32 items) floods the operator and forces them to assemble the matching slash-command manually. The right shape: collapse into a small number of action-units (one per repo or per failing workflow), each carrying a producer-generated `launchPayload` — a ready-to-paste block (slash command + context + the upstream URL) that the operator copies into a new Claude session as the "Fix now" flow. The inbox markdown view IS the launch surface. Generalizes beyond GitHub: any future upstream-with-its-own-store producer should follow the same shape. Origin: iterate-2026-05-20-triage-launch-surface (ADR pending).

- **Schema-migration sweeps in fail-soft producers MUST be per-original-source-gated.** When a triage producer changes its emission shape (e.g. legacy per-finding keys → new action-unit keys), the next run dismisses legacy items as `reason="schemaMigration"` — but ONLY for the original source whose fetch succeeded this run. Inferring success from a different source's success would mass-resolve on a transient outage, violating the ADR-052 fail-soft invariant. Pattern: track `fetch_succeeded[source_name]` per legacy-prefix mapping; iterate `(source_name, legacy_prefix)` pairs and skip migration when that pair's fetch returned `None`. Empirical test fixture: parametrize across all 4 sources with one failing at a time, assert legacy items for the failed source survive. Surfaced as code-review HIGH #3 from external review in iterate-2026-05-20-triage-launch-surface — the migration is one-shot per item but its eligibility check is not pan-producer.

- **Launch-surface CLI parity contract: the GUI is a thin wrapper over the library, not a parallel implementation.** When a feature ships first via CLI and later gains a GUI button (typical Shipwright shape: monorepo CLI → shipwright-webui tab), both surfaces MUST delegate to the same library function with no semantic divergence. Lock the parity at build-time with a test that invokes both surfaces against an identical fixture and diffs the persisted audit-trail events (excluding only the actor-label / timestamp / id). Pattern: extract a shared helper (`promote_item` / `dismiss_item`) BEFORE building either surface; both `main()` and the new CLI import the helper. Avoids the failure mode where the GUI silently develops a different behavior than the CLI over time. Surfaced as code-review MED #2 from external review in iterate-2026-05-20-triage-launch-surface.

- **Repo-identity resolution for triage producers MUST be local-first (git remote), never via `gh api`.** A producer that imports per-repo findings via `gh api repos/{owner}/{repo}/...` needs `{owner}/{repo}` resolved BEFORE the API call — `gh` can't tell you that. The right pattern: parse `git remote get-url origin` (recognise HTTPS + SSH + token-bearing + enterprise variants), strip trailing `.git`, return `None` on missing/malformed/non-GitHub remotes. On `None`, the producer SKIPS emission of repo-scoped action-units rather than emitting malformed dedup keys like `gh-security:`. Test matrix: 12 recognised remote shapes + 8 invalid ones. Origin: iterate-2026-05-20-triage-launch-surface (review finding #4) — `shared/scripts/github_api.py::owner_repo` is the canonical implementation; future producers needing repo identity reuse it.

- **Symmetric emit + resolve gates: a producer that emits an action-unit only when N upstream feeds succeeded must ALSO scope auto-resolve to require the same N feeds.** A combined action-unit (e.g. `gh-security` collapses code-scanning + dependabot) freezes its `launchPayload` at first append; emitting on a partial fetch (one feed `None`, the other present) persists a payload misreporting "0 X alerts" for the failed feed. The auto-resolve gate had this right already (resolvable only when both feeds succeeded); the emit gate must mirror it. Asymmetric gates are the second-most-common boundary-probe failure mode after format drift. Surfaced as code-review MED #1 in iterate-2026-05-20-triage-launch-surface.

- **Render-banner timestamps are a producer/consumer boundary — derive from input data, never from wall-clock.** Any tracked file rendering with a `Generated:` / `Updated:` / `Auto-generated` banner whose value is `datetime.now()` will drift on every regeneration even when the input data is unchanged, leaving the working tree permanently dirty in `git status`. The Shipwright SSoT for "when did things happen" is `shipwright_events.jsonl`; banners should report `max(event.ts)` via `shared/scripts/lib/events_log.latest_event_dt`. Cross-plugin renderers that can't import shared/scripts/lib (e.g. compliance) keep a local helper mirror per the existing parity-test pattern. Empirical verification: two renders separated by `sleep 2` must produce byte-identical output. Note: the iterate's own F7 event isn't in the log at render time (renderers run pre-commit, F7 is post-commit), so dashboard / compliance banners read "data as of LAST iterate's F7"; session_handoff reads the CURRENT iterate (its generation step runs after `_record_event` in finalize_iterate). Asymmetry documented in `events_log.latest_event_dt` docstring. Origin: iterate-2026-05-22-deterministic-render-timestamps.

- **Run the external LLM plan review against the *iterate spec + mini-plan*, not only against the diff — the plan is where structural bugs are cheapest to catch.** Iterate-2026-05-21-security-artifact-producer's first plan said "fire artifact fallback when cs AND db both fail" because the operator framed it as binary "GHAS or shipwright-security". Both Gemini and OpenAI caught the bug in the plan review: Dependabot is free and orthogonal to GHAS Code Scanning, so the fallback condition must be `cs_alerts is None`, not `cs AND db both None`. Fixing the design in the plan changed one conditional + one mapper signature; catching it in the code review would have meant restructuring `security_action_unit_from_artifact` and writing two more tests. Rule: medium+ iterates touching new ingestion paths or new boundary contracts MUST run plan-level external review before tests get written. The iterate SKILL already mandates this at medium+; the lesson is that "plan review" includes empirical contract challenges from the reviewer, not only stylistic feedback. Origin: iterate-2026-05-21-security-artifact-producer external review HIGH findings #1 (both reviewers).

- **Aggregate counters in producer JSON are untrusted — derive from the list.** A serialized artifact like `findings.json` ships both a `findings` array AND a redundant `by_severity` aggregate (and `total_findings`, etc.). Reading the aggregate is tempting (one field, no iteration), but: (a) the aggregate and the list can disagree in real artifacts (producer bug, version drift, mid-write capture), and (b) trusting the aggregate creates a hidden trust boundary that the consumer never validates. Rule: when both a list and its aggregate ship in the same payload, iterate the list and compute the aggregate yourself. Use the producer's aggregate ONLY for cross-check / diagnostic logging, never for emission. Defensive: validate the list is a list before iterating; non-list `findings` returns `None` from the parser (treated as malformed). Origin: iterate-2026-05-21-security-artifact-producer external review #9 (OpenAI). See `shared/scripts/github_triage.py::_artifact_extract_severity` + `security_action_unit_from_artifact` for the canonical pattern.

- **Consumer-side synthesis is a valid fallback when canonical producers are uninstrumented.** When a renderer reads from event type X (`test_run` in this case) but X is uninstrumented across the live pipeline — so the section is silently empty on every real repo — the consumer can synthesize from a *related* event type Y (`work_completed` with `tests.*` side-data) instead of waiting for producers to land. The canonical path stays untouched (X-events win when present); synthesis is a guarded fallback (`if data.test_runs: X else: synthesize-from-Y`). Two contract constraints make this safe: (a) gate the fallback on `any(qualifying)` so behavior matches the canonical path when no data exists at all; (b) drift-protection test asserting both branches emit identical column headers, so a future refactor adding a column to one path must add it to the other. Origin: iterate-2026-05-21-empirical-followups AC-2; see `plugins/shipwright-compliance/scripts/lib/test_evidence.py::_full_suite_runs_from_work_events` + `test_drift_protection_both_branches_render_same_columns`.

- **Path-canon lint must allowlist regenerated artifacts that contain plugin-source-tree paths.** The regex `(?<![\w/.\\])<dirname>/` excludes word-chars, `/`, `.`, and `\` from the negative-lookbehind class — but **not `-`**. So `plugins/shipwright-<dirname>/scripts/...` matches whenever a producer emits that string into a regenerated `.md` artifact (e.g. SBOM card launchPayloads pasted into the triage inbox). The fix is per-artifact allowlist extension, not a regex tightening — `-` is a legitimate path-segment separator and the producer string is structurally valid (it's a plugin source-tree path, not a legacy artifact path). Surfaced empirically post-iterate-B.2 when the regenerated triage inbox started carrying SBOM payloads; F0 catches the trip on the next iterate's full-suite run. Self-referential check: any new learning that quotes a `<dirname>/...` token also needs the allowlist entry, since F3a writes happen after F0. Origin: iterate-2026-05-21-empirical-followups AC-3; allowlist entry in `shared/scripts/lib/artifact_migrations.py::ALLOWLIST`.

- **Artifact contents are untrusted CI output — render aggregated counts only, never raw scanner strings.** Even though `findings.json` is produced by your own workflow, its inputs include scanner rule descriptions, file paths, and CVE summaries that ultimately come from third-party rule packs and the package ecosystem. Persisting those raw strings into `detail` / `launchPayload` means a malicious dep description or a crafted PR title in a transitive `dependency.html_url` could become a markdown-injection vector in the WebUI Triage tab. Hygiene rule mirrors the gh-secrets whitelist-only payload (iterate-2026-05-20): action-unit `detail` and `launchPayload` carry ONLY aggregated counts, owner_repo, and the stable workflow run URL. Length-cap `detail` at 1KB defensively. Origin: iterate-2026-05-21-security-artifact-producer external review #11 (OpenAI).

- **Tracked-but-derived artifacts need a single producer + snapshot-provenance audit, NOT live-render byte-compare.** When an artifact (Markdown / JSON / generated file) is tracked in git but derived from upstream state that drifts on every commit (events log, git log, dep manifests), a "fresh re-render vs on-disk" audit produces perpetual false positives — any non-iterate commit shifts upstream state without touching the tracked file. Two coupling rules fix this: (1) **single producer** — only one well-defined moment writes the artifact (iterate-finalize, in the Shipwright case); all other paths (Stop hooks, drive-by regen) are deleted, not retained as "best-effort fallbacks". (2) **snapshot-provenance audit** — instead of re-rendering at audit time, compare on-disk to the most recent commit that BOTH (a) carries the producer's identity marker (`Run-ID:` trailer) AND (b) modified the artifact's path. Non-producer commits don't touch the artifact → snapshot baseline stays stable → zero false positives. Live state remains inspectable on-demand by manually invoking the producer (writes uncommitted), but the audit no longer conflates "is the file current with live state" (currency) with "is the file intact against the last canonical snapshot" (provenance). Origin: iterate-2026-05-23-compliance-md-single-producer; Codex consult ruled out the auto-regen / per-phase / release-only alternatives as either signal-destroying, too-wide-blast-radius, or semantic-bombs.

- **Avoid `sys.path.insert(0, ".../shared/scripts")` in plugin code — use `audit_adapters.load_shared_lib(name)` instead.** Plain `sys.path.insert + from lib.X import Y` pins the `lib` namespace package to `shared/scripts/lib` for the rest of the process. Any sibling plugin that has its own `lib/` (e.g. `plugins/shipwright-compliance/scripts/lib/thresholds.py`) then silently shadows when imported via `from lib.thresholds import ...` — collection-order-dependent ImportError that passes in isolation, fails in mixed test runs. The `load_shared_lib(name)` helper in `plugins/shipwright-compliance/scripts/audit/audit_adapters.py` loads the file via `importlib.util.spec_from_file_location` under a sentinel module name and never touches the `lib` slot. Use it for any cross-package shared-lib access from a plugin. Origin: iterate-2026-05-23-compliance-md-single-producer (caught when `test_enforcement_hooks.py` failed to collect after `audit_staleness.py` started importing `lib.events_log`).

- **Markdown table rows are also a producer/consumer boundary — but the consumer is the human eye / GFM viewer, not a shipwright parser.** Any framework code that renders a row via `f"| {x} | {y} |"` from event-derived data MUST wrap every cell in `shared/scripts/markdown_table.py::escape_cell`. A single literal `|` in an event field shifts subsequent cells by one column (silently — the renderer reports success and the dashboard ships visibly broken); a literal newline ends the row at the first `\n`, dropping every subsequent cell. The escape order matters: `\` → `\\` MUST run BEFORE `|` → `\|`, otherwise the pipe-pass doubles a pre-existing backslash and a downstream `re.split(r"(?<!\\)\|", row)` mis-classifies escaped vs unescaped pipes. Cross-cutting test rule: a regression test built against the real renderer (event → file → re-parser) is required, not just unit tests on the helper — the unit tests will pass even if a call site is silently missed (which happened: external code review caught a 6th unwrapped row in `compliance_report.py` past my mini-plan's 5-file modify list). Origin: iterate-2026-05-20-escape-md-cells, motivated by an empirical bug in shipwright-webui's Recent-Changes row.

- **`importlib.metadata` is disqualifying for compliance tooling — its `sys.path` lookup is ambient process state.** Any resolver that needs to read package metadata across multiple manifests (workspace monorepo) must read directly from `<manifest_dir>/.venv/{Lib,lib/python*}/site-packages/<pkg>-*.dist-info/METADATA` via `email.parser.HeaderParser`. `importlib.metadata.metadata(name)` walks the **orchestrator's** Python `sys.path`, which is unrelated to the manifest being scanned — leading to two structural bugs: (a) non-determinism (consecutive renders disagree depending on which `.venv` the shell entered recently), (b) cross-manifest blindness (operator runs `uv sync` in `plugins/<x>/`, populates that plugin's `.venv/`, but the resolver running from repo root never looks there → license stays "unknown" and the triage launch payload never resolves). Companion finding: **`uv.lock` does NOT carry license metadata** — verified empirically on `plugins/shipwright-plan/uv.lock` etc. Only package name, version, source URL, hash, dep-graph. Pinning to `uv.lock` for licenses is not an option; pin to per-manifest dist-info METADATA (with PEP 503 canonical-name normalization for `[-_.]+` runs + case). The d325fd6 deterministic-render-timestamps pattern generalizes: derive output from a stable input artifact, not ambient process state. Origin: iterate-2026-05-23-sbom-resolver-pin-lockfile.

- **Filesystem glob enumeration of `*-VERSION.dist-info` directories must sort by parsed version, NOT lexicographic.** A naive `sorted(site_packages.glob("*.dist-info"))[-1]` puts `pkg-2.0.0.dist-info` AFTER `pkg-10.0.0.dist-info` (because "2" > "1" lexicographically) — so "pick newest" silently picks the older one for any two-digit major version. Use `packaging.version.Version` (transitive of pytest in this repo) with a hand-rolled `(int,int,...)` tuple fallback for environments without `packaging`. The same pattern applies any time we sort dir names of the shape `<name>-<version>.<suffix>`: enumerate, parse the version segment, sort by parsed version. Test `pkg-10.0.0` vs `pkg-2.0.0` as the discriminator — `1.0.0` vs `2.0.0` doesn't catch it. Origin: iterate-2026-05-23-sbom-resolver-pin-lockfile (external code review HIGH-1, past `test_multiple_distinfo_picks_deterministically`).

- **Skip-dir patterns for source walkers must distinguish "tool output at root" from "directory name nested under source".** `dist/` and `build/` are skip-anywhere *only* at the project root — `plugins/shipwright-build/skills/build/SKILL.md` is a real source path that shares the dir name. The fix is path-aware pruning: prune those names only when the parent equals the project root. `.git`, `node_modules`, `.venv`, `__pycache__`, `.pytest_cache` etc. stay skip-anywhere because they only occur as output / vendored / cache dirs. Surfaced in iterate-2026-05-25-bloat-foundation when `bloat_baseline.scan()` returned no entries for `plugins/shipwright-build/skills/build/SKILL.md` — the walker had pruned `build/` along the way. Pattern lives in `shared/scripts/lib/bloat_baseline.py::_iter_candidates`.

- **Hook-budget vs message-content tension: long-form error messages are bytes-on-disk that count toward LOC.** The Stop-Gate hook (`bloat_gate_on_stop.py`) carries ~45 LOC of Iron-Law / Red-Flags / Rationalization-Prevention text as a module-level constant — that's the actual error-message UX when the gate fires. Cutting it to hit the campaign's aspirational ≤200 LOC budget would weaken the operator-facing payload of the very enforcement it embodies. The structural 300 LOC limit (which this iterate enforces) is the contract; the campaign's 200 was aspirational. Rule of thumb: when a script's primary output is a long-form error message, the message body counts toward LOC like any other code, and the LOC budget should accept 40-60 LOC of message content above the algorithm baseline. Documented in AC-4 of iterate-2026-05-25-bloat-foundation.

- **Self-eating-dogfood signal: the new gate firing on its own author is a smoke test, not a failure.** While building Campaign A.foundation's marker writer, the existing PostToolUse `check_file_size.py` nudge fired on my own implementation (`bloat_baseline.py` at 316 LOC) and on the test file (`test_bloat_gate_on_stop.py` at 323 LOC). Both were trimmed back under 300 in the same Edit cycle. This is the loop working as designed — even though PostToolUse is advisory in this iterate, the visible nudge surfaced the bloat at edit-time and the Stop-Gate would block from the next iterate onward. Lesson: when adding enforcement, the author's own files are the first integration test; trim or grandfather them deliberately rather than working around the gate.

- **Runtime/snapshot split generalises the single-producer pattern when the artifact carries iterate-specific context.** PR #78 (compliance MDs, 2026-05-23) made `iterate-finalize` the SOLE producer of 5 tracked compliance docs and deleted the Stop-hook fallback writes — acceptable for audit/archival docs whose staleness between iterates is benign. But the same delete-only fix wouldn't work for the 3 agent-doc MDs (`session_handoff.md`, `build_dashboard.md`, `triage_inbox.md`): these are *live mid-session state* — non-iterate sessions (security work, manual fixes, design work) need fresh handoff + triage state between iterates. The right shape is a runtime/tracked SPLIT: Stop hooks write live state to `.shipwright/agent_docs/runtime/` (gitignored), iterate-finalize is the sole producer of the tracked variants. Per-file decision in finalize matters: artifacts that need iterate-specific context (canon-marker, run_id) MUST direct-write (handoff, dashboard) — the runtime variant lacks that context, and a copy would let an F11 verifier (`check_session_handoff_fresh`, `check_build_dashboard_has_run_id`) fail. Pure aggregations like triage (no iterate context) safely copy from runtime via atomic `os.replace` + unlink. The asymmetric path (snapshot copy vs direct-write) is intentional and per-file. Origin: iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox; constants in `shared/scripts/lib/artifact_paths.py`.

- **A finalize sandbox-escape via stale session→worktree pointer is the second-most-common single-producer failure mode after "two producers."** PR #78 closed the source-level escape (multiple writers → one writer = finalize). But the target-level escape stayed open: `iterate_stop_finalize.py` set `SHIPWRIGHT_PROJECT_ROOT` only when `_active_worktree_root()` returned a valid pointer; on None it silently fell through to `resolve_project_root()` which used cwd, which at Stop-time is the main repo. Finalize then wrote the 8 tracked compliance + agent-doc MDs into main, bypassing the single-producer guarantee at the target. Fix: hard-gate the repair pass with `if worktree is None: return 0` (refuse, never fall back to cwd) + strengthen `_active_worktree_root` validation (resolved path must exist AND live under main_root AND look like a worktree). The corollary: every "single producer" guarantee has BOTH a source-level and target-level dimension; both must be enforced. Origin: iterate-2026-05-27 SCOPE 2.

- **Idle-main producers must resolve `main_repo_root` (never `Path.cwd()`) AND write transient state only to gitignored paths.** Two corollaries of the ADR-089 family, found leaking on idle `main` after PR #172: (1) **Root, not cwd.** The bloat-marker PostToolUse writer (`check_file_size`) + Stop reader (`bloat_gate_on_stop`) keyed the marker / baseline / re-measure off `Path.cwd()`. A hook firing with cwd≠repo-root (sub-package test run, monorepo auto-descent) wrote `<cwd>/.shipwright/locks/bloat_pending.*.json` — i.e. into `shared/.shipwright/` — which the root-anchored `/.shipwright/*` ignore misses. The SAME `cwd`-at-Stop antipattern ADR-089 SCOPE 2 hard-gated for finalize. Fix: a fail-soft `repo_root.main_repo_root_or(Path.cwd())` (thin adapter over `worktree_isolation.main_repo_root`, in its own module so the already-grandfathered worktree_isolation isn't ratcheted) shared by BOTH writer and reader so they can never disagree on location; a non-anchored `**/.shipwright/locks/` canon-ignore is belt-and-suspenders. Whenever a fix names ONE side of a producer/consumer marker pair, check the other — the leak's true author is usually the writer. (2) **Transient ⇒ gitignored path.** A derived cache that is regenerated every Stop and is NOT in `audit_staleness.DOC_REGISTRY` is transient: it belongs under an already-gitignored home, not a tracked-eligible one. The 3 phase-quality skill-compliance roll-ups (report/dashboard/findings) Stop-wrote to tracked-eligible `.shipwright/{compliance,agent_docs}/` while their source JSON dir was already ignored — partial ADR-089 adoption. Fix: relocate them UNDER the already-ignored `skill-compliance` dir (no DOC_REGISTRY + finalize arm needed — that is only for tracked-durable docs). Decide transient-vs-durable by evidence (never-tracked + not-in-registry + Stop-regenerated + live-consumer ⇒ transient), not by guess. Origin: iterate-2026-06-09-idle-main-artifact-hygiene; trg-7640bd14.

- **Branch integration: `git merge`, not `git rebase`, for Run-ID-bearing branches.** `audit_staleness.find_snapshot_commit` locates the last single-producer snapshot via `git log --grep=Run-ID:` against the current branch. A rebase rewrites every Run-ID commit's SHA AND may drop merge-bearing trailers entirely depending on the strategy — the audit then reports `snapshot_unavailable` on a branch with dozens of legitimate Run-ID commits. Convention is doc-only (`docs/hooks-and-pipeline.md` → "Branch integration" section), drift-protected by `shared/tests/test_branch_integration_doc.py`. `gh pr merge --rebase` carries the same semantics as a local rebase; prefer `--merge` or `--squash`. Force-push recovery via `git reflog` is documented. A programmatic pre-rebase guard was deferred per external review OpenAI #12. Origin: iterate-2026-05-27 SCOPE 3.

- **Audit-coverage extension to docs added AFTER the last snapshot needs a "not-in-snapshot" semantic, not a stale verdict.** When a single-producer registry expands (e.g. adding the agent-doc trio to `audit_staleness.DOC_REGISTRY`), the next audit will compare against a snapshot from BEFORE the registry change — a snapshot that doesn't contain the new paths. The naive code path (treat snapshot-side missing as "stale") then flags every newly-registered doc as stale until the next iterate-finalize commit, producing 3+ false-positive Group E entries per audit. Right semantic: when snapshot side is missing (regardless of on-disk presence), return `stale=False, error="not-in-snapshot"`. The next finalize introduces the path; subsequent audits compare normally. Caught by code-reviewer HIGH #1 in iterate-2026-05-27.

- **Splitting an allowlisted monolith into a package MUST migrate its `artifact_migrations.py` ALLOWLIST entry to a package glob in the same diff.** The path-canon lint (`test_artifact_path_canon`) runs only on the FULL `shared/tests/` suite — a `-k`-scoped or single-plugin run never sees it. So a Campaign-B-style split (`orchestrator.py` → `orchestrator_pkg/`, `phase_quality.py` → `phase_quality/`) that leaves the old whole-file allowlist entry pointing at a now-deleted/shim path silently passes the split iterate's own F0 (which scoped its tests) and only goes red a campaign later when someone runs the full suite. The fix is mechanical but the diagnosis is not: every finding looks like a regression. Rule: when a split moves code out of an allowlisted file, replace the stale entry with `<package>/**` (preserves the exact pre-split whole-file blast radius — no broadening) in the SAME commit as the split. New files carrying legitimate plugin-source-tree paths (`plugins/shipwright-compliance/...` trips the `(?<![\w/.\\])compliance/` regex because the negative-lookbehind class lacks `-`), phase-name enum strings, or module names in `__all__` need their own allowlist entry too — and for JSON artifacts (`shipwright_bloat_baseline.json`) the file-path allowlist is the ONLY option since JSON has no inline-marker syntax. Verify each finding is legitimate before allowlisting — the lint is a security control, and a too-broad glob masks real legacy-path bugs. Origin: iterate-2026-05-29-fix-path-canon-allowlist (cleaning up Campaign A.defense + B aftermath; 41 findings, all legitimate).

- **A "worktree-aware" abstraction built for one failure mode can become the bug for a later workflow — confirm the full blast radius before flipping it.** The event-log resolver redirected writes to the MAIN repo via git-common-dir, built (2026-05-16) to stop a worktree-local copy being discarded by `git worktree remove`. That assumption was correct ONLY for events written outside a commit; once iterates commit-and-ship-via-PR, the redirect orphaned the `work_completed` event as an uncommitted main-tree line. The same assumption was encoded in FOUR places that all had to move together: `events_log.resolve_events_path`, the compliance parity copy `_resolve_events_path`, the leak-guard `_MAIN_TREE_WRITE_EXEMPT`, and the F7b seal — flipping only the obvious resolver would have left silent disagreement (compliance regen reading a different log than the producer wrote). Rule: when reversing a deliberately-built design decision, grep for every co-located encoding of the same assumption (resolvers, parity copies, exemptions, seals, and their drift meta-tests) and move or document each. The classification matters too — `resolve_main_repo_root` was LEFT unchanged because decision-drops genuinely still need the main repo (gitignored, consumed on `main`); only the events log changed. Origin: iterate-2026-05-29-events-jsonl-worktree-commit.

- **An SHA assigned by a commit cannot be patched back into a file that same commit just committed without re-dirtying it — drop the back-patch, don't add a second commit.** F6.5 patched the F6 commit SHA into the events.jsonl line F5b had recorded. That was fine while the event lived in the main tree (out-of-band, never committed by F6). Once events.jsonl became a per-tree artifact staged BY F6, the post-F6 SHA patch re-dirtied the just-committed file — forcing either a `--commit --amend` (forbidden) or a second seal commit (the very `chore(events)` we were eliminating). Resolution: ship the event with `commit=""` and recover the linkage from the commit's `Run-ID:` footer + the event's `adr_id`; all consumers already tolerate an empty commit field. Lesson: a value produced BY a commit (its SHA) is structurally unavailable to content committed IN that commit — design the artifact to not need it, rather than chasing it with an amend or a follow-up commit. Origin: iterate-2026-05-29-events-jsonl-worktree-commit.
- **A patch that "rides inline" with a campaign silently vanishes unless the campaign's sub-iterate plans explicitly name it.** Spec/external-frameworks-integration.md §6.2 routed SP3 (`F-debug.md`) and OS2 (assumptions-first) to ride inside Campaign B's B1.iterate / B1.project splits "for free" because they touched the same files, and deliberately created NO own triage item. Campaign B closed (PRs #89–#102) having split both SKILL.md files but carrying neither patch — the sub-iterate plans never referenced the riders, and "same files" was not the same as "same work". The gap was invisible until a post-merge grep. Lesson: a rider has no owner; either give it its own tracked item (the `trg-89d3caa4` P2.recovery bundle this iterate closes) or add an explicit, testable sub-point to the host iterate's plan — "no own triage item" is how scope evaporates. Origin: iterate-2026-05-29-sp3-os2-reintegration.

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

- **Iterate skill discipline gaps — three lessons from iterate-2026-05-23-verifier-multi-commit-aware's drift remediation:**

  1. **TDD RED-first applies even to "drift-protection" tests.** Writing the
     assertion AFTER updating the source it asserts on means the test never
     proves it can fail — you can't tell whether the test is well-formed or
     accidentally lax. The RED phase IS the evidence that the test
     discriminates. The F7-fix iterate added 10 tests AFTER the
     implementation existed; they all passed first-try, which means none of
     them ever exercised the failure mode they were supposed to pin. The
     architecture-md drift-protection test in iterate-2026-05-23-verifier-
     drift-remediation went RED first and surfaced 11 historical drift
     entries that nobody had noticed — proof that the RED phase finds real
     drift, not just confirms it doesn't exist.

  2. **F0 leak-guard symmetry with F11.** The iterate skill prescribes
     `check_iterate_isolation.py --stage f0` BEFORE finalization (drops,
     compliance regen) and `--stage f11` BEFORE push. Skipping the F0 stage
     means a parallel-session leak that crept in between worktree creation
     and finalization is not caught until F11 — by which point the iterate's
     own snapshot may already include the leaked path as baseline. Run
     `--stage f0` at the START of finalization (between F0 fresh-test gate
     and F1 drift check) regardless of how small the iterate looks.

  3. **`--architecture-impact convention|component|data-flow` and an
     architecture.md update are coupled, structurally.** Setting the flag
     without adding the bullet is silent drift — the ADR records the
     decision but the read surface (architecture.md as the always-loaded
     Layer-1 context) doesn't reflect it. New drift-protection test
     `shared/tests/test_architecture_md_reflects_arch_impact.py` enforces
     this forward (and surfaced 11 historical drops missing entries). When
     adding the flag to `write_decision_drop.py`, in the same diff: append
     a bullet under `## Architecture Updates` in architecture.md naming
     the `run_id` + impact category + 1–2 sentence summary of the
     convention/component/data-flow change. The test now fails closed.

- **Drift-protection meta-pattern (RED-first surfacing of historical drift).**
  When a convention exists only in prose (SKILL.md, docs/, ADRs), the only
  way to find historical drift is a mechanical test that enumerates every
  artifact governed by the convention. Write the test against the *current*
  state of the artifact; if it goes RED with N entries, you've discovered N
  pre-existing drift cases. Backfill the N entries to GREEN, then keep the
  test as a forward-looking gate. The architecture-md test caught 9
  historical drift entries from the b/c bloat-cleanup campaign that no
  prior reviewer noticed. Apply the same pattern next time a "documented
  but unenforced" convention surfaces — `_find_work_event_by_run_id` ↔
  `adr_id` is a candidate (a meta-test that every iterate's F7 event has
  an `adr_id` matching the iterate's run_id).

- **ADR-056** (2026-05-21): Markdown table cell escaping helper

- **ADR-057** (2026-05-20): Triage Inbox redesigned as a launch-surface: action-units + launchPayload + CLI

- **ADR-058** (2026-05-21): Mode-aware dashboard + Why-warn column + Triage open indicator

- **ADR-059** (2026-05-21): SBOM undeclared-license triage (per workspace)

- **ADR-060** (2026-05-21): Per-layer FAIL triage + Layer column + record_event layers schema

- **ADR-061** (2026-05-21): RTM consumes frId cross-link + actionable Coverage subsections

- **ADR-062** (2026-05-21): Hard-enforce FR-or-change-type at iterate finalize (forward-only)

- **ADR-063** (2026-05-21): F4-F7 detective-only documentation hygiene checks

- **ADR-064** (2026-05-21): Detective-only plugin-cache vs repo drift check

- **ADR-069** (2026-05-21): Triage producer contract: schema + RTM-link fields + inbox polish

- **ADR-070** (2026-05-21): Deterministic render timestamps via events.jsonl max-ts

- **ADR-072** (2026-05-23): Compliance MDs: single-producer + snapshot-provenance audit

- **ADR-073** (2026-05-23): F7b seals F7 appends in self-tracking repos

- **ADR-074** (2026-05-23): Extend snapshot producers: adopt Step H + security Step 7.5

- **ADR-075** (2026-05-23): Test enforces architecture.md ↔ decision-drop coupling; 11 historical drift entries backfilled

- **ADR-076** (2026-05-23): F11 verifier resolves F7 event by run_id, not HEAD commit

- **ADR-082** (2026-05-24): SBOM producer collapses N workspaces with same undeclared-signature into one cluster

- **ADR-083** (2026-05-25): Pre-commit + CI anti-ratchet gate + bloat-exception ADR template + glossary

- **ADR-084** (2026-05-25): Two-hook structural prevention against file-size regrowth

- **ADR-085** (2026-05-25): Bloat-policy detective audit lands as Group H (G collision-avoidance)

- **ADR-089** (2026-05-27): Guide + README refresh for Campaign A+B (post-v0.22.0)

- **ADR-091** (2026-05-27): Runtime/snapshot split for agent-doc trio + hard-gated finalize repair pass

- **ADR-094** (2026-05-29): events.jsonl is a per-tree, PR-committed artifact

- **ADR-097** (2026-05-29): SessionStart bootstrap + plugin-cache Stop reminder; Python hooks keyed off payload session_id

- **ADR-100** (2026-05-30): Canonical .shipwright gitignore block propagates to consuming projects

- **ADR-102** (2026-05-30): Three-stage build reviewer cascade: spec-reviewer (HARD-GATE) -> code-reviewer -> conditional doubt-reviewer

- **ADR-106** (2026-06-01): Churn-artifact merge reconciliation: events=union + regenerate-on-conflict resolver

- **ADR-108** (2026-05-31): CI gate-coverage guard + workflow hardening

- **ADR-109** (2026-05-31): CI lint gate: curated bug-focused ruff ruleset + de-neuter

- **ADR-111** (2026-06-01): Per-project disabled_checks applicability gate + D5 change_type exemption

- **ADR-112** (2026-05-31): Compliance triage emits one rolling backlog action-unit, not one item per check

- **ADR-114** (2026-05-31): Phase-quality triage emits one rolling backlog action-unit, not one item per FAIL

- **ADR-118** (2026-06-01): Pin third-party GitHub Actions to SHA + verify Gitleaks download

- **ADR-119** (2026-06-01): Assert upload-sarif on the real uses: line, not a comment substring

- **ADR-120** (2026-06-02): Dedup SessionStart Phase-Quality injection to once-per-event
- **(2026-06-05, iterate gitleaks-report-path)**: gitleaks `--report-path -` is NOT stdout — gitleaks does `os.Create("-")` and writes a literal file named `-` (verified v8.21.2 `cmd/root.go`+`report/report.go`). Read the JSON report from a real temp file, not subprocess stdout. **Gotcha (sharpens the line-26 "verify against the REAL run" learning):** a "detects on Windows, 0 on Linux CI" scanner story can be a *measurement artifact* — the manual repro command omitted the wrapper's `--report-path -`, so it surfaced gitleaks' own stderr summary (detection) while the wrapper read empty stdout (0 findings) on every platform. Verify the exact wrapped command's output channel (stdout vs report-file) against the real binary before concluding platform divergence. Fingerprint: a stray file named `-` left in the scan CWD (it held the real finding).

- **(2026-06-06, iterate arch-drift-detector)**: **A drift detector that diffs the git HISTORY of gitignored inputs can never fire.** Group F's F5 used `git log <marker>..HEAD -- .shipwright/agent_docs/decision-drops/` to find "new" arch-impact drops, but decision-drops are gitignored — never committed, so the diff was always empty and F5 was permanently green while `architecture.md` silently drifted from 5 real drops (no triage item). The fix is **content reconciliation**, not history-diffing: read the drop JSON + the tracked `architecture.md` text and assert each arch-impact `run_id` appears (the exact oracle the drift test already used). General rule: if a check's INPUTS are gitignored staging, any git-history-based oracle over them is structurally dead — reconcile the staging content against the tracked artifact directly. Two corollaries: (1) **share one oracle** between a detective (surfaces existing drift) and its finalize gate (prevents new drift) — here `shared/scripts/lib/architecture_doc.py` is imported by Group F (via `audit_adapters.load_shared_lib`, which avoids pinning the `lib` namespace) AND by the F11 verifier (via `from lib.architecture_doc`) — so they cannot diverge. (2) **a prose-only "always update X" step that has no live gate WILL drift** (the old `check_architecture_reviewed` was dead code with zero callers + an mtime heuristic that never checked content); convert it to a canon gate (`check_architecture_documented` in `verify_iterate_finalization`). Match `run_id` with `(?<![\w-])id(?![\w-])`, not bare substring — run_ids contain hyphens so `\b` is unreliable and a prefix run_id would falsely satisfy a longer one. Gitignored-staging detectives `skip` in clean CI (inputs absent), so the finalize gate is the authoritative prevention layer.

- **(2026-06-07, iterate triage-docs-monorepo-migration)**: **Migrating a MAIN-tree data pile (`triage.jsonl`) via a worktree iterate.** The live curated pile lives in main's working tree (no committed jsonl yet); a worktree off `origin/main` has none. Pattern: GC main's pile in place (`triage_gc --apply` — leak-guard-exempt for `triage.jsonl` per C2's `_MAIN_TREE_WRITE_EXEMPT`, so it doesn't trip f0/f11), then COPY the canonical snapshot into the worktree so F6 ships it in the PR (option b — stays in the normal review flow). **Gotcha:** don't run `update_compliance` to "settle" a producer's keys (e.g. A's signature-only SBOM ids) when no OPEN items of that source remain — the re-emit/dismiss cycle already ran in background, and the run would dirty main's clean compliance MDs (NOT leak-guard-exempt) and STOP the F0 gate. Verify a destructive GC by diff invariants against the `.bak` (removed ⊆ dismissed, 0 open/promoted lost, validator clean), not by trusting the tool's own summary count.

- **ADR-125** (2026-06-05): B7 excludes non-functional Conventional-Commit types (supersedes narrow Rule D)

- **ADR-126** (2026-06-05): Bloat marker + Stop-gate resolve the worktree path to the baseline key

- **ADR-128** (2026-06-05): Enforce the FR-gate on the finalize write-path; D3 accepts same-event delivery

- **ADR-130** (2026-06-05): SBOM cluster dedup-key = signature + manifest_type only

- **ADR-134** (2026-06-05): git-track triage.jsonl via gitignore negation + scaffolder self-heal

- **ADR-136** (2026-06-06): Architecture-drift detection is content reconciliation, enforced by a canon F11 gate

- **iterate-2026-06-10-event-self-id** (2026-06-10): pytest `-m` on the CLI REPLACES the `addopts` marker filter — `-m "not cross_plugin"` silently re-enabled the `slow` suite (D2V concurrency-stress spawners). Always compose: `-m "not slow and not cross_plugin"`.

- **(2026-06-10, iterate finalize-resolver / campaign S3)**: **Don't reuse the global "regenerate ALL derived snapshots" pattern for a PER-ENTITY derived artifact.** The churn resolver re-derives the *global singleton* DERIVED_MDs (one dashboard, one SBOM…) by globbing — safe because there's one of each and they round-trip. Mirroring that for per-campaign `status.json` (glob ALL campaigns on every integrate) was destructive: the projection schema doesn't losslessly round-trip a *legacy* `campaign.md` (bold-id cells parse as new subs → real `complete` subs drop to `pending`/`null`; unknown committed sub-fields stripped), so re-deriving an UNTOUCHED campaign silently corrupted its tracked board. Review caught it (B1) by dry-running the producer against the *real* campaign corpus, not fixtures. **Rule:** scope a merge-time regeneration to the entities the merge actually TOUCHED (here: campaign `status.json` files that CONFLICTED — `complete_merge.resolved` → `integrate_main` → `regenerate_tracked_snapshots(campaign_status_rels=…)`); leave an untouched entity byte-identical and let it self-heal on its own next write (never-downgrade makes that safe). Corollary: verify a producer that runs automatically on shared state against the LIVE data, not a clean fixture — a fixture hides exactly the legacy-shape rows that break round-trip.

- **(2026-06-11, iterate bloat-gate-worktree-baseline)**: **A check that compares a MEASUREMENT to a THRESHOLD must read both from the same tree.** The bloat Stop-gate re-measured the worktree file but read its ceiling from MAIN's baseline — so a worktree iterate that bumped a baseline via ADR (committed in the worktree, not yet on main) false-blocked at Stop, even though pre-commit + CI anti-ratchet (which read the worktree baseline) passed (trg-28e83840; #150/trg-305e2aab had fixed only the path-prefix *key*, not the baseline *source*). **Rule:** when a hook fires with `main_repo_root_or(cwd)` = the MAIN root but the artifact lives under `.worktrees/<slug>/`, resolve any per-tree state (baseline, config) from THAT worktree, falling back to main — never to empty (empty = treat an already-baselined file as a new crossing). Two meta-lessons: (1) a gate is only as correct as the consistency of its two inputs — equal-strength to the CI gate is the bar (verify them against the SAME committed baseline). (2) The bloat-fix iterate itself trips the bloat gate: a worktree fix to worktree-vs-main asymmetry runs under the very machinery it fixes, so dog-foods its own regression — keep the fix file ≤300 or the Stop gate you just fixed will (correctly) flag it.
