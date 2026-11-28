# TOML release manifests (root pyproject.toml and uv.lock)

Run: `iterate-2026-11-28-u1-root-pyproject-manifest` · campaign `dfp-changelog-followups`, unit U1 · FINDINGS D111 · FR-01.09.AC12 (restored: every declared manifest carries the release version; the root files can now be declared).

AC record: first frozen as a new AC16 under FR-01.09, then superseded by `restore` FR-01.09.AC12. A new AC in FR-01.09 would need its own golden scenario, oracle judge and promise entry (the frozen harness asserts every FR-01.09 AC through the oracle and pins the count at 15), which is out of scope for U1; AC12 already promises that every declared manifest carries the version.

## Architecture Review

Brief: "nothing new as a mechanism; the existing manifest sync learns two formats". Verdicts: glm `approve`, openai `approve`.

## External-Plan-Review-Findings

| Finding | Severity | Disposition |
|---|---|---|
| tomllib needs Python 3.11+ | medium | rejected-with-reason: the repo and shared scripts require Python >= 3.11 (`requires-python`, CLAUDE.md) |
| Virtual root package without a version line | medium | accepted-and-fixed as a documented refusal (`missing_version_field`); a version is never inserted |
| Root package present but version missing or not a string | medium | accepted-and-fixed: tests for `missing_version_field` and `invalid_version_type` |
| CRLF must survive read and write | medium | accepted-and-fixed: sync reads bytes and writes verbatim; CRLF pinned in unit and scratch-project tests |
| Drive `release.py sync` and test a stale TOML verify | medium | partly accepted: the test drives `release_sync.sync` (what `release.py sync` dispatches to) with the real tool; stale `pyproject.toml` / `uv.lock` verify-commit cases added |
| Campaign brief / D111 not readable by the reviewer | high | rejected-with-reason: read by the runner; no operator answer needed |
| `[package.metadata]` sub-table in tests; error names the file | low | already covered (fixture has it; the caller adds the path) |

## External-Code-Review-Findings

| Finding | Severity | Disposition |
|---|---|---|
| A multi-line string line like `[Overview]` ends the table early | medium | accepted-and-fixed: lines inside `"""`/`'''` strings are text; test added |
| `describe_version_state` not changed | medium | rejected-with-reason: it delegates through `read_manifest_version`; test covers it |
| NaN elsewhere makes the re-parse comparison fail | low | rejected-with-reason: fail-closed refusal, never corruption; NaN in a pyproject is rare |
| Header pattern matches array rows; non-table `project` key | low | header fixed after the code review (below); non-table `project` stays `missing_version_field` |

## Internal reviews

Spec-reviewer (opus): PASS. Code-reviewer (opus): pass, five low findings, all fixed (header-shaped end-of-table pattern plus test, one line split, docstring wrap, `invalid_version_type` row widened with the approved delta updated, sentinel check in the real-file test).

Doubt-reviewer (opus): four doubts. (1, medium) a uv re-lock between sync and commit would be swept into the release commit: rebutted by probe — after the sync, `uv run --offline` leaves the lock byte-identical and `uv lock --check --offline` passes; a stale lock is re-locked at the fold step before the sync and refused as `manifest_dirty_before_sync`. (2) SemVer pre-release/build parts are not always PEP 440: fixed, the TOML formats refuse them (`unsupported_version_for_format`). (3) `tomllib` now imported lazily. (4) Recovery note for a uv.lock re-locked by uv itself.

## Self-Review

1. Spec Compliance: pass. Every AC and the brief's Done-when has a test.
2. Error Handling: pass. Named closed-vocabulary statuses; the re-parse check refuses before a write.
3. Security Basics: pass. Repo-local files through `resolve_contained_path`; no subprocess; `re.escape` on a validated version.
4. Test Quality: pass. Exact changed lines and bytes, each refusal, stale verify-commit.
5. Performance Basics: pass. Linear scans and two parses per manifest, once per release.
6. Naming & Structure: pass. New module beside `manifest_sync_lock`/`_marketplace`, under 200 lines.
7. Affected Boundaries: pass. Producer `sync_release_manifests` to consumers uv and `--verify-commit`, both probed for real.

## Confidence Calibration

- Boundaries: `sync_release_manifests` (producer) to `uv` (consumer of `pyproject.toml` + `uv.lock`) and to `--verify-commit` (consumer of the committed blob).
- Probes: (1) scratch copy of the real files bumped to 0.99.0, `uv lock --check --offline` exit 0; a stale lock exits 1. (2) real git round trip with verify-commit (test). (3) edge round 1: BOM (refused, `parse_error`), empty version, header comment, non-ASCII, no trailing newline, inline table (refused), spaced header: no bug. (4) edge round 2: CRLF lock, workspace member before the root, `[[package]] # x`, `[manifest]` table: no bug. Two rounds without a finding: asymptote reached.
- Not probed: a BOM-prefixed pyproject is refused instead of edited (tomllib rejects it); accepted, it fails closed with a named status.

F2: architecture bullet written (component). F3a: one learning line (uv lock --check as the consumer probe).
