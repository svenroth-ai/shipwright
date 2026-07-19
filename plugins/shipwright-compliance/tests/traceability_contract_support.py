"""Scaffolding for the test-traceability contract gate (campaign S3).

The gate itself is ``test_traceability_contract.py``; this is the subject it pins and
the machinery it pins with. Split out because the Kern test file is capped at 300 LOC.

The manifest is consumed OUTSIDE this repo: the Command Center WebUI's
``readTraceabilityIndex`` reads ``requirements`` -> each ``.id`` / ``.tests`` (layer ->
array) / each test's ``.id`` / ``.layer`` / ``.resolved_from``, plus root
``generated_at``. It never reads the composite requirement KEY, which is why v3 could
change the key form at all -- but a change to any of those INNER fields renders a
half-empty or plausible-but-wrong screen over there rather than failing loudly here.

**Why the baseline is git and not a pin in a file.** A pin is editable in the same
change: alter the shape, update the pin, and the diff is empty. *Editing the pin erases
the evidence.* So the published fixture is frozen against ``origin/main`` -- the one
thing a pull request cannot rewrite.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.lib.collectors.test_links import build_manifest

_HERE = Path(__file__).resolve().parent
_PLUGIN_ROOT = _HERE.parent
_REPO_ROOT = _PLUGIN_ROOT.parent.parent
_CONTRACTS = _HERE / "contracts"

CONTRACTS_DIR = "plugins/shipwright-compliance/tests/contracts"
STEM = "test-traceability"
SCHEMA_VERSION = 3
FIXTURE_VERSION = "3.0"
CONSUMER = "The Command Center WebUI (github.com/svenroth-ai/shipwright-webui)"
ARTIFACT = "The test-traceability manifest (.shipwright/compliance/test-traceability.json)"

# The fields the WebUI's traceability screen is documented to depend on. Pinned by NAME
# as well as by shape: the skeleton would catch a rename, but this states WHY each one
# may not simply be dropped, in the place a person removing it would read.
LOAD_BEARING = {
    "generated_at",
    "requirements",
    "requirements.03::FR-03.01.id",
    "requirements.03::FR-03.01.tests",
    "requirements.03::FR-03.01.tests.unit[].id",
    "requirements.03::FR-03.01.tests.unit[].layer",
    "requirements.03::FR-03.01.tests.unit[].resolved_from",
}


def _load(name: str):
    """Load a shared contract module by PATH.

    Never via ``sys.path``: this plugin binds ``scripts.lib`` for its own modules, so a
    shared package competing for that namespace would shadow them in a combined pytest
    run (ADR-045). Registered under the bare name BEFORE exec because
    ``contract_baseline`` falls back to ``from contract_skeleton import ...`` when it has
    no parent package.
    """
    path = _REPO_ROOT / "shared" / "scripts" / "lib" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CE = _load("contract_skeleton")
CB = _load("contract_baseline")

# The fixture repo deliberately exercises EVERY optional arm of the manifest, because an
# empty array pins nothing about its elements: a nested field could be renamed while the
# pin still looked like coverage. So it carries an orphan tag, a malformed tag, an
# untagged test, an FR whose Layers cell is a typo, and a fold-map (the only way
# `resolved_from` — a field the WebUI reads — appears at all).
_SPEC = """# App

| ID | Requirement | Priority | Layers |
| --- | --- | --- | --- |
| FR-03.01 | User can sign in | Must | unit |
| FR-03.02 | Reporting rollup | Should | int, db |

## FR-Fold-Map

| Folded ID | → Survivor | Reason | Was |
|-----------|-----------|--------|-----|
| `FR-03.44` | `FR-03.01` | merged into sign-in | granular |

## Removed Requirements

| ID | Requirement | Priority |
| --- | --- | --- |
| FR-03.09 | Legacy launch copy | Should |
"""

_TEST = (
    'import pytest\n\n'
    '@pytest.mark.covers("FR-03.01")\n'
    'def test_sign_in():\n    assert True\n\n'
    '@pytest.mark.covers("FR-03.44")\n'          # folded id → resolved_from
    'def test_sign_in_folded():\n    assert True\n\n'
    '@pytest.mark.covers("FR-77.77")\n'          # nothing declares it → orphan
    'def test_orphaned():\n    assert True\n\n'
    '@pytest.mark.covers("FR-1.3")\n'            # non-canonical → invalid_tag
    'def test_malformed_tag():\n    assert True\n\n'
    'def test_untagged():\n    assert True\n'
)


def _materialize(root: Path, split: str) -> None:
    spec = root / ".shipwright" / "planning" / split / "spec.md"
    spec.parent.mkdir(parents=True, exist_ok=True)
    spec.write_text(_SPEC, encoding="utf-8")
    unit = root / "tests" / "test_auth.py"
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(_TEST, encoding="utf-8")


def _manifest_for(root: Path) -> dict:
    """A deterministic manifest: fixed timestamp/commit so the pin is about SHAPE."""
    return build_manifest(
        root,
        evidence={"tests/test_auth.py::test_sign_in":
                  {"status": "enabled", "executed": "pass"}},
        generated_at="2026-07-20T00:00:00+00:00",
        source_commit="1" * 40,
        collector_version="test_links/0.0.0-contract",
    )


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    _materialize(tmp_path, "01-adopted")
    return tmp_path


def live_contract(root: Path) -> dict:
    return {"skeleton": CE.skeleton_of(_manifest_for(root))}


def fixture_path(version: str) -> Path:
    return _CONTRACTS / f"{STEM}-{version}.json"


def require_baseline_ref(ref: str = "origin/main") -> None:
    """The gate needs the immutable baseline. Skip locally, HARD-FAIL in CI.

    A gate that quietly no-ops when it cannot reach its baseline is a false green."""
    if shutil.which("git") is None:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail("git is required in CI — install git on the runner")
        pytest.skip("git not available on this machine")  # test-hygiene: allow-silent-skip: CI hard-fails above
    done = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "rev-parse", "--verify", ref],
        capture_output=True, text=True, check=False, timeout=30,
    )
    if done.returncode != 0:
        if os.environ.get("CI", "").lower() in ("true", "1"):
            pytest.fail(f"{ref} is unreachable in CI — the contract gate cannot verify")
        pytest.skip(f"{ref} unavailable locally")  # test-hygiene: allow-silent-skip: CI hard-fails above

def published_anywhere(stem: str, *, ref: str = "origin/main") -> list[str]:
    """Every path under any ``contracts/`` dir on ``ref`` that publishes ``stem``.

    The disarm detector's evidence. ``CB.any_published_contract`` asks the repo-wide
    question ("does ref publish ANY contract?"), which is the right question for a stem
    that has existed for a while and the WRONG one for a stem being introduced: this repo
    already publishes grade-report and adopt-snapshot, so a repo-wide check would fail on
    the very commit that adds this contract. Scoping the search to THIS stem keeps the
    detector's real job — catching a renamed CONTRACTS_DIR/STEM that leaves the gate
    looking at nothing — while letting the genuine bootstrap through.
    """
    done = subprocess.run(
        ["git", "-C", str(_REPO_ROOT), "ls-tree", "-r", "--name-only", ref],
        capture_output=True, text=True, check=False, timeout=30,
    )
    if done.returncode != 0:
        return []
    return [
        line.strip() for line in done.stdout.splitlines()
        if "/contracts/" in line and Path(line.strip()).name.startswith(f"{stem}-")
        and line.strip().endswith(".json")
    ]
