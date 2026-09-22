# Mini-Plan: r1b-codex-hooks-config-layer-shim

- **Run ID:** iterate-2026-09-22-r1b-codex-hooks-config-layer-shim

## 1. Files to create/modify

**New:**
- `shared/scripts/lib/codex_runtime.py` — `is_codex_runtime(plugin_root: Path
  | None = None) -> bool`: resolves the plugin root via
  `plugin_root.resolve_plugin_root()` (or takes one directly, for testing)
  and returns true only when BOTH of `build_codex_plugin.py`'s own root
  markers are present at that path — `BUILD_MANIFEST.json` and
  `.codex-plugin/plugin.json`. Never a bare env-var presence check (an
  ordinary Claude `CLAUDE_PLUGIN_ROOT` pointing at a per-plugin cache
  directory, or a stray unrelated `PLUGIN_ROOT` value, must return false).
  Catches `PluginRootUnresolvedError` and returns false rather than raising.
- `shared/tests/test_codex_runtime.py` — true under a `tmp_path` fake bundle
  root with both markers; false with only one marker, with neither, with no
  resolvable plugin root at all, and with a plugin-root value pointing at an
  unrelated real directory.
- `shared/scripts/tools/codex_hooks_sync.py` — the producer, both a CLI
  entrypoint and an importable `sync_codex_hooks(bundle_root: Path, *,
  codex_home: Path) -> SyncResult` function (parameterized `codex_home` so
  tests never touch the real `~/.codex/`):
  1. No-ops (returns a `SyncResult(applied=False, reason=...)`) unless
     `is_codex_runtime(bundle_root)`.
  2. Reads `hooks = json.loads((bundle_root / ".codex-plugin" /
     "plugin.json").read_text())["hooks"]`.
  3. Rewrites every `${CLAUDE_PLUGIN_ROOT}` token in every `command` string to
     `str(bundle_root)` (plain string replace — the bundle's own commands are
     already fully resolved relative to that one placeholder, per
     `build_codex_plugin.py`'s docstring; no further origin-namespacing logic
     needed, that's already baked into the bundle's stored commands).
  4. **Launcher-script generation (Windows `cmd.exe /C` double-quote bug —
     see iterate spec Design Notes).** For each rewritten command, writes a
     small launcher script into `codex_home / "shipwright-hooks" /
     "<slug>.{cmd,sh}"` (`.cmd` on Windows, `.sh` + `chmod 0o755` on POSIX;
     `<slug>` derived from a short stable hash of `(event, matcher,
     handler_index)` so re-syncs overwrite the same filename rather than
     accumulating). The launcher's single line is the real, normally-quoted
     invocation (safe — not subject to `cmd.exe /C`'s re-wrap, since it's
     read as a script, not a re-parsed argument). The `hooks.json` entry's
     `command` field is then just that launcher's bare path — no embedded
     quotes, no arguments — which parses correctly under `cmd.exe /C` even
     when the path itself contains spaces (single quote pair, whitespace-
     only content, resolves as an executable name — `cmd.exe`'s documented
     preserve-as-is case).
  5. Loads `codex_home / "hooks.json"` if present (else starts from `{"hooks":
     {}}`), and `codex_home / ".shipwright-hooks-managed.json"` if present
     (else starts from `{"entries": []}` — a flat list of the launcher paths
     Shipwright has previously written, one per hook entry).
  6. **Ownership detection: by launcher-directory membership, not exact
     command-string match** (external review, glm + openai, both flagged the
     original `(event, matcher, command)` triple match as fragile — an
     operator's own identical entry could collide, and losing the sidecar
     orphaned every prior entry permanently). An existing `hooks.json` entry
     is Shipwright's if-and-only-if its `command` path resolves inside
     `codex_home / "shipwright-hooks"` — self-evident from the entry alone,
     no sidecar needed to detect it (the sidecar is still written, as a
     human-readable record of what this run's sync did, but is no longer
     load-bearing for the removal step). Every such entry is removed before
     the fresh set is appended; a manual edit to the *real* invocation lives
     in the launcher script body, not the tracked `hooks.json` entry, so it
     survives a re-sync untouched — the fragility class both reviewers
     flagged no longer applies.
  7. Appends the freshly rewritten entries (pointing at the new launcher
     paths), and writes the new manifest listing exactly those.
  8. **Advisory lock** (`codex_home / ".shipwright-hooks-sync.lock"`,
     `durable_atomic_write`-adjacent exclusive-create) held for the
     read-merge-write span — openai review, low severity: two concurrent
     manual syncs racing. A held lock makes the second invocation fail fast
     with a clear message rather than silently discarding the first's
     writes; not a queue, just a collision guard.
  9. Writes `hooks.json` and the sidecar manifest via `durable_atomic_write`
     (existing shared primitive — durability for a file Codex reads on every
     session start is worth the one extra import).
  10. Returns `SyncResult(applied=True, hooks_written=<count>,
      path=codex_home / "hooks.json")`.

  **Malformed-input handling (openai review, medium):** an existing
  `hooks.json` or sidecar that fails to parse as the expected shape fails the
  whole sync loudly (raises), never silently overwrites or drops unrelated
  content — a broken file is a genuine problem to surface, not an absence
  signal.
- `shared/scripts/tools/tests/test_codex_hooks_sync.py`:
  - AC5 regression: `is_codex_runtime` false (no bundle markers at the given
    `bundle_root`) → `applied=False`, `codex_home` directory untouched
    (created or not; no `hooks.json` written).
  - AC2: a fake bundle root with a `.codex-plugin/plugin.json` containing a
    small representative `hooks` object (one `SessionStart`, one `Stop` with
    a `${CLAUDE_PLUGIN_ROOT}`-referencing command) → the written
    `~/.codex/hooks.json`-equivalent has the placeholder replaced with the
    literal `bundle_root` string, verbatim.
  - AC3 idempotency: run twice back-to-back against the same fake
    `codex_home` → byte-identical `hooks.json` after both runs; a THIRD run
    after changing the fake bundle's hook content → old Shipwright entries
    replaced, a hand-added unrelated entry (simulating an operator's own
    hook, added directly to the fake `hooks.json` between runs, never listed
    in the manifest) survives unchanged across all three runs.
  - Malformed/missing `.codex-plugin/plugin.json` at a bundle root that DOES
    have both markers (a corrupted bundle) → raises a clear error rather
    than silently no-oping (this is a real Codex bundle, an unreadable
    `hooks` key is a genuine problem, not an absence signal).
  - Malformed existing `hooks.json` / sidecar manifest (not valid JSON, or
    valid JSON but the wrong shape) → raises rather than overwriting.
  - Launcher generation: a fake `bundle_root` whose path contains a space
    (`tmp_path / "Shipwright Bundle"`) → the written launcher script's own
    path also contains a space, and the `hooks.json` entry's `command` is
    that bare path with no embedded quotes; a real subprocess test invokes
    it via `cmd.exe /C "<launcher path>"` on Windows / `sh -lc "<launcher
    path>"` on POSIX (platform-gated) and asserts it actually runs — this
    is the concrete regression test for the quoting bug, no live Codex
    needed to prove it.
  - POSIX only: generated `.sh` launcher has the executable bit set
    (`os.access(path, os.X_OK)`).
  - Ownership-by-directory: a hand-added entry in the fake `hooks.json`
    whose `command` does NOT point into `shipwright-hooks/` survives a
    re-sync unchanged, even with no sidecar present at all (simulates
    sidecar loss — external review's manifest-loss finding).
  - Lock contention: holding the lock file open and calling
    `sync_codex_hooks()` again raises a clear "sync already in progress"
    error rather than racing.
- CLI smoke test: `uv run shared/scripts/tools/codex_hooks_sync.py --help`
  exits 0 (argparse wiring only, covered by the same test file via
  `subprocess`).

**Edit:**
- `docs/hooks-and-pipeline.md` — correct the "Codex Plugin Bundle" section
  (added by R1): state plainly that the bundle's own `hooks` key does NOT
  execute under real Codex (cite `openai/codex#16430` and `#39895`), and add
  a new subsection documenting: the config-layer shim, why global
  `~/.codex/hooks.json` and not project-local (the `C-02` / trust-friction
  reasoning from the iterate spec's Design Notes, condensed), the sidecar
  ownership manifest, and the `codex_hooks_sync.py` command with an example
  invocation. Also a one-line forward pointer: "R2's terminal helper
  (paused) is the intended automatic trigger once it resumes."
- `.shipwright/planning/01-adopted/spec.md` — `FR-01.21` MODIFY: add one
  acceptance criterion for hook-execution parity (distinct from AC01's
  skill-discoverability), referencing this run.

## 2. Work breakdown

1. `codex_runtime.py` + tests (TDD: tests first).
2. `codex_hooks_sync.py`'s pure logic (rewrite + merge + manifest), tests
   against `tmp_path` fakes for every AC2/AC3/AC5 case above (TDD).
3. CLI argparse wrapper + smoke test.
4. Docs (`hooks-and-pipeline.md`) + `spec.md`.
5. **Live proof (AC4, blocking).** Reuse this session's existing scratch
   probe (`codex-hook-probe/`) — but this time target a FAKE `codex_home`
   under the scratch dir (never the operator's real `~/.codex/`) via
   `codex_hooks_sync.py`'s `--codex-home` override flag (added for exactly
   this reason — the CLI must accept an override, tests already need it, and
   a real live-proof run against production `~/.codex` would pollute the
   operator's actual Codex config). Point `codex`'s own config search at that
   fake home via `CODEX_HOME=<scratch>` (Codex's own env var, confirmed to
   exist from this session's `codex doctor` output: "CODEX_HOME
   C:\Users\SvenRoth\.codex"). Run `sync_codex_hooks()` against the real,
   already-registered probe bundle (or a fresh minimal one built the same
   way), then `codex exec` with `CODEX_HOME` pointed at the fake home and
   NO `--dangerously-bypass-hook-trust` — confirms global hooks are trust-
   independent, which is the whole point of AC4. Needs one round-trip with
   the operator to actually invoke `codex` (same pattern as R2's aborted
   probe), since this agent's sandbox cannot run Codex directly.
6. Full review cascade + finalization.

## 3. Test strategy

- Unit: `codex_runtime.py`, `codex_hooks_sync.py`'s pure logic — all against
  `tmp_path` fakes, zero touches to the operator's real `~/.codex/` or
  `~/.claude/`.
- Live: AC4 only, via `CODEX_HOME` override (never the operator's real
  config) — one round-trip with the operator to run the actual `codex`
  invocation.
- No E2E/browser layer — `surface: cli`.

## 4. Alternative approaches (considered, rejected)

**Project-local `<project_root>/.codex/hooks.json` instead of global.**
This was the sub-iterate spec's original wording. Rejected during this run's
own design pass (before external review, not a finding from it) once
`C-02` and the per-worktree trust-friction were reasoned through together —
see the iterate spec's Design Notes for the full argument. Global is the
correct target; the sub-iterate spec's file was written before this
reasoning happened and does not itself gate the decision.

**Bypass hook trust automatically inside the sync tool (bake
`--dangerously-bypass-hook-trust`-equivalent config into what's written).**
Never seriously considered — this run's whole point is to make hooks work
through Codex's OWN sanctioned mechanism (global, trust-independent config-
layer hooks), not to ship a standing security bypass. If global hooks turn
out to ALSO require some trust step this run's research didn't surface, that
is a finding for AC4's live proof to catch, not something to route around
with a flag.

**Embed the real invocation directly in `hooks.json`'s `command` field,
quoted as needed, instead of generating launcher scripts.** Rejected once
`codex-rs/hooks/src/engine/command_runner.rs` was read directly this run:
Codex's own Windows execution path (`cmd.exe /C "<command_line>"`) wraps the
whole string in an extra quote pair unconditionally, and `cmd.exe`'s
quote-stripping heuristic only parses cleanly with exactly one quote pair
total — any command needing its own internal quoting (any path with a space)
has no safe quoted form once Codex's wrap is added. A launcher script sidesteps
the problem entirely rather than trying to out-clever a heuristic that isn't
under Shipwright's control, and gives ownership detection a cleaner signal
as a side effect (see item 6 above).
