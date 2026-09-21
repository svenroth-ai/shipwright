# Mini-Plan: codex-plugin-bundle-root-contract

- **Run ID:** iterate-2026-09-20-codex-plugin-bundle-root-contract

## 1. Files to create/modify

New:
- `shared/scripts/lib/plugin_root.py` — canonical resolver: `SHIPWRIGHT_PLUGIN_ROOT` env → `CLAUDE_PLUGIN_ROOT` env → `PLUGIN_ROOT` env (Codex native, checked last — doubt-review, 2026-09-20: reordered after this plan was written, see the iterate spec's Confidence Calibration item 2 for why) → raise. One function, `resolve_plugin_root() -> Path`.
- `shared/scripts/tools/build_codex_plugin.py` — deterministic builder: reads the 14 `plugins/*/.claude-plugin/plugin.json` + `hooks/hooks.json` + `skills/` + `scripts/`, plus `shared/` (excluding `shared/tests/`, `__pycache__`, `.venv`), and emits a single `.codex-plugin/plugin.json` + copied tree under a build-output directory (default `dist/codex-plugin/`, gitignored). Also emits `.agents/plugins/marketplace.json` for local install. Writes a build manifest (bundled-relative-path→sha256 map — corrected from an earlier "source→bundled-file map" description; the verifier re-derives source provenance via fresh rebuild-and-diff rather than trusting a stored source mapping, external code review 2026-09-20) alongside the bundle for the verifier to consume.
- `shared/scripts/tools/verify_codex_plugin_bundle.py` — drift/verifier: (a) clean-rebuild-has-no-diff, (b) every bundled file traceable to a declared source (no path escape, no undeclared generated content), (c) staleness (source newer than bundle manifest hash), (d) hook-manifest dedup/collision check per event.
- `shared/tests/test_plugin_root.py`, `shared/scripts/tools/tests/test_build_codex_plugin.py`, `shared/scripts/tools/tests/test_verify_codex_plugin_bundle.py` — TDD, written first.
- `dist/.gitignore` (or an entry in the root `.gitignore`) excluding `dist/codex-plugin/`.

Modify:
- `shared/scripts/hooks/capture_session_id.py` — use `resolve_plugin_root_str()` instead of the bare `os.environ.get("CLAUDE_PLUGIN_ROOT", "")` at line 75.
- `shared/scripts/hooks/audit_phase_quality_on_stop.py` — same migration (foreign-plugin recognition gate at line 73).
- `shared/scripts/hooks/audit_compliance_on_stop.py` — same migration (foreign-plugin recognition gate at line 146).
- `shared/scripts/tools/generate_session_handoff.py` — checked; its only `PLUGIN_ROOT` reference is a docstring usage example, not a live read — no migration needed.
- `plugins/shipwright-build/scripts/hooks/cleanup-review-scratch-on-code-reviewer-failure.py` — **not migrated to the shared import**, but its `resolve_shared_root()` DOES gain the `CLAUDE_PLUGIN_ROOT` fallback. This script avoids importing `shared/` per its own documented ADR-044 self-containment constraint (cross-plugin `lib.` imports risk a pytest sys.path collision across plugin test roots), so it inlines the same precedence instead. Correction (doubt-review, 2026-09-20): this plan originally claimed reading `SHIPWRIGHT_PLUGIN_ROOT` alone was sufficient because `capture_session_id.py`'s own SessionStart injection "has already resolved and exported the value by then" — false, `additionalContext` is model-visible text, not an OS environment export, so this hook was permanently dark in production without the inline fallback.
- `docs/hooks-and-pipeline.md` — note the new canonical resolver and that `SHIPWRIGHT_PLUGIN_ROOT` is now framework-owned per M2 (required in the same diff per `CLAUDE.md`'s hook-change rule, even though no `hooks.json` itself changes — this is a startup-context-read change for the 3 modified scripts).
- `shared/prompts/writing-plugin.md` — add a short "Codex bundle" pointer so future plugin-side changes know a second sync step now exists (build_codex_plugin.py), without duplicating the full procedure.

## 2. Work breakdown (medium)

1. **Resolver first (TDD).** Write `test_plugin_root.py` covering: `SHIPWRIGHT_PLUGIN_ROOT` already set (wins outright), only `PLUGIN_ROOT` set, only `CLAUDE_PLUGIN_ROOT` set, both `PLUGIN_ROOT` and `CLAUDE_PLUGIN_ROOT` set (CLAUDE_PLUGIN_ROOT wins — reordered under doubt-review, 2026-09-20, after this plan was written; see the iterate spec's Confidence Calibration item 2), neither set (raises a clear error). Then implement `plugin_root.py`. Test expectation: 100% branch coverage of the precedence order.
2. **Migrate the real call site(s) that actually need it.** SUPERSEDED — see §1 and AC3: all 3 of `capture_session_id.py`, `audit_phase_quality_on_stop.py`, and `audit_compliance_on_stop.py` read `CLAUDE_PLUGIN_ROOT` directly and needed migrating to the shared resolver (this line originally undercounted the scope to just the first); `generate_session_handoff.py`'s reference was docstring-only, and `cleanup-review-scratch-on-code-reviewer-failure.py` is excluded by its own ADR-044 constraint and inlines the fallback instead (see §1 above). Test expectation: all 3 migrated call sites' own existing test suites still pass unchanged (regression, AC3), plus a new test per site pinning the Codex-native `PLUGIN_ROOT` path.
3. **Fixture the three real cache shapes** (monorepo `plugins/<name>/scripts/...`, Claude cache `.../cache/shipwright/<plugin>/<version>/...`, Codex cache `.../plugins/cache/<marketplace>/<plugin>/<version>/...` — the last one now known-correct from the live probe) and prove the resolver returns the plugin's own root under all three when only the corresponding env var is set. Test expectation: one parametrized test, 3 cases (AC2).
4. **Builder (TDD).** Write `test_build_codex_plugin.py` first: given a small fixture source tree (2-3 fake plugins + a fake `shared/`), the builder emits the expected `.codex-plugin/plugin.json` shape (inline `hooks.hooks.<Event>`, `skills: "./skills/"`), copies files, and a second run with no source change produces byte-identical output (AC4). Then implement against the real 14-plugin + `shared/` tree.
5. **Hook manifest generation.** Within the builder: read all 14 `hooks.json` files, normalize into one inventory (event, matcher, command, source plugin), dedupe exact-duplicate command lines per event (several hooks are registered once per plugin by convention — see `shared/prompts/writing-plugin.md`), and emit the deduped inventory as the bundle's inline hook object. Test expectation: a fixture with a deliberately duplicated hook command across two fake plugins collapses to one entry; a fixture with two *different* commands on the same event for the same conceptual step is surfaced as a collision (recorded, not silently resolved — this iterate does not attempt the real M3 ordering/dispatcher, only detects the shape it will need).
6. **Path rewriting.** Bundled hook commands currently read `${CLAUDE_PLUGIN_ROOT}/../../shared/scripts/...` (cache-topology-specific). Inside the bundle, `shared/` is copied to a fixed path relative to the bundle root — rewrite these to a bundle-relative form (or to call the new resolver + a documented bundled-shared-path convention) so the bundle is self-contained per M1 ("no skill depends on `~/.claude/plugins/cache`"). Test expectation: after rewriting, no bundled hook command string contains `../../` (AC1's "no skill depends on..." half, verified structurally).
7. **Drift/verifier (TDD).** `test_verify_codex_plugin_bundle.py`: stale bundle (touch a source file, don't rebuild) → fail; untracked file inserted into the bundle output → fail; clean rebuild → pass. (AC5)
8. **Local marketplace + live probe.** Point `codex plugin marketplace add` at the real build-output directory, `codex plugin add`, and re-run the skill-discovery introspection prompt used during Repo Scout, this time expecting every real Shipwright skill name to appear (not just one toy skill). Clean up (`codex plugin remove` + `marketplace remove`) afterward, same as the probe. Capture the transcript as evidence (AC1, live).
9. **Regression check.** Full existing shared + plugin test suites still green; `.claude-plugin/marketplace.json` and all 14 `plugins/*/.claude-plugin/plugin.json` unchanged (`git diff --stat` shows zero touched lines in those paths). (AC6)
10. **Docs.** Update `docs/hooks-and-pipeline.md` (resolver is now framework-owned) and `shared/prompts/writing-plugin.md` (pointer to the new bundle-build step) per M11's own minimal-delta carve-out.

Each step's test runs before moving to the next (TDD Red-Green-Refactor per SKILL.md Step 6).

## 3. Component hierarchy

n/a — no UI.

## 4. Data model changes

None.

## 5. Test strategy

- Unit: `shared/tests/test_plugin_root.py` (resolver, parametrized 3-cache-shape fixture), `shared/scripts/tools/tests/test_build_codex_plugin.py`, `shared/scripts/tools/tests/test_verify_codex_plugin_bundle.py`.
- Regression: full `shared/tests/` + `shared/scripts/tools/tests/` + the 3 modified call sites' own existing plugin test suites.
- Live/manual (CLI surface, not CI-enforced — `e2e (inferred)` in the FR row): the local-marketplace install + skill-discovery probe against the real built bundle, using the real Codex CLI available in this environment. Not automated in CI because CI runners have no authenticated Codex CLI; this matches the parent spec's own "Hermetic CI uses captured schemas... never needs a signed-in agent account" principle — the fixtures in step 3 above are what CI actually gates on.
- No E2E web verification: no dev server surface exists for this change (Verification: surface=cli).

## 6. Alternative approach (medium)

**Considered and rejected: commit the built bundle into the repo instead of gitignoring it.**
Would make the bundle directly installable from a bare git checkout without a build step, which is attractive for `Spec/codex-runtime-integration-spec.md` §7's own eventual "publish through the supported plugin directory" (Slice 5). Rejected for this iterate because: (a) M1's own text is explicit — "Do not commit a mutable machine cache. Commit source, build definition, and stable package metadata" — a generated multi-hundred-file copy of 14 plugins + `shared/` is exactly the kind of drift-prone generated artifact `CLAUDE.md`'s "where documents live" section says does not get committed among hand-written files, and there is no "read alongside its source" placement for a whole copied tree the way `gate_catalog.json`+`.md` sit together; (b) it would multiply this iterate's diff size by roughly the size of `shared/` (8.4 MB of scripts) for no verification benefit the drift checker doesn't already provide; (c) publication-readiness (Slice 5) is explicitly out of this campaign's scope. Revisit only when an actual publish/distribution iterate needs it.
