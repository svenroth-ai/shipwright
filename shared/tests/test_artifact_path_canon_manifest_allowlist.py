"""Regression: the generated requirement→test manifest is exempt from the
Layer-1 artifact-path-canon lint.

Context (iterate-2026-07-16-collector-test-roots): once the monorepo opts into
scanning plugins/*/tests + shared/tests (via traceability.test_roots in
shipwright_compliance_config.json), the test_links collector emits a
.shipwright/compliance/test-traceability.json manifest whose test ids include
plugins/shipwright-compliance/tests/... paths. The compliance migration's path
regex false-matches the -compliance/ segment (`-` is not in the negative
lookbehind). update_compliance regenerates + commits the manifest on every
iterate finalize, so without the allowlist the NEXT unrelated iterate's canon
lint would go red on ~1000 such ids.

The manifest is a generated, per-iterate-regenerated churn artifact (same exempt
class as change-history.md / shipwright_test_results.json), so the fix is an
allowlist entry, not an inline marker (JSON has no comment syntax).

NOTE ON THIS FILE: it deliberately references the -compliance/ path segment and
the bare compliance migration name, which trip the compliance migration's own
regex — so this file is itself allowlisted in the compliance migration (same
class as test_artifact_path_canon.py). It is written to carry NO other bare
migration-name literal, and it identifies migrations by BEHAVIOR (regex match),
never by name, so it trips no other migration.
"""
from __future__ import annotations

import fnmatch
import re

# shared/tests/conftest.py inserts shared/scripts into sys.path.
from lib.artifact_migrations import ALLOWLIST, ARTIFACT_MIGRATIONS  # noqa: E402

MANIFEST = ".shipwright/compliance/test-traceability.json"
# A representative manifest-rendered test id (carries the -compliance/ segment).
_SAMPLE_TEST_ID = "plugins/shipwright-compliance/tests/test_test_links_config_roots.py::test_x"


def _path_matches_any(rel_path: str, patterns) -> bool:
    """Mirror of the canon lint's allowlist match (POSIX glob on path or basename)."""
    for pat in patterns:
        pat_posix = pat.replace("\\", "/")
        if fnmatch.fnmatch(rel_path, pat_posix) or fnmatch.fnmatch(
            rel_path.rsplit("/", 1)[-1], pat_posix
        ):
            return True
    return False


def _migrations_tripped_by(text: str) -> list[dict]:
    """Every active migration whose own path patterns match `text`.

    Identifies migrations by behavior, not by literal name, so this test file
    carries no bare migration-name string that the canon lint would flag.
    """
    tripped = []
    for m in ARTIFACT_MIGRATIONS:
        if m["status"] not in ("in_progress", "migrated"):
            continue
        if any(re.compile(p).search(text) for p in m["old_path_patterns"]):
            tripped.append(m)
    return tripped


def test_manifest_content_really_trips_a_migration() -> None:
    """Non-vacuity: prove the FP the allowlist guards against is REAL — a
    manifest-rendered plugin test id trips at least one migration's canon regex."""
    tripped = _migrations_tripped_by(MANIFEST + "\n" + _SAMPLE_TEST_ID)
    assert tripped, (
        "expected the manifest's rendered content to false-match at least one "
        "migration regex — if it no longer does, the allowlist may be redundant"
    )


def test_manifest_is_allowlisted_in_every_migration_it_trips() -> None:
    """The manifest must be exempt in each migration its content actually trips,
    so a regenerated manifest never fails the Layer-1 canon lint downstream."""
    for m in _migrations_tripped_by(MANIFEST + "\n" + _SAMPLE_TEST_ID):
        assert _path_matches_any(MANIFEST, ALLOWLIST.get(m["name"], [])), (
            f"{MANIFEST} is not allowlisted for a migration its content trips "
            f"(canonical: {m['canonical']}) — the next iterate's canon lint would fail"
        )
