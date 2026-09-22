# Iterate Spec: R1b — Codex hooks config-layer shim

- **Run ID:** iterate-2026-09-22-r1b-codex-hooks-config-layer-shim
- **Campaign:** codex-plugin-execution-reliability, sub-iterate R1b (inserted
  2026-09-22, blocks R2 — see `sub-iterates/R1b-codex-hooks-config-layer-shim.md`)
- **Type:** CHANGE
- **Complexity:** medium (classifier estimated `small`, confidence 0.65;
  overridden — this fixes already-shipped infrastructure across all 14
  plugins' Codex distribution and needs a live-proof gate, which warrants
  the fuller review process)

## Goal

R1 (PR #781) inlines every one of Shipwright's 14 plugins' hooks into
`.codex-plugin/plugin.json`'s own `hooks` key inside the built Codex bundle.
Live probing while starting R2 (6 real Codex CLI runs: interactive and
non-interactive, varying hook event/file location/absolute paths, a
confirmed-active `--dangerously-bypass-hook-trust`) found these hooks never
fire — Codex CLI does not execute a plugin-bundled `hooks.json` at all,
confirmed against two open upstream bugs:
[openai/codex#16430](https://github.com/openai/codex/issues/16430) (open
since 2026-04-01: "Plugin docs/examples imply plugin-local hooks are
supported, but the runtime only loads hooks from config-layer locations") and
[openai/codex#39895](https://github.com/openai/codex/issues/39895) (open, a
related manifest-precedence bug, same silent-no-op symptom, no error/log/
`codex doctor` diagnostic). The one documented and — per this run's own live
proof, see Confidence Calibration — actually-confirmed-working path is a
**config-layer** hooks file: `~/.codex/hooks.json` (global, independent of
project trust) or `<project>/.codex/hooks.json` (project-local, gated on that
project's `.codex/` layer being trusted).

This run builds the producer that reuses R1's already-built merge/rewrite
machinery (`codex_hook_inventory.build_hook_inventory`,
`codex_hook_merge._rewrite_command`) to compute Shipwright's consolidated
hook inventory from the installed Codex bundle and installs it into the
**global** `~/.codex/hooks.json` — not project-local — so that no per-project
setup step or per-project artifact is introduced (see Design Notes for why,
and the direct tension with `C-02`).

## Acceptance Criteria

- [x] AC1: `codex_runtime.is_codex_runtime()` returns true only when the
      resolved plugin root is a real, on-disk Codex bundle (both of
      `build_codex_plugin.py`'s own root markers — `BUILD_MANIFEST.json` and
      `.codex-plugin/plugin.json` — present), never a bare env-var presence
      check; false under a Claude plugin-cache root, an absent env var, or a
      wrong/stray env-var value pointing at an unrelated directory
- [x] AC2: `codex_hooks_sync.sync_codex_hooks()` reads the resolved bundle's
      own precomputed `hooks` key, rewrites every `${CLAUDE_PLUGIN_ROOT}`
      token to the bundle's actual absolute path (config-layer hooks get no
      env-var injection — confirmed: "Plugin hook commands receive
      `PLUGIN_ROOT` and `PLUGIN_DATA`", scoped to plugin-bundled hooks only,
      not config-layer ones), and merges the result additively into
      `~/.codex/hooks.json`
- [x] AC3: the merge is idempotent (running twice back-to-back produces
      byte-identical output) and non-destructive — an entry the operator or
      another tool placed in `~/.codex/hooks.json` that Shipwright did not
      write survives every re-run untouched; a sidecar ownership manifest
      (`~/.codex/.shipwright-hooks-managed.json`) records exactly which
      entries are Shipwright's, so a re-run replaces only those
- [x] AC4 (live proof, blocking): a hook written this way actually fires
      under real `codex exec` against a trusted project, WITHOUT
      `--dangerously-bypass-hook-trust` — global hooks are documented as
      trust-independent; this is the empirical confirmation. **Confirmed by
      the operator, both rounds, against the actual shipped
      `codex_hooks_sync.py`** (not the raw probe scripts): Round 1
      (interactive `codex`, brand-new never-trusted scratch `CODEX_HOME`)
      fired cleanly with real captures for `UserPromptSubmit` and `Stop`.
      Round 2 (`codex exec --sandbox workspace-write --json`, no bypass
      flag, same `CODEX_HOME` immediately after) fired cleanly with fresh
      captures — confirming global config-layer hooks are genuinely
      trust-independent once a trust decision has been made once. Both
      `hooks.json` entries used the real generated launcher `.cmd` paths,
      bare, no embedded quotes. Two incidental observations recorded for
      later: trust-prompt visibility in the TUI appears to vary run-to-run
      (functionally irrelevant — the captures prove firing either way), and
      a never-trusted `codex exec` silently no-ops with zero hook fires and
      no error (exec-mode has no interactive trust prompt to fall back on).
- [x] AC5: regression — running `sync_codex_hooks()` when
      `is_codex_runtime()` is false (i.e. under Claude, or with no plugin
      root resolvable) is a no-op: no file is created or modified anywhere
- [x] AC6: `docs/hooks-and-pipeline.md` corrected in the same diff — R1's
      "Codex Plugin Bundle" section currently states the bundle's own hooks
      fire; that's now known false and must say so, cite both upstream
      issues, and document the config-layer shim, the global-vs-project
      choice, and the sync command

## Spec Impact

**MODIFY** `FR-01.21` (Codex Plugin Distribution). Same capability's next
phase, not a new capability (MINT-vs-FOLD gate reasoning, matching R1's own
classification) — R1 delivered the installable bundle; R1b makes the
bundle's hooks actually reach Codex's runtime the way its skills already do
(AC01 in `spec.md` already covers skill discoverability; hook *execution*
parity was implicitly assumed by R1's own build and needs its own line).

## Design Notes

**Why global (`~/.codex/hooks.json`), not project-local
(`<project>/.codex/hooks.json`), despite the sub-iterate spec initially
describing "project-local":**

1. **`C-02` (`spec.md` Constraints): "The framework installs nothing into a
   project's own settings... nothing has to be set up per project and
   nothing is left behind if a project stops using it."** A per-project
   `.codex/hooks.json` is exactly that — a file set up inside each target
   project, left behind if Shipwright is removed. A global, home-directory
   file is not "a project's own settings" in the sense this constraint
   means (the same sense in which `~/.claude/plugins/cache` isn't either);
   it is Shipwright's own tool-level registration, done once, analogous to
   `codex plugin add` itself.
2. **Trust friction.** Codex's project-trust is keyed by literal absolute
   path (confirmed in this run's own probe: `[projects.'<exact
   path>'].trust_level` in `config.toml`). Every iterate creates a fresh
   `.worktrees/<slug>` directory — a NEW path each time — so project-local
   hooks would need the operator to grant trust to every new worktree
   individually before that iterate's hooks would ever fire. Global hooks
   are documented as independent of project trust, so this friction does
   not exist for them.
3. **Safety is unaffected.** Every Shipwright hook script already no-ops
   outside a real Shipwright project (the `shipwright_run_config.json` /
   `.shipwright/` presence guard already used pervasively, e.g.
   `suggest_iterate.py`). Registering them globally means they evaluate that
   guard on every Codex session on the machine and no-op on non-Shipwright
   ones — the same pattern already relied on elsewhere, not a new risk.

**Command construction: the Windows `cmd.exe /C` double-quote bug (found
during this run's own build, via reading Codex's Rust source directly —
`codex-rs/hooks/src/engine/command_runner.rs::build_command`).** On Windows,
Codex always runs a hook's `command` string as `cmd.exe /C "<command_line>"`
— it wraps the *entire* string in one extra pair of double quotes itself,
unconditionally. `cmd.exe /C` only parses cleanly when there is **exactly
one** quote pair in the resulting argument; a `command_line` that embeds its
own quoted paths (e.g. `"C:\...\python.exe" "C:\...\script.py" arg`) produces
multiple quote pairs once Codex's own wrap is added, and `cmd.exe`'s
documented quote-stripping heuristic mangles the whole line — the process
never spawns, surfacing only as a generic "hook exited with code 1" with zero
observable side effects (confirmed empirically this run: 8 live Codex
invocations with a quoted command produced zero fires across every
plugin/config-layer/trust-bypass combination tried; removing the inner
quotes on the 9th attempt fired cleanly, both interactively and via
`codex exec`, no bypass flag). POSIX is unaffected — non-Windows commands run
via `$SHELL -lc "<command_line>"` with a single `arg()` call and no extra
wrap, so normal shell quoting inside `command_line` parses correctly there.

Because bundle roots and `%USERPROFILE%`/`$HOME` can contain spaces on any
platform, the fix is not "quote correctly" (there is no single quoting form
safe under both `cmd.exe`'s bug and normal shells) — it is to never need
inline quoting at all. `sync_codex_hooks()` therefore writes one small
**launcher script per hook entry** (`.cmd` on Windows, `.sh` on POSIX —
`chmod +x` required there, `.cmd` needs no equivalent on Windows) into a
fixed Shipwright-owned directory under `codex_home`, with the real,
correctly-quoted invocation as the script's own body (safe — scripts are
read and parsed normally, not subject to the `/C` re-wrap bug). The
`hooks.json` entry's `command` field is then just that launcher's bare path,
with no embedded quotes and no arguments — a single quoted token satisfies
`cmd.exe`'s documented "preserve as executable name" special case even when
that path itself contains spaces, and needs no shell-quoting reasoning on
POSIX either. This also gives ownership detection a much simpler, more
robust signal than the sidecar's original `(event, matcher, command)` triple
match (external review, glm/openai, both flagged this as fragile): a
`hooks.json` entry is Shipwright's if its `command` points inside the
launcher directory, full stop — survives operator edits to the *real*
underlying invocation (they'd edit the launcher script, not the tracked
entry) and doesn't silently orphan on sidecar loss the way an exact-string
match would.

**macOS-specific risk carried forward to AC4, not yet proven:** Codex picks
the shell via `$SHELL` and runs it as `-lc` (login + command) — on a login
shell, `zsh` sources `.zprofile`/`.zlogin` but **not** `.zshrc`. Any hook
invocation relying on PATH entries set up only in `.zshrc` (Homebrew shims,
pyenv, nvm — a common interactive-only setup) could fail with "command not
found" independent of the quoting fix above. The launcher scripts should
therefore invoke tools via fully-resolved absolute paths where practical, and
AC4's live proof (once repeated on macOS — operator has a Mac available) must
explicitly check for this, not just confirm the hook fires at all.

**Chicken-and-egg on invocation.** The natural place to *trigger* a hook sync
would be a hook itself (e.g. `SessionStart`) — but that is exactly the
mechanism this run proves is broken, so nothing can bootstrap itself that
way. This run ships `codex_hooks_sync.py` as a documented, manually-run (or
update-time-run) command; R2's future terminal helper
(`codex_activation_helper.py`, paused with R2) is the natural place to call
it automatically before every Codex launch once R2 resumes — noted as a
forward pointer, not built here (see Out of Scope).

## Out of Scope

- Automatic, no-operator-action invocation of the sync (R2's terminal helper
  is the natural trigger once it resumes; this run ships the manual command)
- R2's own mint/gate activation-protocol hooks (paused, depends on this
  landing first, not part of this run's own diff)
- Fixing openai/codex#16430 / #39895 upstream — this run works around them,
  not fixes Codex itself
- Windows/macOS/Linux `~/.codex` path differences beyond what
  `Path.home()` already handles correctly across platforms
- A `codex plugin remove`-triggered auto-cleanup of the global hooks file
  (the sidecar ownership manifest makes a *manual* clean removal possible;
  automatic cleanup on uninstall is not built, since Codex's plugin-removal
  hook (if any) is unproven for the same class of reason this whole run
  exists)
- Cryptographic/registry-backed bundle-root authenticity — `is_codex_runtime()`
  checks shape, not provenance; the PR-review preflight flagged this as a
  BLOCK and the operator explicitly accepted the risk rather than scoping a
  fix here. Full reasoning + the cheap mitigation added instead (an
  interactive `y`/`N` confirmation before `main()` writes, skippable with
  `--yes`): ADR's "Accepted Risk" section.

## Affected Boundaries

| Boundary | Direction | Notes |
|---|---|---|
| `~/.codex/hooks.json` | write (merge) | Global, user-scoped, NOT project-local (see Design Notes) |
| `~/.codex/.shipwright-hooks-managed.json` | write | Sidecar ownership manifest for idempotent, non-destructive re-merge |
| `<bundle_root>/.codex-plugin/plugin.json` | read only | Reuses R1's already-computed `hooks` key; no change to `build_codex_plugin.py` |
| `docs/hooks-and-pipeline.md` | write | Corrects R1's now-known-wrong claim; documents the shim |

## Confidence Calibration

- **Boundaries touched:** see Affected Boundaries above.
- **Empirical probes run:** 6 live Codex CLI runs during R2's aborted start
  (interactive x2, non-interactive x4) proving plugin-bundled hooks never
  fire regardless of event/path/trust-bypass; corroborated by
  `openai/codex#16430` and `#39895` (primary-source GitHub issues, both
  open); official docs fetch (`learn.chatgpt.com/docs/hooks`,
  `.../config-reference`) confirming the config-layer path and the
  project-trust/global-independence distinction. Two further live rounds
  during this run's own design pass: a hardened config-layer probe (all 4
  events, fallback markers) still produced zero fires (8 total), until an
  interactive `codex` session surfaced a "Hooks need review" trust prompt no
  `codex exec` run had ever hit — trusting it exposed "Hook failed / exited
  with code 1" for all 3 registered hooks, which traced (via reading
  `codex-rs/hooks/src/engine/command_runner.rs` directly) to the Windows
  `cmd.exe /C` double-quote bug documented in Design Notes. Removing the
  inner quotes fired all 3 hooks cleanly with full real payloads — both
  interactively and via a follow-up `codex exec` with no bypass flag,
  confirming global config-layer hooks are genuinely trust-independent once
  the command string itself is well-formed. **AC4's live proof is now
  done** — see AC4 above for the operator's two-round confirmation against
  the actual shipped `codex_hooks_sync.py`.
- **Test Completeness Ledger:**

  | Behavior | Disposition | Evidence |
  |---|---|---|
  | AC1 detection (both markers true) | tested | `shared/tests/test_codex_runtime.py::test_both_markers_present_returns_true` |
  | AC1 detection (one/neither marker, unrelated dir, env-var resolution) | tested | `shared/tests/test_codex_runtime.py` (7 remaining cases) |
  | AC2 placeholder rewrite into launcher script | tested | `test_codex_hooks_sync.py::test_ac2_placeholder_rewritten_into_launcher_script` |
  | AC2 real bundle double-wrap shape (`plugin.json["hooks"]["hooks"]`) | tested | fixed live against a real `build_codex_plugin.py` bundle; `_codex_hooks_sync_fixtures.py::make_bundle` reproduces the real shape |
  | AC3 idempotent byte-identical rerun | tested | `test_ac3_idempotent_byte_identical_on_rerun` |
  | AC3 foreign entry survives resync + bundle content change | tested | `test_ac3_foreign_entry_survives_resync_and_content_change` |
  | AC3 ownership survives without sidecar present | tested | `test_ownership_survives_without_sidecar_present` |
  | AC4 live fire against real Codex CLI, no bypass flag | tested | operator's two-round live proof, see AC4 above |
  | AC5 no-op under non-Codex bundle | tested | `test_ac5_noop_when_not_codex_runtime` |
  | AC6 docs corrected | tested | `docs/hooks-and-pipeline.md` diff (manual doc review, not a unit test) |
  | Windows `cmd.exe /C` quoting bug (launcher path with spaces actually runs) | tested | `test_launcher_path_with_spaces_actually_runs` (real `cmd.exe /C "<launcher>"` invocation on Windows) |
  | POSIX `$SHELL -lc` word-splitting bug (launcher path with spaces, `shlex.quote()` round-trip, real `$SHELL -lc <launcher>` invocation) | tested | same test's POSIX (`else`) branch (external code review, both legs, high — found after the Windows fix landed) |
  | Ownership check rejects a lexical `../`-traversal that escapes `launcher_dir` (`.resolve()` fix) | tested | `test_ownership_rejects_lexical_traversal_outside_launcher_dir` |
  | Ownership check accepts a genuinely-inside path with a harmless `.` segment | tested | `test_ownership_accepts_genuinely_inside_path_with_dot_segment` |
  | `is_codex_runtime()` rejects two empty/placeholder marker files (shape check, not presence-only) | tested | `shared/tests/test_codex_runtime.py::test_false_with_empty_placeholder_markers` |
  | `is_codex_runtime()` rejects a malformed `BUILD_MANIFEST.json` | tested | `test_false_with_malformed_build_manifest` |
  | POSIX launcher is executable, owner-only (0700) | tested | `test_posix_launcher_is_executable`, `test_posix_launcher_is_owner_only_executable` (skipped on this Windows dev machine, run in CI's Linux matrix) |
  | Malformed bundle / hooks.json / sidecar inputs raise `CodexHooksSyncError` | tested | `test_codex_hooks_sync_errors.py` (8 cases incl. wrong-inner-shape, relative-path resolution) |
  | Lock contention raises `CodexHooksSyncError` specifically | tested | `test_lock_contention_raises_clear_error` (tightened from a too-broad `RuntimeError` assertion, external review) |
  | Empty bundle refuses unless `--allow-empty` (doubt-review) | tested | `test_empty_bundle_raises_unless_allow_empty` |
  | Stale-launcher removal is a genuine orphan (handler/event structurally removed, not just command text edited) and unlink failure degrades to a warning, never crashes | tested | `test_stale_launcher_removal_survives_unlink_failure` (redesigned — `_launcher_slug()` is positional, editing only command text never orphaned anything, external review) |
  | CLI `--help` smoke | tested | `test_cli_help_exits_zero` |

  Counts: testable = 23, tested = 23, untestable = 0, untested_testable = 0.
  Enumeration basis: 6 ACs, all 6 covered (several ACs are covered by more
  than one behavior row above; the added rows cover the external-review
  cascade's HIGH POSIX finding plus the MEDIUM/LOW ownership, bundle-shape,
  and test-fidelity findings — see the ADR's External-Code-Review-Findings
  table for the full disposition of each).
- **Confidence-pattern check:** Depth (asymptote) — the Windows quoting bug
  was found only by reading Codex's own Rust source after 8 zero-fire live
  probes; the fix is verified at the same depth, with a regression test that
  replicates Codex's *exact* `cmd.exe /C "<command_line>"` raw-string
  invocation (not a Python-list-quoted approximation) and a real launcher
  generated against a real `build_codex_plugin.py` bundle. Breadth
  (coverage) — every AC has at least one behavior row above, plus 4
  doubt-review findings each got their own fix and regression test
  (concurrency/crash-safety, empty-bundle guard, unlogged deletes, launcher
  permissions). `cross_component`/integration: this change is a producer for
  a global, machine-wide config file consumed by an external process (Codex
  CLI), not FRAMEWORK cross-component machinery in the sense the risk flag
  defines (merge/churn/event-log resolver, Claude-Code hook fan-out,
  pipeline phase validators, campaign drain), so `category:"integration"` is
  not owed here; AC4's live proof against real `codex`/`codex exec` is the
  actual integration evidence and is cited above.

## Verification

- **Surface:** cli
- **Unit:** rewrite/merge/idempotency logic against `tmp_path`-scoped fake
  `~/.codex/`, never the real one
- **Live (real Codex CLI, throwaway scratch project, reusing this session's
  existing probe setup):** AC4
