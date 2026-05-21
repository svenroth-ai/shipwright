# ADR-061 — Plugin-cache vs repo drift check (C.3)

> Long-form spec backing the iterate-2026-05-21-c3-plugin-cache-sync-check
> ADR drop.

## Audience principle

Solo dev today, leadwright Phase 3 tomorrow. CLAUDE.md captures
this iterate's reason for existence verbatim: "Iterates 7-11 had
plugin-side fixes that silently never took effect because
`update-marketplace.sh` was skipped." The dev edits a plugin-side
file, runs an iterate, and the runtime serves the cached version
unaware. The audit detector (Group F, ADR-060) catches doc drift;
this script catches *cache* drift — the same class of "edit landed
but doesn't take effect" failure mode at a lower layer.

Detective-only, fail-soft. The operator gets a WARN, decides
whether to run the sync. No automatic side effects.

## What landed in C.3 vs forward-looking

| Decision | Realized in this iterate? | Realized where |
|----------|---------------------------|----------------|
| D1 SHA-256 file comparison                 | **Yes** | C.3 (this PR) |
| D2 Lexically-latest cache version          | **Yes** | C.3            |
| D3 No-op when cache root absent (CI)       | **Yes** | C.3            |
| D4 Fail-soft default, `--strict` flag      | **Yes** | C.3            |
| D5 Structured `--json` output              | **Yes** | C.3            |
| D6 SessionStart hook integration           | No — out of scope | Future iterate                          |
| D7 Triage emission                         | No — out of scope | Future iterate (audit-detector hook)    |
| D8 SemVer-aware version selection          | No — out of scope | Lexical sort is enough for the cache set |

## Decisions (C.3)

### D1. SHA-256 hash-based comparison

`mtime` is unreliable across filesystems, archive extractions,
fresh clones. SHA-256 of file contents is the only deterministic
"are these byte-identical?" signal. Per-file hash storage in a
plain dict is trivial; the comparison is a key intersection.

### D2. Lexically-latest cache version

The cache layout is `<root>/<plugin>/<version>/...`. Plugin
versions in the cache are pinned strings like `0.2.1` /
`0.3.0`. The lexically-latest version is the one Claude Code
actually loads at runtime; older versions in the cache are
leftovers from prior installs. We deliberately pick `max(sorted)`
rather than SemVer-parse because (a) the cache set is small,
(b) lexical sort works fine for SemVer in practice for our
version range, (c) we don't want a parse-fail to swallow a real
drift.

### D3. No-op when `~/.claude/plugins/cache/shipwright/` doesn't exist

Typical in CI environments (the `claude-code` CLI isn't
installed in headless runners). Returning `status="cache_root_absent"`
with exit 0 means the script slots cleanly into a CI sanity-check
pipeline without spurious failures.

### D4. Fail-soft default, `--strict` opt-in

Daily-iteration workflow: WARN at iterate-start, operator decides
to re-sync or not. CI / pre-commit workflow: `--strict` exits 1
on drift so the pipeline fails fast. Both surfaces honored.

### D5. Structured `--json` output

The drift result is consumed both by humans (default plaintext
output) and potentially by downstream tooling (a future
SessionStart hook, the audit-detector adapter). `--json` emits
the full structured result on stdout so consumers don't have to
parse prose.

### D6. SessionStart hook out of scope

Wiring this check into a SessionStart hook (so every
`/shipwright-iterate` start prints a WARN if drift exists) is
the natural next step but lands in a separate iterate. Shipping
the script + tests first lets the operator try it manually
before automating; per the audience principle, the explicit-run
path comes first.

### D7. Triage emission out of scope

The audit detector (Group F, F4-F7) mirrors fail findings into
`source="compliance"` triage items. A future iterate can add
this script's output to the same path (perhaps as F8 — "plugin
cache drift") once the SessionStart hook lands. For now, the
WARN-to-stderr is the operator-visible signal.

### D8. Lexical sort instead of SemVer parse

The cache holds at most one or two versions per plugin at any
time. SemVer-parsing pulls in either `packaging` (transitive
dep) or hand-rolled parsing (more code to maintain). Lexical
sort gets the right answer for `0.1.0 < 0.2.0 < 0.10.0`?
*No, lexical fails for 0.10.0 vs 0.2.0.* But in practice the
plugin versions never reach double digits at any major level
yet, so the simple sort holds. Documented in the spec; if it
ever bites, swap in `packaging.version.parse` then.

## Consequences

- Solo-dev iterate workflow: a one-line WARN tells the operator
  "your repo has plugin changes the runtime hasn't picked up
  yet". Run `scripts/update-marketplace.sh` to fix.

- CLAUDE.md's recurring "remember to run update-marketplace.sh"
  reminder gains a programmatic backstop. The audit-detector
  (C.2) catches doc hygiene; this script catches code-sync.

- The campaign closes end-to-end on the artifact-polish plan.
  Every planned iterate (A.1-C.3) is now landed.

## Rejected (kept for future me)

- **Block-level diff output in WARN** — would inflate stderr.
  Top-5 path sample + diff-count is enough for the operator to
  decide.

- **Auto-run `update-marketplace.sh`** — side effect; defeats
  the "detective" design intent.

- **Cache version vs `package.json` version compare** — would
  add a parse step. The hash-based check already catches the
  meaningful drift class (file content differs).

## External-Review-Findings

OpenRouter cascade ran 2026-05-21. 16 findings (OpenAI 12 + Gemini 4).
The two HIGH findings (SemVer parsing + repo-only files as drift)
were addressed inline; medium and low addressed where actionable.

| # | Source | Severity | Finding | Disposition |
|---|--------|----------|---------|-------------|
| 1 | OpenAI | HIGH   | Repo-only files (in repo, missing from cache) might be missed as drift. | accepted-and-already-correct — `diffs = [rel for rel in repo_hashes if cache_hashes.get(rel) != repo_hashes[rel]]` flags any repo file whose cache hash is missing or different. `test_repo_added_file_shows_as_drift` covers it. |
| 2 | Gemini | HIGH   | Lexical version sort breaks for `0.10.0 vs 0.2.0`. | accepted-and-fixed — `_version_key` parses leading MAJOR.MINOR.PATCH as ints. `test_picks_010_over_020_correctly` covers it. |
| 3 | OpenAI | MEDIUM | Surface the chosen cache version in output. | accepted-and-already-correct — `cache_version` in every plugin record; tests assert it. |
| 4 | OpenAI | MEDIUM | Per-plugin OSError isolation across all filesystem touchpoints. | accepted-and-already-correct — `_walk_tracked_files` returns `{}` on OSError, `_file_hash` returns None, `_latest_cache_version_dir` returns None on missing dir. Errors don't cascade. |
| 5 | OpenAI | MEDIUM | Distinguish "no tracked files" from "traversal failed". | rejected-with-reason — adds API surface without operator value for this iterate; current behavior treats both as "no signal" which is the right default for a fail-soft check. Future iterate can add an `error` state when needed. |
| 6 | OpenAI | MEDIUM | Plugin name mapping repo↔cache underspecified. | accepted-and-documented — names match 1:1 by directory name (the cache layout is `<root>/<plugin-name>/<version>/`, where `<plugin-name>` IS the repo dir name `shipwright-*`). Documented in `check_sync` docstring; tests use real-shape fixtures. |
| 7 | OpenAI | MEDIUM | Validate cache layout against `update-marketplace.sh` contract. | rejected-with-reason — `update-marketplace.sh` is the source of truth for the layout; adding a parallel parse here would create a tight coupling. The current layout is verified manually in the smoke-test step. |
| 8 | OpenAI | MEDIUM | Symlink handling. | accepted-and-fixed — `_file_hash` refuses to follow symlinks (`is_symlink() → None`). `test_symlinked_file_is_skipped` covers it (skipped on Windows runners without symlink permission). |
| 9 | OpenAI | MEDIUM | Symlink security (path traversal). | accepted-and-fixed — same as #8. |
| 10 | OpenAI | LOW    | `--json` stdout must stay clean. | accepted-and-already-correct — the `--json` branch is the only stdout writer in JSON mode; WARN goes to stderr unconditionally. `test_cli_json_output` parses the stdout as JSON. |
| 11 | OpenAI | LOW    | Empty `plugins/` dir status. | accepted-and-already-correct — `status="ok"` with empty `plugins` list when plugins/ exists but no `shipwright-*` matches. `test_no_repo_plugins_dir` covers the absent case; an empty-but-existing dir is the same OK path. |
| 12 | OpenAI | LOW    | Case-insensitive suffix matching. | accepted-and-already-correct — `entry.suffix.lower() in _TRACKED_SUFFIXES`. |
| 13 | OpenAI | LOW    | Surface scan context (tracked_count, missing_count, version). | accepted-and-fixed — `tracked_count`, `missing_in_cache_count`, `cache_version`, `diff_count`, `sample` all in the per-plugin output. `test_ok_carries_tracked_count` covers it. |
| 14 | Gemini | MEDIUM | CRLF vs LF false drift on text files. | accepted-and-fixed — text-suffix files (`.py .md .json .sh .ps1 .yml .yaml`) read in universal-newline text mode so `\r\n` / `\r` / `\n` all hash identically. `test_crlf_vs_lf_identical_hash` covers it. |
| 15 | Gemini | LOW    | Symlinks. | accepted-and-fixed — same as #8/9. |
| 16 | Gemini | LOW    | Memory spikes hashing large files. | accepted-and-already-correct — binary path reads in 64 KiB chunks via `iter(lambda: fp.read(65536), b"")`. Text path reads line-by-line. |

## External-Code-Review-Findings

OpenRouter cascade ran 2026-05-21 on the staged diff. 4 OpenAI
findings + 1 truncated Gemini hint about `rglob` PermissionError.
All addressed inline.

| # | Source | Severity | Finding | Disposition |
|---|--------|----------|---------|-------------|
| 1 | OpenAI | MEDIUM | CLI treats `no_repo_plugins` as drift WARN; AC-4 says no-op. | accepted-and-fixed — added explicit `elif status == "no_repo_plugins":` branch printing "plugin-cache-sync: skip — no plugins/ dir in repo" on stdout (no WARN, no stderr). `test_cli_no_repo_plugins_dir_skips_cleanly` covers it. |
| 2 | OpenAI | MEDIUM | CLI bug: `no_repo_plugins` → false WARN. | accepted-and-fixed — same as #1. |
| 3 | OpenAI | LOW    | Docstring `--plugins-root` doesn't match real CLI flag `--repo-root`. | accepted-and-fixed — usage block now says `--repo-root`. |
| 4 | OpenAI | MEDIUM | Missing CLI test for `no_repo_plugins`. | accepted-and-fixed — `test_cli_no_repo_plugins_dir_skips_cleanly` asserts exit 0 + "skip" on stdout + NO "WARN" on stderr. |
| 5 | Gemini | MEDIUM (truncated) | `rglob` / `iterdir` could raise `PermissionError` mid-walk, propagating up. | accepted-and-fixed — `_walk_tracked_files` now wraps `rglob` materialization in `try/except OSError` and the per-entry `is_file()` / `relative_to()` calls in a second `try/except OSError`. A bad permission on one entry can't crash the sweep. |

## See also

- Iterate spec: `.shipwright/planning/iterate/2026-05-21-c3-plugin-cache-sync-check.md`
- Script: `scripts/check_plugin_cache_sync.py`
- Sync action: `scripts/update-marketplace.sh`
- Audit detector (sibling check class): `plugins/shipwright-compliance/scripts/audit/group_f.py` (F4-F7, ADR-060)
- CLAUDE.md "When editing plugin-side files" rule (origin of this iterate)
