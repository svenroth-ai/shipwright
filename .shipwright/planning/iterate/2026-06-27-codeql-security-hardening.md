# Iterate Spec — CodeQL Security Hardening + Repo-Tailored Suite

- **run_id:** iterate-2026-06-27-codeql-security-hardening
- **intent:** CHANGE
- **complexity:** medium
- **Spec Impact:** MODIFY (security behavior of file-mode + regex sites; new CI config; dead-code removal is behavior-preserving / NONE)

## Context / Problem

The repo went public 2026-06-24, activating CodeQL code-scanning
(`.github/workflows/codeql.yml`, `/language:python`, `queries:
security-and-quality`). 175 open alerts surfaced. This session verified each of
the 23 "high" alerts against the code: **11 are genuine security queries**, **12
are quality/correctness queries** surfaced as "high" only because their CodeQL
severity is `error`. The 149 "low" + 3 "medium" are the quality half of the
suite (import hygiene, dead code, empty-except).

Verified outcome: ~8 genuine root-fixes, a tailored CodeQL config that keeps the
full security + high-value-correctness net while removing only ruff-redundant or
convention-conflicting *quality* queries, plus a dead-code (bloat) cleanup. The
verified false-positives are dismissed on GitHub **out of band** (operator step,
not in this diff).

## Acceptance Criteria

### AC-1 — Tighten file-creation modes (overly-permissive-file ×5 source sites)
`0o644 → 0o600` (owner-only) at, with a one-line "owner-only; non-secret state
file" comment each:
- `shared/scripts/lib/event_once.py` (`os.open` O_CREAT|O_EXCL sentinel)
- `shared/scripts/hooks/plugin_sync_reminder_on_stop.py`
- `shared/scripts/hooks/session_start_using_shipwright.py`
- `shared/scripts/tools/write_changelog_drop.py`
- `shared/scripts/tools/write_decision_drop.py`
**Done when:** all five create files with `0o600`; existing tests green (these
are single-user lock/marker/drop files — no cross-user reader).

### AC-2 — De-ambiguate 2 ReDoS regexes (no language change)
- `shared/scripts/github_api.py` `_GITHUB_HOST_RE`: inner host class
  `[a-zA-Z0-9.-]` → `[a-zA-Z0-9-]` (each `\.` consumes exactly one separator).
- `plugins/shipwright-compliance/scripts/lib/collectors/rtm.py` `_FR_TABLE_RE`:
  trailing `(?:\s*[^|]*?\s*\|)*\s*$` → `(?:[^|]*\|)*\s*$`.
- Keep `shared/scripts/lib/drift_parsers.py:parse_fr_table` in sync if it shares
  the pattern.
**Done when:** new regression tests prove (a) the intended inputs still parse
identically (owner/repo extraction; 3/5/6-column FR rows incl. Removed-section
exclusion) and (b) the prior catastrophic input now resolves fast. Existing
suites green.

### AC-3 — Fix loop-variable late-binding bug (genuine correctness bug)
`plugins/shipwright-compliance/tests/test_audit_groups_c_f.py:38` →
`lambda _r, cid=cid: _FakeCheck(cid, ok=True)`. Add a regression assertion that
each returned check carries its own id (not the last loop value).

### AC-4 — Defensive rollback guard
`plugins/shipwright-deploy/scripts/lib/rollback.py`: explicit `else:` returning
an error JSON so `result` is always bound (argparse `choices` guarantees a
branch today; latent NameError if a 3rd strategy is added). Add/extend a test
for the unreachable-strategy path if cheap.

### AC-5 — Remove dead module-level globals (unused-global-variable ×21 → bloat)
Per-name **repo-wide** verification first. Remove only truly-dead names; keep
(and list for out-of-band dismissal) any that are public API / `__all__` /
dynamically used. Clearly-dead (count==1 / both-flagged): `_DESCRIBE_RE`,
`_IT_RE`, `_tools_file`, `_SEMANTIC_TOKEN_RE`, `_INDEX_TRUE_RE`,
`W1_REMEDIATION`, `_TERMINAL_STATUSES`, `_CRITICAL_ROW_RE`, `_PROJECT_CHECKS`,
`_ITERATE_CHECKS`, `_COPYLEFT_LICENSES`×2. Inspect-then-decide: `_SEVERITY_MAP`,
`_OWNED_PREFIXES`, `_GIT_WARN_EMITTED` (warn-once flag — verify read site),
`mark_phase_failed`, `_is_shipwright_project`, `LEGACY_COMPLIANCE_DIRNAME`×3,
`_REPO_ROOT`. **Done when:** ruff stays green; full suite green; no removed name
referenced anywhere.

### AC-6 — Tailored CodeQL config (keep the net; remove only noise)
Add `.github/codeql/codeql-config.yml`, wire from `codeql.yml` via the init
action `config-file:` input, **keep `queries: security-and-quality`**. Exclude
ONLY (each with an inline reason comment):
- `py/empty-except` — repo convention: fail-open best-effort try/except
  (`# noqa: BLE001`) in hooks/producers.
- `py/unused-import` — owned by ruff F401 (hard green CI gate).
- `py/unused-local-variable` — owned by ruff F841.
- `py/import-and-import-from`, `py/repeated-import`, `py/import-own-module` —
  pure import-style; ruff intentionally omits import-placement cosmetics.
**Keep scharf** (must NOT be excluded): every security query, plus
`py/uninitialized-local-variable`, `py/loop-variable-capture`,
`py/call/wrong-named-argument`, `py/implicit-string-concatenation-in-list`,
`py/mixed-returns`, `py/cyclic-import`, `py/unsafe-cyclic-import`.
**Done when:** `codeql.yml` references the config; a regression test asserts the
config excludes exactly the six allowlisted query ids and excludes none of the
keep-scharf ids; YAML is valid.

## Out of Scope (operator out-of-band GitHub dismissals — NOT this diff)
clear-text-logging/storage ×2 (taint FP), overly-permissive-file test fixtures
×2, uninitialized-local test-import guards ×7, call/wrong-named-argument ×1
(intentional `pytest.raises`), cyclic-import ×8 (deliberate guarded
registration; query stays scharf), any unused-global kept as public API.

## Affected Boundaries
- File-creation modes (POSIX permission bits) — AC-1.
- Regex parsers at I/O boundaries (git remote URL, RTM markdown) — AC-2.
- `.github/workflows/codeql.yml` + new `.github/codeql/codeql-config.yml` — AC-6
  (CI config boundary → Tier-3 PR review expected).
- Hook files (`**/hooks/*.py`) touched by AC-1 → `cross_component` may recompute
  at F11.

## Test Plan
- AC-2: dedicated regex regression tests (parse-equivalence + fast-fail).
- AC-3: per-id closure assertion.
- AC-6: config-content assertion test (exclude set == allowlist).
- AC-1/AC-4/AC-5: existing suites + ruff green; targeted `--related` runs.

## Confidence Calibration
- **Boundaries touched:** POSIX file-permission bits (AC-1); regex parsers at
  I/O boundaries — git remote URL + RTM markdown (AC-2); CI config
  `.github/workflows/codeql.yml` + new `.github/codeql/codeql-config.yml`
  (AC-6); module-level globals across adopt/test/compliance/deploy/shared (AC-5).
- **Empirical probes run:**
  - ruff (hard CI gate) — clean across the repo after removals.
  - Full suites green: shared/tests 3556, shared/scripts/tests 196,
    shared/scripts/tools/tests 61; plugins adopt 334, test 143, deploy 26,
    compliance 707. Every touched module has a passing suite.
  - ReDoS: both regexes resolve a catastrophic input in <1s (fast-fail tests).
  - AC-5: per-name repo-wide reference sweep — found 3 live FPs
    (`_OWNED_PREFIXES` imported by resolve.py; `_GIT_WARN_EMITTED` read at
    line 275; `_is_shipwright_project` aliased + imported) and a 3× deliberate
    `LEGACY_COMPLIANCE_DIRNAME` allowlist → KEPT, not deleted.
  - AC-1: `_create` makes a 0o600 file (POSIX assertion in CI).
- **Test Completeness Ledger:**
  | Behavior | Disposition |
  |---|---|
  | AC-1 claim/marker/drop files created owner-only (0o600) | `tested` — test_event_once.py::test_create_claim_is_owner_only (POSIX); other 4 sites use the identical `os.open(...,0o600)` pattern, create paths `covered-by-existing-test` (green hook/tool suites) |
  | AC-2 `_GITHUB_HOST_RE` parses all recognised remotes + fast-fail | `tested` — test_github_api.py (27, incl. no_catastrophic_backtracking) |
  | AC-2 `_FR_TABLE_RE` parses 3/5/6-col rows + fast-fail | `tested` — test_rtm_fr_table_redos.py (5) |
  | AC-3 each fixture check binds its own id | `tested` — test_group_cf_fixture_loop_capture.py |
  | AC-4 `result` always bound (defensive else) | `covered-by-existing-test` — else is unreachable by argparse `choices`; a static-analysis guard, no new runtime behavior; reachable git/clone dispatch tested by test_rollback.py |
  | AC-5 13 dead globals removed, 8 live/deliberate kept, no breakage | `tested` — full suites + ruff green |
  | AC-6 CodeQL config excludes exactly the 6 allowlisted ids, 0 security/high-value | `tested` — test_codeql_config_query_filters.py (15) |
  - 0 testable-but-untested behaviors.
- **Confidence-pattern check:** depth — each AC has a direct assertion test, not
  just a smoke pass. Breadth — cross-plugin global removals validated by every
  touched plugin's full suite, not a sampled subset. No integration-composition
  axis (`cross_component` not triggered: the hook edits are 1-token mode
  changes, not fan-out/merge machinery).

## Risks
- AC-5 is the highest-risk item: removing a global that is actually written via
  `global` or used dynamically would break behavior. Mitigation: per-name
  repo-wide grep + read-site check before each removal; ruff + full suite gate.
- Multi-concern diff (security + CI config + dead-code) reduces reviewability —
  organized by AC; flagged at the approval gate.
