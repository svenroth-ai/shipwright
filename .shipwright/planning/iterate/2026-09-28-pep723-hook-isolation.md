# Iterate Spec: pep723-hook-isolation

- **Run ID:** iterate-2026-09-28-pep723-hook-isolation-pilot
- **Type:** change (hardening)
- **Complexity:** medium (`cross_component`: every plugin's hook entry points; the
  classification floor for Claude-Code hook machinery)
- **Status:** built, in review
- **Origin:** triage card `trg-141b57d5`, filed by the main-repair of #810/#814

## Goal

Hook isolation from the session CWD's project must not depend on which uv release
happens to run. `--no-project` (PR #810) stops project *sync*, but (a) it does not stop
uv honoring a CWD `.python-version` — measured on uv 0.11.9: a headerless hook run with
`--no-project` from a CWD pinning an uninstallable interpreter fails
(`No interpreter found for Python 3.99`) — and (b) on uv >= 0.12 project discovery is
script-relative anyway (astral-sh/uv#14585), which is why #810's negative-control test
went red on CI's floating uv 0.12.19 while passing on the dev box's 0.11.9.

PEP 723 inline script metadata (`# /// script`) is uv's documented, version-independent
isolation: a script carrying it never consults an ambient project, `.venv` or
`.python-version`. Roll it across every hook entry point, keeping `--no-project` as the
second layer.

## Acceptance Criteria

- [x] AC-1: every script a `hooks.json` runs via `uv run` (35 across 12 plugins +
      shared) carries a `# /// script` header with `requires-python = ">=3.11"` and
      `dependencies` mirroring that entry's `--with` flags.
- [x] AC-2: `--no-project` stays in every hooks.json entry (second layer).
- [x] AC-3: a test derives the header ledger FROM hooks.json (a new hook without a header
      fails CI), asserts header deps cover the `--with` flags, and proves headed hooks run
      clean from a poisoned CWD (unsatisfiable `pyproject.toml` + `.python-version=3.99`)
      with and without `--no-project`.
- [x] AC-4: a headerless negative control shows the header is what isolates (skips visibly
      where the running uv ignores the CWD pin).
- [x] AC-5: the #814 isolation test stays as merged; its negative control now runs a
      headerless probe so `--no-project` is still exercised on its own.
- [x] AC-6: the vendored `run_if_cache_ready.py` copies stay byte-identical to their
      canonical template; no hook file crosses the bloat limit.
- [x] AC-7: `docs/hooks-and-pipeline.md` documents the second layer, what was verified on
      uv 0.11.9 and 0.12.19, and what is NOT covered.

## Spec Impact

NONE — hook hardening; no product requirement changes.

## Out of Scope

- The three bash hooks (`validate_command.sh`, `check_secrets.sh`,
  `check_destructive_migration.sh`) look up `python3` on PATH and can still be affected by a
  CWD `.python-version` (pre-existing, now documented).
- The ~157 unpinned `uv run` calls in scripts/skill prose (an agent or subprocess runs those,
  not a hook).
- Removing `--with` flags from hooks.json (kept: codex bundle dedup keys on command shape).
- Chain-run scripts (`sys.executable` from `run_if_cache_ready`) — they ignore inline metadata
  and inherit the entry point's environment.

## Affected Boundaries

- hooks.json `command` → uv → hook script header (PEP 723) → ephemeral environment.
- `run_if_cache_ready.py` → `sys.executable` chain (inherits pyyaml/jsonschema from the header).
- Codex bundle merge dedup (command strings unchanged).

## Confidence Calibration

- **Boundaries touched:** uv script-metadata parsing; hook interpreter/env; vendored template.
- **Empirical probes run:**
  1. Poisoned CWD (unsatisfiable `requires-python`, `.python-version` 3.9 / 3.99): headed hook
     exits 0 silently on uv 0.11.9 AND 0.12.19; headerless hook errors on 0.11.9 and is
     unaffected on 0.12.19 (the header adds no protection there, control test skips).
  2. stderr of a headed hook with `--no-project`: empty on both uv versions (no
     "flag ignored" warning).
  3. Cold uv cache, 12 plugin copies of `run_if_cache_ready` started at once: ~2.3 s wall,
     all exit 0 (vs ~0.5 s for the headerless command); inside the 5 s / 10 s repair windows.
  4. Warm per-call cost 0.13 s (header) vs 0.17 s (none).
- **Test Completeness Ledger:** see `shipwright_test_results.json` `test_completeness`.
- **Confidence-pattern check:** the first proof (poisoned pyproject) was version-dependent —
  the exact failure that reddened main — so the load-bearing probes use `.python-version`
  and a headerless control that skips visibly.

## Review Record

Code review (opus): REJECT → fixed (bloat crossings on two files, negative-control moved to a
headerless probe, useless chain-run headers dropped, probe count cut). Doubt review (opus): 4
medium / 2 low → each answered with a probe or a doc change (compatible-pin probe, stderr noise,
cold-cache concurrency, env leak into probes, claim scoped to `uv run` entry points).
