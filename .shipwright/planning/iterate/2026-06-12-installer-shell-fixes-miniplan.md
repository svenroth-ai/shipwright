# Mini-Plan: iterate-2026-06-12-installer-shell-fixes (campaign a1-7 / WP10)

## Problem

The recommended POSIX install path is broken in six ways (deep-audit
2026-06-10 WP10, F33-F38). All three top-level shell scripts under `scripts/`
are affected: `install.sh`, `update-marketplace.sh`, `verify-setup.sh`.

## Findings & Fixes

- **F33 (MED, install.sh):** `((missing++))` under `set -e` returns exit 1 when
  the prior value is 0, aborting at the FIRST missing prerequisite. → replace
  the three `((missing++))` with `missing=$((missing + 1))` (always exit 0).
- **F34 (MED, install.sh):** after `curl … astral.sh/uv/install.sh | sh` it
  exports `~/.cargo/bin`, but astral installs `uv` to `~/.local/bin` → the
  immediate `uv sync` is command-not-found. → export `~/.local/bin`.
- **F35 (MED, install.sh):** the emitted `shipwright()` alias lists only 12 of
  13 plugins (omits `shipwright-adopt`); the grep idempotency guard skips on a
  pre-existing alias, permanently pinning a stale block. → add adopt; replace
  the skip-guard with an awk strip-and-rewrite so a re-run refreshes the alias.
- **F36 (MED, install.sh):** `--plugin-dir $REPO_ROOT/…` is unquoted → a
  space-containing clone path (e.g. 'Program Files', 'My Projects') splits into
  two args. → double-quote every `--plugin-dir` path.
- **F37 (MED, update-marketplace.sh):** three `$(python -c …)` substitutions
  call bare `python` with stderr suppressed → on Debian/Ubuntu/macOS (only
  `python3`) the substitution is empty and `set -e` aborts the whole sync
  silently. → resolve `python3`/`python`/`py` once into `$PYTHON_BIN`.
- **F38 (LOW, verify-setup.sh):** `source "$PROJECT_ROOT/.env.local"` executes a
  dotenv data file as a shell script → a spaced/quoted/`$(…)` value crashes or
  runs as a command. → parse `.env.local` via the canonical
  `shared/scripts/lib/env.py:parse_env_file`; `env_has` tests live-env OR the
  parsed key list (no eval/injection).

## Approach considered & rejected

- For F38, considered emitting `export K=V` lines from Python and `eval`-ing
  them in the shell — rejected: re-introduces the same injection surface the
  fix removes. Chosen: print only the *names* of keys that carry a value and
  test membership; values never re-enter the shell.

## Tests (TDD)

`shared/tests/test_installer_shell_scripts.py` — drives the scripts via `bash`
subprocess (ADR-044 CI-discipline `_require_bash` gate): premise + behavioral
probes for F33 (no abort under set -e), F34/F35/F36 (alias text + spaced-root
tokenization), F37 (python3-only resolver), F38 (no `source`, no injection).

## Risk

`touches_io_boundary` (the `.env.local` dotenv reader). Round-trip + injection
probes run empirically in Confidence Calibration.
