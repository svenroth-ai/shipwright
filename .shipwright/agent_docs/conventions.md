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

> **One line per learning, no bold paragraphs** — always-loaded Layer-1 context. Format: `- (YYYY-MM-DD) <phase> — <one-line rule/gotcha>. → <run_id|ADR-NNN>`. **Budget ≤ 600 chars; if a learning won't fit one line it is a *decision* — write an ADR and leave a one-line pointer here.** Enforced repo-agnostically by the F11 verifier + `shared/scripts/tools/check_agent_doc_budget.py`; see `references/reflection.md`. Full rationale for compacted entries is in [`../planning/adr/_archive-agent-doc-updates.md`](../planning/adr/_archive-agent-doc-updates.md).

- (2026-06-16) iterate — compliance Type-column producers read the raw event `intent`, which can carry a leaked free-text description (real class lives in `change_type`) or an adopted repo's git conventional-commit type; normalize at the READER (`shared/scripts/event_classification.normalize_intent`), don't trust the field. A merged-work `passed<total` gap is SKIPPED tests not failures ({passed,total} can't distinguish), so render skip-aware PASS/COVERED, never a gap-driven FAIL — real regressions surface via the open-triage override. → iterate-2026-06-16-compliance-rendering-fixes
- (2026-06-15) iterate — a derived cache consumed at a different lifecycle stage than it's written (SessionStart reads the on-Stop-only `_findings.md` digest) must re-apply the producer's canonical filter at the CONSUMER, not trust cache freshness — esp. for a user-facing signal (a stale digest resurfaced filtered-out sentinel-run FAILs = cry-wolf). Apply count caps AFTER the filter so dropped items can't starve real ones. → iterate-2026-06-15-sessionstart-sentinel-filter
- (2026-06-14) iterate — a prose-only "one-line entry" rule gets ignored unless it's a GATE that runs in every repo: the agent-doc budget was monorepo-pytest-only AND had a date-regex hole (run-id-slug dates parsed as undated → exempt). Fix = shared SSoT (`lib.agent_doc_budget`) + F11 verifier check (ships to adopted repos) + a paren-enclosed-date parser. → iterate-2026-06-14-agent-doc-entry-budget-gate
- (2026-06-14) iterate — a non-greedy `^- \*\*(.+?)\*\*` de-bold regex mangles any entry whose rule text holds an inner `**` (e.g. `client/**` in backticks) — it matches the inner marker as the closing one. Grep the section for stray `**` after a bulk de-bold. → iterate-2026-06-14-agent-doc-entry-budget-gate
- (2026-06-13) iterate — a plugin-local file importing a NEW shared helper must use the helper's UNIQUE top-level name (`from atomic_write import …`), NOT `from lib.atomic_write …`: a plugin that puts its own `scripts/lib` on sys.path poisons the `lib` package name (ADR-044), so `lib.<mod>` ModuleNotFounds under full-suite collection order (green in isolation). Shared-tree files keep `from lib.<mod>`. → iterate-2026-06-13-atomic-write-fsync-durability
- A "read the config to grab one flag" call can be a hidden WRITER: `load_run_config` implicitly runs the legacy-pipeline migration, which persists via `save_run_config` — so reading `standalone` BEFORE acquiring `run_config_lock` performed that migration write UNLOCKED (residual WP2/F11 window, legacy-only/idempotent/atomic). Add a `migrate=False` raw read for migration-invariant fields (`standalone` lives outside `pipeline`/`phase_tasks`); the migration's write then happens on the next in-lock load. (iterate-2026-06-13-runconfig-standalone-read)
- A Claude Code hook must deliver its reason on the channel the EVENT reads, which differs per event: PostToolUse exit-2 → STDERR (stdout is DISCARDED on exit 2); SessionStart → STDOUT `additionalContext` at exit 0, and SessionStart CANNOT block a session. The two security guards emitted JSON on stdout+exit 2 (lost) and the drift gate claimed an exit-1 'hard-gate' SessionStart can't perform (inert). Pin the channel per event with a test that subprocesses the REAL registered hook. (iterate-2026-06-13-hook-block-channel)
- (2026-06-13) iterate — OS advisory file-locks coordinate by lock-file PATH, not shared code: two lock impls mutually exclude iff they target the same `*.lock` path with the same `flock`/`msvcrt` primitive, and on Windows the lock file must stay 0 bytes (`msvcrt.locking` locks at the current offset, so `seek(0)` first). → iterate-2026-06-13-runconfig-atomic-writes
- A hook/CLI whose only real logic lives in `main()` (stdin/env parse, arg wiring) MUST be tested THROUGH `main()` at least once, not only via its pure `run()` core: the phase-session integration suite drove `run()` exclusively, so F1 — `main()` resolved identity from env vars NO launcher sets → the whole v2 lifecycle no-op'd — passed every test undetected. Drive `main()` with a realistic stdin payload + cleared env. (iterate-2026-06-10-phase-hook-lifecycle)
- Relocating a shared symbol to a new home + back-compat re-export: migrate only consumers whose import edit stays net-zero/≤limit; a grandfathered (>300 LOC) consumer must STAY on the re-export — adding a `from <new-home> import …` line ratchets its bloat past baseline (a hard CI gate), and growing other oversized files to chase import purity inverts a bloat-reduction iterate. A lazy (call-time) re-export breaks the home→consumer→home import cycle a module-level one would create. (iterate-2026-06-12-repo-root-resolver-relocate)
- A `from_dict` deserializer must coerce explicit-null via `or []` / `or {}`, NOT `d.get(key, default)` — the default only fires on an ABSENT key, so an event carrying `affected_frs: null` yields None and bricks every downstream consumer (here it crashed the whole compliance MD regen). 2nd occurrence in `collectors/_types.py` after `TestRunEvent.layers`; treat `or <empty>` as the house rule for nullable JSON list/dict fields. (iterate-2026-06-12-workevent-null-frs-coerce)
- The empirical gate enforced depth (asymptote) + breadth (coverage ledger) but not COMPOSITION (do cross-component pieces compose), so FRAMEWORK changes shipped unit-tested-but-integration-unproven (the merge cascade). New `cross_component` flag → required `category:"integration"` behavior at medium+, enforced NON-dodgeably by the F11 verifier RECOMPUTING the flag from the diff (not an agent-report). Detector SSoT in `classify_complexity`, drift-pinned copy in the verifier. (iterate-2026-06-12-cross-component-gate)
- Probe for an executable by TEST-RUNNING it (e.g. `"$c" --version >/dev/null 2>&1`), not `command -v` alone: on Windows `python3` is a Microsoft Store App-Execution-Alias stub that `command -v` finds on PATH but that exits 49 on invocation, so a `command -v`-only resolver under `set -euo pipefail` picks it and aborts at the first real call (`$(python3 -c …)`). `command -v` proves the name resolves, not that it runs. (iterate-2026-06-12-marketplace-python3-stub-probe)
- "Delivered" = the PR is actually MERGED with all Required Checks GREEN, confirmed by watching it to terminal — arming auto-merge (or pushing) and walking away is "shoot and forget"; a check can fail afterward and sit BLOCKED, red, un-merged. F11 runs `watch_pr_delivery.py` and fails closed on anything but merged. Corollary: the `shared/tests` F0 run misses iterate-plugin content-lints (the agent-doc 600-char budget gate), so re-run them after F2/F3a before push. (iterate-2026-06-12-delivery-watch)
- `merge=union` extends past the JSONL append-logs to the curated agent-docs whose `## …Updates`/`## Learnings` sections are bullet-prepended by parallel iterates: a DISTINCT `CURATED_DOC_UNION_PATHS` category keeps both bullets (server-side too), closing the prose half of the cascade the regenerate resolver can't touch; accepted caveat — union is silent on a same-line non-append edit. (iterate-2026-06-12-union-curated-agent-docs)
- A whole-set checker over shared, gitignored, cross-branch-accumulating state must scope to per-tree ownership (run_id in the committed `shipwright_events.jsonl`), and "fail-open when the ownership ledger is absent" is what keeps it from breaking hermetic tests + CI; reproduction needs a tree whose *tracked* state trails the *accumulated* gitignored state, not a clean fork. (iterate-2026-06-12-arch-drift-test-scope)
- A projection over a human-authored markdown skeleton must tolerate inline emphasis, and "verify X regenerates without downgrade" is not a no-op AC. → archive
- The `check_security_scan` PreToolUse:Bash deploy-gate substring-matches its trigger words inside *argument prose*, not just argv[0]. (iterate-2026-06-10-status-projection) → archive
- Tune heuristic classifiers against a harvested real-input corpus, not synthetic guards. (iterate-2026-06-10-complexity-classifier-prior) → archive
- A module loaded by absolute file path (`importlib.util`) that defines a `@dataclass` under `from __future__ import annotations` must be registered in `sys.modules` BEFORE `exec_module`. (iterate-2026-06-07-scaffold-churn-merge-machinery) → archive
- A silently-uncovered test directory hides real, pre-existing failures. (iterate-2026-05-31-ci-gate-guard) → archive
- Always quote `uv run <placeholder>` path arguments in shell snippets. (ADR-020) → archive
- A new `.github/workflows/*.yml` must be Semgrep-clean to merge ITSELF. (2026-06-11, iterate automerge-pr-review / B4.5 Phase 2) → archive
- Hook-installer-style code that detects "already-present" must also upgrade legacy forms in place, not just refuse to add a duplicate. (ADR-019) → archive
- Drift-protection tests across two SSoTs use AST + source-position sort, not substring grep. (iterate-2026-05-03-adopt-env-local-scaffold) → archive
- `.env.local` is the single secrets surface; `.gitignore` enforcement is a hard-stop. (ADR-021) → archive
- Producer/consumer round-trip is the only test that catches format drift. (ADR-024) → archive
- Default permissive on missing-marker guardrails. (ADR-026) → archive
- Idempotent writes preserve audit-trail fields. (ADR-026) → archive
- "Are you confident?" is unfalsifiable; the asymptote heuristic replaces it. (ADR-025) → archive
- `${CLAUDE_PLUGIN_ROOT}` is plugin-context-only. (ADR-030) → archive
- Subprocess tests on Windows must forward `SystemDrive`/`LOCALAPPDATA`/`APPDATA` alongside `SystemRoot`/`USERPROFILE`/`HOME`. → archive
- Pre-push test gates that depend on the marketplace cache must skip pre-push, not fail. (ADR-030) → archive
- Markdown is also a producer/consumer boundary. (ADR-024) → archive
- End-to-End Verification: spec-only authorship counts as no test; the Backend-affects-Frontend rule forces `surface = web` when a diff touches API / store / SSE / WS / message contracts even with no `client/**` file changed. → archive
- Marker scanners need comment-context recognition, not "match anywhere on line". (ADR-041) → archive
- Claude Code hook schemas are per-event, not uniform. (ADR-042) → archive
- Orphan-file detection requires consumer-grep, not git history. (ADR-043) → archive
- PyYAML loses comments — drift tests on workflow files must require ABSENT, not "commented or absent". (iterate-2026-05-10-adopt-ci-scaffolders) → archive
- F0.5 `surface_verification.py --surface cli --runner "..."` execs WITHOUT a shell — the runner must be a single executable, not a compound `cd … && …`. (iterate-2026-06-07-campaign-expands-triage) → archive
- `test_architecture_md_reflects_arch_impact.py::test_arch_impact_drops_found_at_all` is born-fragile against the post-release main-tree state. (iterate-2026-06-07-finalization-tooling-hardening) → archive
- Wiring a previously-CI-less test dir into CI: simulate a clean checkout, don't trust the dev tree. (iterate-2026-05-31-ci-shared-tests) → archive
- Pytest `conftest.py` name collision across plugin dirs. (iterate-2026-05-10-adopt-ci-scaffolders) → archive
- Silent `pytest.skip` on missing binary/import paths must hard-fail in CI. (ADR-044) → archive
- Vestigial `|| true` from a dormant-CI era silently disables gating; sweep for it when hardening. (iterate-2026-05-31-ci-gate-f821) → archive
- Producer auto-resolve reason tokens and `triage_gc.MACHINE_REASONS` are a decoupled SSoT pair — a new producer reason silently escapes the dismissed-pile GC. (iterate-2026-06-07-triage-gc-compliance-refreshed) → archive
- F0.5 `surface_verification.py` runs `--runner` via `shlex.split` + `subprocess.run(shell=False)` — no shell builtins. (iterate-2026-06-03-campaign-status-field) → archive
- A regression guard only counts if it lives in a directory CI actually runs. (iterate-2026-05-31-ci-gate-f821) → archive
- Registry → disk mappings need BOTH directions of drift protection. (iterate-2026-05-11-test-hygiene-and-skill-rules) → archive
- F0.5 cli-surface `--runner` commands must pass `--color=no`. (iterate-2026-05-15-rtm-adopt-worktree-fix) → archive
- Test-Update-Klausel: when an iterate changes test infrastructure (skip semantics, hygiene rules, conventions), the iterate skill's reference rules MUST be updated in the same diff. (ADR-021) → archive
- `pytest.fail`-raising helpers should be annotated `NoReturn`. (ADR-044) → archive
- OneDrive-synced repos + uv hardlink mode = hook subprocess hell. (iterate-2026-05-11-test-hygiene-and-skill-rules) → archive
- Cross-cutting Python helpers go under `shared/scripts/<name>.py`, NOT `shared/scripts/lib/<name>.py`. (iterate-2026-05-11-test-hygiene-helper-and-self-review-wiring) → archive
- AST + tokenize hybrid for source-pattern detection that respects comments. → archive
- Static-probe scope topology, not line geometry. (ADR-045) → archive
- Pre-backlog buffer keeps the WebUI task list curated. (ADR-046) → archive
- Concurrency-correct idempotent append: dedup-scan + write under the same lock. (ADR-046) → archive
- Cross-session dedup needs an explicit "no window" mode. (iterate-2026-05-11-triage-inbox-1a) → archive
- Gitignored test fixtures are absent in fresh worktrees/clones. (iterate-2026-05-16-fix-adopt-review-config) → archive
- A triage `source` is not always a unique producer identity — an auto-resolve pass must scope by the dedup-key shape it owns. (iterate-2026-05-16-fix-triage-dedup-resolve) → archive
- A load-bearing "always" step enforced only by prose gets skipped — convert it to a gate. (iterate-2026-05-16-spec-impact-gate) → archive
- Bash hooks must resolve a Python interpreter — never hardcode `python3`. (iterate-2026-05-18-fix-launch-blocker-tests) → archive
- Test fixtures must not use bare migrated-path words as content markers. (iterate-2026-05-18-phase-quality-check-fixes) → archive
- `check_secrets.sh` flags any `secret`/`password`/`token`-named variable assigned a string literal — test files are NOT exempt. (iterate-2026-05-19-github-triage-importer) → archive
- A Learnings entry that quotes a legacy-path pattern trips the path-canon lint it describes — and F0 runs before F3a, so the trip lands undetected. (iterate-2026-05-19-github-triage-importer) → archive
- An auto-resolving triage producer MUST distinguish a failed fetch from an empty one. (iterate-2026-05-19-github-triage-importer) → archive
- Triage producers importing from systems that already have a per-finding store MUST emit action-units, not finding-mirrors. (iterate-2026-05-20-triage-launch-surface) → archive
- Schema-migration sweeps in fail-soft producers MUST be per-original-source-gated. (iterate-2026-05-20-triage-launch-surface) → archive
- Launch-surface CLI parity contract: the GUI is a thin wrapper over the library, not a parallel implementation. (iterate-2026-05-20-triage-launch-surface) → archive
- Repo-identity resolution for triage producers MUST be local-first (git remote), never via `gh api`. (iterate-2026-05-20-triage-launch-surface) → archive
- Symmetric emit + resolve gates: a producer that emits an action-unit only when N upstream feeds succeeded must ALSO scope auto-resolve to require the same N feeds. (iterate-2026-05-20-triage-launch-surface) → archive
- Render-banner timestamps are a producer/consumer boundary — derive from input data, never from wall-clock. (iterate-2026-05-22-deterministic-render-timestamps) → archive
- Run the external LLM plan review against the *iterate spec + mini-plan*, not only against the diff — the plan is where structural bugs are cheapest to catch. (iterate-2026-05-21-security-artifact-producer) → archive
- Aggregate counters in producer JSON are untrusted — derive from the list. (iterate-2026-05-21-security-artifact-producer) → archive
- Consumer-side synthesis is a valid fallback when canonical producers are uninstrumented. (iterate-2026-05-21-empirical-followups) → archive
- Path-canon lint must allowlist regenerated artifacts that contain plugin-source-tree paths. (iterate-2026-05-21-empirical-followups) → archive
- Artifact contents are untrusted CI output — render aggregated counts only, never raw scanner strings. (iterate-2026-05-21-security-artifact-producer) → archive
- Tracked-but-derived artifacts need a single producer + snapshot-provenance audit, NOT live-render byte-compare. (iterate-2026-05-23-compliance-md-single-producer) → archive
- Avoid `sys.path.insert(0, ".../shared/scripts")` in plugin code — use `audit_adapters.load_shared_lib(name)` instead. (iterate-2026-05-23-compliance-md-single-producer) → archive
- Markdown table rows are also a producer/consumer boundary — but the consumer is the human eye / GFM viewer, not a shipwright parser. (iterate-2026-05-20-escape-md-cells) → archive
- `importlib.metadata` is disqualifying for compliance tooling — its `sys.path` lookup is ambient process state. (iterate-2026-05-23-sbom-resolver-pin-lockfile) → archive
- Filesystem glob enumeration of `*-VERSION.dist-info` directories must sort by parsed version, NOT lexicographic. (iterate-2026-05-23-sbom-resolver-pin-lockfile) → archive
- Skip-dir patterns for source walkers must distinguish "tool output at root" from "directory name nested under source". (iterate-2026-05-25-bloat-foundation) → archive
- Hook-budget vs message-content tension: long-form error messages are bytes-on-disk that count toward LOC. (iterate-2026-05-25-bloat-foundation) → archive
- Self-eating-dogfood signal: the new gate firing on its own author is a smoke test, not a failure. → archive
- Runtime/snapshot split generalises the single-producer pattern when the artifact carries iterate-specific context. (iterate-2026-05-27-tracked-artifacts-single-producer-and-finalize-sandbox) → archive
- A finalize sandbox-escape via stale session→worktree pointer is the second-most-common single-producer failure mode after "two producers." → archive
- Idle-main producers must resolve `main_repo_root` (never `Path.cwd()`) AND write transient state only to gitignored paths. (iterate-2026-06-09-idle-main-artifact-hygiene) → archive
- Branch integration: `git merge`, not `git rebase`, for Run-ID-bearing branches. → archive
- Audit-coverage extension to docs added AFTER the last snapshot needs a "not-in-snapshot" semantic, not a stale verdict. → archive
- Splitting an allowlisted monolith into a package MUST migrate its `artifact_migrations.py` ALLOWLIST entry to a package glob in the same diff. (iterate-2026-05-29-fix-path-canon-allowlist) → archive
- A "worktree-aware" abstraction built for one failure mode can become the bug for a later workflow — confirm the full blast radius before flipping it. (iterate-2026-05-29-events-jsonl-worktree-commit) → archive
- An SHA assigned by a commit cannot be patched back into a file that same commit just committed without re-dirtying it — drop the back-patch, don't add a second commit. (iterate-2026-05-29-events-jsonl-worktree-commit) → archive
- A patch that "rides inline" with a campaign silently vanishes unless the campaign's sub-iterate plans explicitly name it. (iterate-2026-05-29-sp3-os2-reintegration) → archive
- (2026-06-12) iterate — When making a routing oracle impact-aware, read ALL candidate target docs unconditionally; checking only an impact's primary target silently breaks a cross-target legacy fallback (the convention→architecture.md fallback false-failed until both docs were loaded). → iterate-2026-06-12-agent-doc-entry-rules.
- When compacting an always-loaded doc to one-line pointers, an entry pinned by a drift-protection test is load-bearing — keep its pinned phrases inline, don't archive them away. Blanket bolded-lead compression dropped the E2E learning's "Backend-affects-Frontend" sub-rule that `test_skill_e2e_gate_consistency.py` requires in conventions.md. Grep every test that reads the doc for asserted phrases BEFORE compressing. → iterate-2026-06-12-compress-agent-doc-backlog.
- GitHub auto-merge runs a server-side 3-way merge and CANNOT run the regenerate-at-merge resolver — safe ONLY for a single iterate whose branch is current. Parallel/concurrent iterate PRs that each commit regenerated snapshots cascade `DIRTY` (snapshot conflict → auto-merge stalls) or merge stale (Group-E); bring a branch current THROUGH `integrate_main` (the `ensure_current.py` refresh-if-behind guard) BEFORE it merges. (iterate-2026-06-12-automerge-serial-integrate) → decision_log (Run-ID).
- An iterate's base is the worktree (clean `origin/main`), not the dirty main working tree — re-baseline scouting there before editing. A task-named `drift_anchor.py` target was only uncommitted main-tree WIP, absent from `origin/main`; write the multi-site drift-guard test first — its collection error exposes phantom targets. (iterate-2026-06-12-canonical-project-predicate) → decision_log (Run-ID).
- (2026-06-13) iterate — doc-drift findings from an older audit must be re-verified against current HEAD before fixing: intervening merges (audit waves, the guide.md correctness PRs) shift the shipped reality the doc must match; reconcile to code, not the audit's snapshot. → iterate-2026-06-13-docs-ssot-reconcile.
- (2026-06-13) iterate — a behavior-snapshot/verify gate only catches drift the test suite COVERS: a probe mutating an un-covered path passes green, so the gate must hard-reject removed coverage and pair with non-mechanical reasoning (Chesterton-Fence + Five Principles), never stand alone. Also: a synthetic-project CLI test must set `PYTHONDONTWRITEBYTECODE` or a same-second source rewrite reuses a stale `.pyc` and masks the drift. → iterate-2026-06-13-code-simplify-skill.
- (2026-06-13) iterate — adding code to a shared lib already AT/near 300 LOC trips the new-crossing bloat Stop-gate mid-edit (its own writer fires); trim or split in the SAME iterate. Don't baseline a file that's only AT 300 (not over) — the baseline grandfathers OVER-limit files, so 300==limit needs a real reduction, not an allowlist entry. → iterate-2026-06-13-bloat-marker-writer-baseline.
- (2026-06-13) iterate — `integration-tests/` INHERITS the root `addopts = -m 'not slow'`, and CI's integration step (`pytest integration-tests/ -v`, no `-m`) inherits it too — so a subprocess-spawning integration test marked `@pytest.mark.slow` is SILENTLY DESELECTED in CI (never runs). Leave such tests UNMARKED (the `test_shipwright_run_e2e.py` convention); reserve `slow` only for the genuinely-too-slow few. The per-plugin CI step has no `-m` filter, so a plugin-dir slow test DOES run there — the rule is dir-specific. → iterate-2026-06-13-unify-simplify-reducibility.
- (2026-06-14) iterate — an autonomous-loop phase-quality Tier-1 FAIL can be a STALE degenerate-context artifact: a `run_id=unknown` snapshot (audit with no resolvable run/session) frozen before its audit-time guard landed, re-rendered by the rollup readers. Run a fresh audit before "fixing" the symptom — here it yielded ZERO FAILs. Write-time guards don't clear on-disk pre-fix snapshots; the durable fix is read-layer (`load_actionable_findings` excludes sentinels). → iterate-2026-06-14-phasequality-sentinel-rollup-filter.

---

## Contributing

Contribution rules, dev setup, the graduated trust model, and high-sensitivity areas live in the root [`CONTRIBUTING.md`](../../CONTRIBUTING.md) — the single source of truth. (Previously copied here verbatim by /shipwright-adopt; replaced with this link to keep always-loaded Layer-1 context lean — iterate-2026-06-12-agent-doc-entry-rules.)

## Convention Updates
> **One line per change** — always-loaded Layer-1 context. Format: `- **<run_id|ADR-NNN>** (YYYY-MM-DD): <one sentence>. → decision_log (Run-ID/ADR)`. **Budget ≤ 600 chars; detail goes in the ADR, not here.** Routed here for `convention`-impact entries (`component`/`data-flow` → `architecture.md`); enforced repo-agnostically by the F11 verifier + `shared/scripts/tools/check_agent_doc_budget.py`. See `references/F2.md`.
- **iterate-2026-06-16-compliance-rendering-fixes** (2026-06-16): Convention — Type-column compliance producers (RTM Verification Timeline, Build Dashboard) MUST route the event `intent` through `shared/scripts/event_classification.normalize_intent`; completed-work `passed<total` renders skip-aware PASS/COVERED (never a gap-driven FAIL — real regressions surface via the open-triage override); the dashboard links the audit report UNCONDITIONALLY (gitignored/transient → a conditional link flip-flops). → decision_log (Run-ID).
- **iterate-2026-06-17-launch-version-branding** (2026-06-17): Convention — all 13 plugins + `marketplace.json` now carry ONE shared version (0.29.0), bumped in lockstep at release; per-plugin independent SemVer retired. Maturity label is "Beta" (not "Early Access Beta"). → decision_log (Run-ID).
- **iterate-2026-06-14-hook-fanout-dedup** (2026-06-14): Convention — cross-cutting Claude-Code hook fan-out deduped symmetrically (no single controlling plugin): register-everywhere kept, genuinely-redundant work wrapped in a fail-open once-per-(event,session) guard (`event_once.claim_once_for_event`) on the audit/handoff/drift hooks; the phase-quality Stop audit resolves engaged phase(s) from session state (`resolve_engaged_phases`) not `CLAUDE_PLUGIN_ROOT`. → decision_log (Run-ID).
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
- **iterate-2026-05-23-verifier-multi-commit-aware** (2026-05-23): three iterate-skill discipline lessons — (1) TDD RED-first applies to drift-protection tests (the RED phase is the proof the test discriminates); (2) run `check_iterate_isolation.py --stage f0` at finalization start, symmetric with `--stage f11`; (3) `--architecture-impact` and the doc bullet are structurally coupled (silent drift otherwise), now gated by `test_architecture_md_reflects_arch_impact.py`. → decision_log (Run-ID).
- **Drift-protection meta-pattern** (2026-05-23): a prose-only convention's historical drift is only findable by a mechanical test enumerating every governed artifact, written RED-first against current state (the architecture-md test surfaced 9 historical drift entries); keep it as a forward gate. → `shared/tests/test_architecture_md_reflects_arch_impact.py`.
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
- **(2026-06-05, iterate gitleaks-report-path)**: gitleaks `--report-path -` writes a literal file named `-`, NOT stdout — read the JSON from a real temp file. A "detects on Windows, 0 on Linux CI" story can be a measurement artifact: verify the exact wrapped command's output channel against the real binary before concluding platform divergence. → decision_log (Run-ID)
- **(2026-06-06, iterate arch-drift-detector)**: a drift detector that diffs the git HISTORY of gitignored inputs (decision-drops) can never fire — reconcile the staging CONTENT against the tracked artifact instead; share ONE oracle between the detective and its finalize gate; a prose-only "always update X" step with no live gate WILL drift, so convert it to a canon gate. → decision_log (ADR-136 via Run-ID)
- **(2026-06-07, iterate triage-docs-monorepo-migration)**: migrate a MAIN-tree data pile via a worktree iterate by GC-ing main's pile in place (leak-guard-exempt) then copying the canonical snapshot into the worktree so F6 ships it; don't run `update_compliance` when no OPEN items of that source remain (it dirties main's clean compliance MDs and STOPs F0); verify a destructive GC by diff invariants against the `.bak`. → decision_log (Run-ID)
- **ADR-125** (2026-06-05): B7 excludes non-functional Conventional-Commit types (supersedes narrow Rule D)
- **ADR-126** (2026-06-05): Bloat marker + Stop-gate resolve the worktree path to the baseline key
- **ADR-128** (2026-06-05): Enforce the FR-gate on the finalize write-path; D3 accepts same-event delivery
- **ADR-130** (2026-06-05): SBOM cluster dedup-key = signature + manifest_type only
- **ADR-134** (2026-06-05): git-track triage.jsonl via gitignore negation + scaffolder self-heal
- **ADR-136** (2026-06-06): Architecture-drift detection is content reconciliation, enforced by a canon F11 gate
- **iterate-2026-06-10-event-self-id** (2026-06-10): pytest `-m` on the CLI REPLACES the `addopts` marker filter — `-m "not cross_plugin"` silently re-enabled the `slow` suite (D2V concurrency-stress spawners). Always compose: `-m "not slow and not cross_plugin"`.
- **(2026-06-10, iterate finalize-resolver / campaign S3)**: don't reuse the global "regenerate ALL derived snapshots" pattern for a per-entity artifact — scope a merge-time regeneration to the entities the merge actually TOUCHED (conflicted campaign `status.json`), leaving untouched ones byte-identical (never-downgrade self-heals); verify an auto-running producer against LIVE data, not a clean fixture. → decision_log (ADR-160 via Run-ID)
- **(2026-06-11, iterate bloat-gate-worktree-baseline)**: a check comparing a MEASUREMENT to a THRESHOLD must read both from the same tree — the bloat Stop-gate re-measured the worktree file but read its ceiling from MAIN's baseline, false-blocking a worktree baseline bump. Resolve per-tree state (baseline/config) from the worktree, fall back to main, never to empty. → decision_log (ADR-126 via Run-ID)
- **(2026-06-11, iterate automerge-gh-pr-ci-producer)**: a PR-checks producer must treat `len(check_runs) < total_count` as a truncated view (return None, don't classify on a partial set) and pass `?filter=latest` (else a superseded failed run re-reddens a fixed PR); a session-autouse network stub also shadows the unit tests OF those fns — expose `real_*` opt-back-in fixtures. → decision_log (Run-ID)
- **(2026-06-11, iterate automerge-f11-arm)**: a pipeline step depending on an out-of-band repo/infra setting must be fail-soft (`|| echo WARN`, never `|| exit`) or it breaks the pipeline for everyone the moment the setting is off; self-modifying plugin changes don't take effect this run (ship in a PR; future iterates get it); gate behavior on the actual branch name, not an assumption. → decision_log (ADR-165 via Run-ID)
- **(2026-06-12, iterate triage-status-idle-main-outbox)**: a routing rule keyed off a context predicate must cover EVERY write verb (append/status/delete/promote) — `mark_status` was left residence-derived after appends were routed to the outbox, re-introducing idle-main drift; to test a predicate that probes git state, the fixture MUST build a real repo WITH an origin remote. → decision_log (ADR-189 via Run-ID)
- **iterate-2026-06-12-utf8-churn-merge** (2026-06-12): strict UTF-8 round-trip in `resolve_churn_conflicts._git` + structured commit-failure handling in `integrate_main` (no mojibake / MERGE_HEAD wedge on cp1252). → decision_log (Run-ID; ADR-099 amendment).
- **iterate-2026-06-12-agent-doc-entry-rules** (2026-06-12): agent-doc update entries are one-line ADR pointers, routed by `lib.architecture_doc.IMPACT_TARGETS` (convention → here; component/data-flow → architecture.md `## Architecture Updates`) and capped by a forward-only 600-char budget gate; the oracle (F11 gate + Group-F detective) checks each impact against its target doc. → decision_log (Run-ID).
- **iterate-2026-06-12-triage-tooling-hardening** (2026-06-12): Convention — deep-audit WP9 triage-tooling hardening: `triage_gc.MACHINE_REASONS` gains `phaseQualityRefreshed` (+ a forward/reverse drift meta-test); `apply_gc` recomputes the droppable set under-lock ∩ the caller's planned ids (honors a concurrent re-open); `_strip_control_chars` is wired into title/detail/evidence incl. the C1 range; `triage_promote` relaxes its existence pre-check to tracked-OR-outbox. Campaign `2026-06-10-audit-1-auto`. → archive
- **iterate-2026-06-12-triage-gc-union-residence** (2026-06-12): Convention — a1-6/F19 follow-up: `apply_gc`'s under-lock recompute is now union-residence aware (`read_all_items`, tracked ∪ outbox) so an outbox-routed re-open survives GC (D1: report tracked-only, only the tracked file rewritten). The source-derived drift meta-test adds the missing `prChecksResolved` + allowlists the `auditResolved` orphan; `_strip_control_chars` → `shared/scripts/lib/tty_sanitize.py`. Campaign `2026-06-10-audit-1-auto`. → decision_log (Run-ID).
- **iterate-2026-06-11-automerge-f11-arm** (2026-06-11): Convention — `/shipwright-iterate` F11 arms GitHub-native auto-merge after `gh pr create` (`gh pr merge --auto --squash --delete-branch`) for `iterate/*` PRs only (a `case` branch-scope guard) and fail-soft (`||`-guarded WARN, never `|| exit`). B4.5 Phase 3; `trg-bdc160e2`. Drift: `test_f11_automerge_arm.py`. → archive
- **iterate-2026-06-11-automerge-pr-review** (2026-06-11): Convention — new CI workflow `.github/workflows/pr-review.yml` gates external-contributor / sensitive-path / `needs-review` PRs through an OpenRouter LLM review before auto-merge (Tier 1/2 PRs are NOT reviewed at the PR stage); logic in shipwright-security `pr_review.py` + `pr_review_lib.py` (stdlib urllib, ≤300 LOC each); required check `PR Review`. B4.5 Phase 2. → archive
- **iterate-2026-06-11-backfill-docs** (2026-06-11): Convention + docs — closes campaign `2026-06-07-tracked-campaign-status` (S4, anchor `trg-fda5f7a3`): `parse_campaign_skeleton` strips wrapping markdown emphasis from id/slug cells (else a legacy bold-id `campaign.md` drops completed subs on re-projection); new read-only drift-guard `test_campaign_status_backfill.py`; glossary + hooks-and-pipeline docs landed. → archive
- **iterate-2026-06-11-spec-path-relative** (2026-06-11): Convention — campaign sub-iterate `spec_path` is now repo-relative POSIX (not a machine-absolute Windows path) so the WebUI + fresh clones resolve it portably; new pure module `shared/scripts/lib/campaign_paths.py` (`relativize_spec_path` / `campaign_spec_path`); producers write relative + the projection self-heals; a one-off migration rewrote all 7 tracked campaigns. `trg-196f4aa6` (N1). → archive
- **iterate-2026-06-10-complexity-classifier-prior** (2026-06-10): Convention + data-flow — the iterate Stage-1 complexity classifier's fall-through default is history-calibrated: with no scope-keyword match, `classify()` reads the last ≤20 F5c entries and uses their median final complexity (clamped to medium); `signals.prior_source` surfaces `keyword|history|default`. Scope keywords moved to `complexity_vocabulary.py` (alnum-boundary + optional-plural). → archive
- **iterate-2026-06-10-d2v-evidence-write-optin** (2026-06-10): Convention — the D2V empirical-gate evidence artifact (`D2V-empirical-results.md`) is regenerated only on opt-in (`SHIPWRIGHT_D2V_WRITE_EVIDENCE`): `_d2v_helpers.Evidence.flush()` early-returns otherwise (the gate assertions still run). Ends the dirty-tree / manual-revert churn that hit 3 consecutive iterates. → archive
- **iterate-2026-06-10-triage-list-json** (2026-06-10): Convention — new machine-readable contract `triage_cli.py list --json` for the Command Center WebUI live-view: emits the unioned open items (`triage.read_all_items`, tracked ∪ outbox) as a JSON array, each enriched with `pendingDelivery: true` iff the item lives only in the gitignored outbox (TRACKED-PREFERRED). Read/output surface only. `trg-e2a0ebb3`. → archive
- **iterate-2026-06-09-audit-report-hygiene** (2026-06-09): Convention — the compliance detective-audit writer relocates `shipwright_audit_report.json` from the repo ROOT to `.shipwright/compliance/audit-report.json` (re-excluded in the gitignore canon, propagating to adopted repos); the stdout JSON stays the stable contract. Same ADR-089 leak class as idle-main-artifact-hygiene. PR #174. → archive
- **iterate-2026-06-09-external-review-marker-gitignore** (2026-06-09): Convention — the gitignore canon re-excludes the transient external-review gate markers under `.shipwright/planning/iterate/**/external_*review_state.json` (run-scoped, NOT RTM evidence — `rtm.collect_external_review_states` skips `planning/iterate/`); it deliberately does NOT touch the durable `planning/<split>/` evidence. Near-miss guard via a real `git check-ignore` round-trip. → archive
- **iterate-2026-06-09-idle-main-artifact-hygiene** (2026-06-09): Convention — completes ADR-089 for two idle-`main` producers: new `shared/scripts/lib/repo_root.py::main_repo_root_or` (the bloat marker writer + reader resolve the canonical main root, not `Path.cwd()`); the 3 phase-quality `skill-compliance` roll-ups relocate under the already-gitignored `skill-compliance/`; new canon rule `**/.shipwright/locks/`. PR #173. → archive
- **iterate-2026-06-07-scaffold-churn-merge-machinery** (2026-06-07): Convention — the append-log `merge=union` `.gitattributes` driver is scaffolded into every managed repo: new SSoT `gitattributes-union.template` + `shared/scripts/lib/gitattributes_union.py` (`UNION_PATHS`, `merge_into`, `self_heal_gitattributes`); adopt Step E.13c + `setup_iterate_worktree` self-heal. New write-surface: the target repo root `.gitattributes`. → archive
- **iterate-2026-06-07-sbom-not-installed-vs-undeclared** (2026-06-07): Convention — the SBOM license resolver distinguishes `NOT_INSTALLED` (a scan-environment property — silent, rendered `-`, excluded from counts/verdict) from `UNKNOWN_LICENSE` (a real triage finding + `sbom.md` concern). New sentinels in `collectors/_license_const.py`; producer-side so it generalizes to every repo. Reverses ADR-056 for the not-installed case. → archive
- **iterate-2026-06-07-adopt-gitleaks-allowlist** (2026-06-07): Convention — /shipwright-adopt scaffolds a companion `.gitleaks.toml` allowlist alongside `security.yml` (Step E.13b, new `gitleaks_config_scaffolder`); the deployed path + template are declared as SSoT constants in `security_workflow.py`, pinned by `test_gitleaks_config_convention.py`. Stops every adopted repo's first scan false-redding on the `cafebabe:deadbeef` placeholder. PR #163. → archive
- **iterate-2026-06-08-outbox-delivery-d3** (2026-06-08): Convention — the canonical `.shipwright/` artifact-ignore block (incl. `/.shipwright/triage.outbox.jsonl`) is self-healed into every adopted / stale-cache repo on its next iterate via new `lib/gitignore_selfheal.self_heal_gitignore` (sibling of `self_heal_gitattributes`), wired into `setup_iterate_worktree` step 4.6 as a guarded `chore` commit. Campaign `2026-06-08-triage-outbox-delivery` D3. → archive
- **iterate-2026-06-10-canon-exempt-agent-doc-caches** (2026-06-10): Convention — the ADR-089 single-producer agent-doc trio (`triage_inbox.md` + `session_handoff.md` + `build_dashboard.md`) is exempt from the `artifact-path-canon` Layer-1 lint in all 4 `ALLOWLIST` migrations (they render free-form text that may quote any legacy path + are regenerated each iterate). Drift-locked by `test_generated_cache_canon_exempt`. Closes `trg-6ed063ae`. → archive
- **iterate-2026-06-12-compress-agent-doc-backlog** (2026-06-12): Convention — compacted the always-loaded agent-doc backlog to one-line pointers: architecture.md `## Architecture Updates` (component/data-flow only; `convention` entries migrated here), conventions.md `## Convention Updates` (+16 migrated) and `## Learnings` (verbatim detail archived under `.shipwright/planning/adr/_archive-agent-doc-updates.md`). Retired the `_LEGACY_CONVENTION_DOC` fallback in `architecture_doc.py` and lowered the entry-budget gate cutoff to 2026-05-01. → decision_log (Run-ID).
- **iterate-2026-06-12-canonical-project-predicate** (2026-06-12): Convention — the greenfield/foreign boundary is now a single canonical predicate `lib.project_root.is_shipwright_project` (any config marker OR `.shipwright/agent_docs/`; fail-closed) that every hook delegates to, collapsing 4 divergent marker sets so a tree is classified identically everywhere; `resolve_project_root` gains a config-subdir tie-break. Drift-guard `test_canonical_project_predicate.py`. PR #209. → decision_log (Run-ID).
- **iterate-2026-06-12-w2-unresolvable-runid-skip** (2026-06-12): Convention — every run_id-keyed phase-quality verifier must share the `unresolvable_run_id_skip` guard (`tools/verifiers/_iterate_run_id.py`): a sentinel run_id (`unknown`/empty) with no run-specific marker SKIPs as not-applicable, never FAIL/PASS on the run-agnostic state file. W2 was the asymmetric outlier vs S2/S3 → recurring audit-context Tier-1 false-positive. Drift-guard `test_workflow_w2_run_id_guard.py`. → decision_log (Run-ID).
- **ADR-143** (2026-06-07): Adopt scaffolds .gitleaks.toml + hardens security.yml.template
- **ADR-147** (2026-06-07): SBOM splits 'not installed' from 'no declared license'
- **ADR-148** (2026-06-08): Scaffold append-log union merge driver into managed repos
- **ADR-152** (2026-06-08): Explicit outbox gitignore propagation + iterate self-heal
- **ADR-153** (2026-06-09): Relocate detective-audit JSON under .shipwright/compliance/ so the gitignore canon covers it
- **ADR-154** (2026-06-09): Iterate-scoped external-review markers are gitignored (not blanket)
- **ADR-155** (2026-06-09): Idle-main producers resolve main_repo_root + write transient state only to gitignored paths
- **ADR-156** (2026-06-10): Generated agent-doc cache trio fully exempt from artifact-path-canon (finalize trg-6ed063ae)
- **ADR-157** (2026-06-10): History-calibrated complexity prior + cross-domain scope vocabulary
- **ADR-158** (2026-06-10): D2V evidence artifact write is opt-in (SHIPWRIGHT_D2V_WRITE_EVIDENCE)
- **ADR-159** (2026-06-10): Campaign sub-iterates self-identify via event extras stamp
- **ADR-164** (2026-06-10): triage_cli.py list --json: machine-readable contract for the WebUI live-view
- **ADR-165** (2026-06-11): F11 arms GitHub-native auto-merge for iterate/* PRs
- **ADR-167** (2026-06-11): Tier-3 PR review via OpenRouter custom-script
- **ADR-168** (2026-06-11): Campaign skeleton tolerates markdown emphasis; backfill drift-guard
- **ADR-171** (2026-06-11): Campaign sub-iterate spec_path is repo-relative POSIX
- **ADR-172** (2026-06-12): Compact agent-doc entries + impact-aware routing SSoT
- **ADR-176** (2026-06-12): Single canonical Shipwright-project predicate
- **ADR-179** (2026-06-12): Compact agent-doc backlog + retire convention-routing fallback
- **ADR-188** (2026-06-12): triage_gc under-lock recompute is union-residence aware
- **ADR-190** (2026-06-12): Triage tooling hardening: GC token SSoT, GC TOCTOU, control-char sanitizer, outbox CLI
- **ADR-192** (2026-06-12): UTF-8-strict churn _git + structured commit-failure handling
- **ADR-222** (2026-06-14): Hook fan-out deduped via once-per-event guard + session-state phase resolver
- **ADR-227** (2026-06-16): Skip-aware compliance rendering + centralized intent normalization
- **ADR-230** (2026-06-17): Unify all plugin/marketplace versions to 0.29.0; relabel Early Access Beta to Beta
