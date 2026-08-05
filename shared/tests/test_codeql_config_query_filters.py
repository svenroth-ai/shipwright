"""Pin the monorepo's tailored CodeQL config (`.github/codeql/codeql-config.yml`).

This is the LIVE monorepo config (distinct from the adopt *template* pinned by
``test_codeql_workflow_convention.py``). It tailors the `security-and-quality`
suite by excluding only quality queries that ruff already gates or that conflict
with a documented convention — while KEEPING every security query and the
high-value correctness queries.

Failure modes deliberately covered:

1. A security query (or a high-value correctness query we rely on) gets added to
   the exclude list — silently blinding the scanner. The ``KEEP_SHARF`` guard
   makes that a red test.
2. The exclude set drifts from the intended six — a reviewer can no longer trust
   the config comment.
3. The live workflow stops referencing the config file, or drops the
   `security-and-quality` suite — the filters would silently not apply.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")  # PyYAML — root + adopt + compliance deps

REPO_ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = REPO_ROOT / ".github" / "codeql" / "codeql-config.yml"
WORKFLOW_PATH = REPO_ROOT / ".github" / "workflows" / "codeql.yml"

# The exact, intentional exclude set. Every id here is either owned by ruff
# (a hard green CI gate) or conflicts with a documented repo convention.
EXPECTED_EXCLUDES = {
    "py/empty-except",            # convention: fail-open hooks/producers (BLE001)
    "py/unused-import",           # ruff F401
    "py/unused-local-variable",   # ruff F841
    "py/import-and-import-from",  # import-style cosmetics (ruff omits E401/E402)
    "py/repeated-import",
    "py/import-own-module",
}

# Test fixtures (generated sample apps / scanner-bait) are intentional
# non-first-party code — ruff already excludes them via pyproject
# [tool.ruff] extend-exclude. CodeQL must skip them too: a single bundled
# sample app otherwise floods the dashboard with ~1000 quality alerts. This is
# a path-level exclusion, NOT a query-filter — no security query is disarmed.
EXPECTED_PATHS_IGNORE = {"**/tests/fixtures/**"}

# Queries that MUST stay armed — excluding any of these is the regression we are
# defending against. Security queries + high-value correctness queries.
KEEP_SHARF = {
    "py/overly-permissive-file",
    "py/redos",
    "py/clear-text-logging-sensitive-data",
    "py/clear-text-storage-sensitive-data",
    "py/uninitialized-local-variable",
    "py/loop-variable-capture",
    "py/call/wrong-named-argument",
    "py/implicit-string-concatenation-in-list",
    "py/mixed-returns",
    "py/cyclic-import",
    "py/unsafe-cyclic-import",
}


def _exclude_ids() -> set[str]:
    assert CONFIG_PATH.exists(), f"CodeQL config missing at {CONFIG_PATH}"
    parsed = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    filters = parsed.get("query-filters") or []
    ids: set[str] = set()
    for entry in filters:
        excl = entry.get("exclude") if isinstance(entry, dict) else None
        if isinstance(excl, dict) and isinstance(excl.get("id"), str):
            ids.add(excl["id"])
    return ids


def test_config_is_valid_yaml_with_query_filters() -> None:
    parsed = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    assert isinstance(parsed, dict)
    assert isinstance(parsed.get("query-filters"), list) and parsed["query-filters"]


def test_exclude_set_is_exactly_the_intended_six() -> None:
    assert _exclude_ids() == EXPECTED_EXCLUDES, (
        "CodeQL exclude set drifted. Every excluded query must be ruff-owned or "
        "convention-conflicting (justified inline in codeql-config.yml)."
    )


@pytest.mark.parametrize("query_id", sorted(KEEP_SHARF))
def test_no_security_or_high_value_query_excluded(query_id: str) -> None:
    assert query_id not in _exclude_ids(), (
        f"{query_id} is excluded — that blinds the scanner to a security or "
        f"high-value correctness class. It must stay armed."
    )


def _codeql_action_steps() -> dict[str, list[dict]]:
    """Map step-purpose ('init'/'autobuild'/'analyze') -> ALL matching step
    dicts, matched by `uses:` prefix. Kept as a list (not last-write-wins) so
    a leftover duplicate step is visible instead of silently shadowed by a
    later match."""
    parsed = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    steps = ((parsed.get("jobs") or {}).get("analyze") or {}).get("steps") or []
    found: dict[str, list[dict]] = {}
    for step in steps:
        uses = step.get("uses") if isinstance(step, dict) else None
        if not isinstance(uses, str):
            continue
        for name in ("init", "autobuild", "analyze"):
            if uses.startswith(f"github/codeql-action/{name}@"):
                found.setdefault(name, []).append(step)
    return found


def _init_step() -> dict:
    matches = _codeql_action_steps().get("init") or []
    if not matches:
        raise AssertionError("no github/codeql-action/init step in codeql.yml")
    return matches[0]


@pytest.mark.parametrize("step_name", ["init", "autobuild", "analyze"])
def test_codeql_action_steps_pin_v4(step_name: str) -> None:
    """CodeQL Action v3 is deprecated December 2026 and drops Node.js 20
    runner support in fall 2026; v4 is the GA, Node-24-based replacement.
    Guards the live monorepo workflow against a regression back to @v3 —
    and, since every match is kept (not last-write-wins), against a
    leftover v3 duplicate hiding behind an added v4 step."""
    matches = _codeql_action_steps().get(step_name) or []
    assert len(matches) == 1, (
        f"expected exactly one github/codeql-action/{step_name} step in "
        f"codeql.yml, found {len(matches)}"
    )
    assert matches[0]["uses"] == f"github/codeql-action/{step_name}@v4", (
        f"codeql.yml {step_name} step uses={matches[0]['uses']!r}, "
        f"expected 'github/codeql-action/{step_name}@v4'"
    )


def test_workflow_references_config_file() -> None:
    with_ = _init_step().get("with") or {}
    assert with_.get("config-file") == "./.github/codeql/codeql-config.yml", (
        "codeql.yml init step must reference the tailored config-file, or the "
        "query-filters silently never apply."
    )


def test_workflow_keeps_security_and_quality_suite() -> None:
    with_ = _init_step().get("with") or {}
    assert with_.get("queries") == "security-and-quality", (
        "We keep the full security-and-quality suite and tailor via "
        "query-filters — dropping the suite would defeat the whole approach."
    )


def _paths_ignore() -> set[str]:
    parsed = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    entries = parsed.get("paths-ignore") or []
    return {e for e in entries if isinstance(e, str)}


def test_paths_ignore_is_exactly_test_fixtures() -> None:
    assert _paths_ignore() == EXPECTED_PATHS_IGNORE, (
        "CodeQL paths-ignore drifted. Fixtures (**/tests/fixtures/**) are "
        "excluded because they are generated, non-first-party code (mirrors "
        "ruff's extend-exclude); any change must be justified inline in "
        "codeql-config.yml."
    )
