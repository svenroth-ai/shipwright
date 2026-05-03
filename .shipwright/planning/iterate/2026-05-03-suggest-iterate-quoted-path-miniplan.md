# Mini-Plan — suggest_iterate quoted-path + Shape-A→B upgrade-in-place

- **Run ID:** iterate-2026-05-03-suggest-iterate-quoted-path
- **Spec:** `.shipwright/planning/iterate/2026-05-03-suggest-iterate-quoted-path.md`
- **Branch:** `iterate/suggest-quoted-path-v2` (from `origin/main` after
  ADR-019 + post-rebase compliance refresh)
- **Note:** integrates on top of Sven's iterate
  `iterate-2026-05-02-fix-hook-installer-shape` (ADR-019). Original
  pre-integration work is preserved on the local branch
  `iterate/suggest-iterate-quoted-path` for history.

## Approach (chosen)

Replace the static `_HOOK_COMMAND` constant with the quoted +
`--no-project` form. Build a small `_build_canonical_entry()` helper
that constructs a fresh canonical Shape B matcher-group entry. In
`install_suggest_iterate_hook`, when iterating existing rows: a Shape
A bare-command match → REPLACE the entire entry with
`_build_canonical_entry()` (Shape A is rejected by Claude Code per
ADR-019); a Shape B inner-sub match where the command differs from
canonical → rewrite `sub.command` in place. In both upgrade paths
return `upgraded: True`. Keep `installed: False, already_present:
True` for both upgrade and true no-op cases (caller-facing API
unchanged) but distinguish via the new `upgraded` field.

Propagate the documented snippet update to both shipwright-project
and shipwright-run SKILL.md (the two places that show the install
JSON to operators), and sweep quoting across every `uv run
{placeholder}/...` snippet in skills/agents/docstrings — same
conceptual fix, same risk class.

## Files to change

### Critical (the bug + tests)

| Path | Change |
|---|---|
| `plugins/shipwright-adopt/scripts/lib/hook_installer.py` | Replace canonical `_HOOK_COMMAND` with quoted+`--no-project`; expand `_HOOK_ALIASES` to 6 known forms; introduce `_build_canonical_entry()`; rewrite `install_suggest_iterate_hook` to handle Shape A→B carrier upgrade AND inner Shape B command upgrade, returning `upgraded: bool`. |
| `plugins/shipwright-adopt/tests/test_hook_installer.py` | Keep all 5 origin/main tests verbatim. Add: `test_installer_emits_quoted_command_with_no_project` (AC-1, exact-equality); `test_installer_upgrades_legacy_unquoted_entry_in_place_shape_b` (AC-2, parametrized × 6); `test_installer_upgrades_legacy_shape_a_entry_to_shape_b` (AC-3, parametrized × 6); `test_installer_upgrades_shape_a_canonical_command_to_shape_b` (AC-3 corner); `test_installer_idempotent_returns_upgraded_false_when_already_canonical` (AC-4). |

### Documentation (Category A — same install snippet shown to operators)

| Path | Change |
|---|---|
| `plugins/shipwright-project/skills/project/SKILL.md` (~line 400) | JSON snippet → matcher-group Shape B + canonical quoted command + `--no-project`. Manual edit (sweep regex would corrupt the inner JSON-quoted string). |
| `plugins/shipwright-run/skills/run/SKILL.md` (~line 178) | Same. |

### Documentation sweep (Category B — agent-rendered template patterns)

| Path | Change |
|---|---|
| `plugins/shipwright-{adopt,build,changelog,compliance,deploy,design,iterate,plan,preview,project,run,security,test}/skills/**/*.md`, `plugins/*/agents/*.md`, `shared/scripts/**/*.py` (docstrings) | Wrap path arguments of the form `{plugin_root}/...`, `{shared_root}/...`, `${SHIPWRIGHT_PLUGIN_ROOT}/...`, `${CLAUDE_PLUGIN_ROOT}/...` in double quotes inside `uv run` snippets. Mechanical regex sweep, audit via `git diff`. |

### Spec / FR

| Path | Change |
|---|---|
| `.shipwright/planning/01-adopted/spec.md` | Add explicit AC lines under FR-01.13 covering canonical install + Shape A/B upgrade-in-place + true no-op. Add documentation-parity ACs under FR-01.02 + FR-01.01. References ADR-019 + ADR-020. |

### Conventions / decision_log

| Path | Change |
|---|---|
| `.shipwright/agent_docs/conventions.md` | New entries under `## Learnings`: always-quote-uv-run rule + upgrade-in-place pattern (Shape + command both fixable). |
| `.shipwright/agent_docs/decision_log.md` | New ADR-020 referencing ADR-019 as prerequisite. |

## Test Plan

```bash
cd plugins/shipwright-adopt
uv run pytest tests/test_hook_installer.py -v   # 20 tests (5 origin + 15 new)
uv run pytest tests/ -v                          # full adopt suite
```

```bash
cd plugins/shipwright-iterate
uv run pytest "../../shared/tests/test_suggest_iterate.py" \
              "../../shared/tests/test_phase_plugin_hooks_consistency.py" \
              "../../shared/tests/test_phase_session_hooks.py" -v
```

## Alternative considered (rejected)

**Generate the command via `shlex.quote` at install time, embedding
the already-resolved plugin path literally (no `${CLAUDE_PLUGIN_ROOT}`
indirection).** Pro: no shell expansion, rock-solid against quoting
bugs. Con: hard-codes the version-numbered cache path
(`cache/shipwright/0.3.0/`), breaking on plugin upgrade. The
`${CLAUDE_PLUGIN_ROOT}` indirection is what lets plugin upgrades work
without re-running adopt; quoting the env-var expansion is the right
fix.

## Risk

- **Low.** Pure text fix in installer + tests + docs; no schema
  changes; no migration; idempotent installer means re-running adopt
  against existing projects is safe.
- The legacy-alias matching must be exhaustive and the Shape A → B
  upgrade must NOT lose nested data. Mitigation: parametrized tests
  over all 6 legacy literals × both Shape A/B carriers.
- Sweep edits in SKILL.md/agents.md are text-only and don't change
  agent behavior on paths without spaces. Mitigation: mechanical
  regex with negative lookbehind/lookahead, audit via `git diff`,
  AST-parse all touched .py files to confirm no Python syntax broke.

## Success criteria

- `pytest plugins/shipwright-adopt/tests/test_hook_installer.py -v` →
  green, 20 tests (5 origin + 15 new).
- `pytest plugins/shipwright-adopt/tests/ -v` → green, full adopt
  suite no regressions (was 240 on origin/main, becomes 255 with the
  15 new tests).
- Empirical re-verification: pre-seed a tmp project's
  `.claude/settings.json` with each of the 12 broken combinations
  (6 commands × 2 shapes), call installer, assert resulting file is
  the canonical Shape B + canonical command.
- `git grep -nE 'uv run \$\{[A-Z_]+\}/[^\"]' plugins/*/skills/`
  returns zero hits (and same for agents/, shared/).
