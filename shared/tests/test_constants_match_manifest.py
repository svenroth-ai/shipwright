"""Layer 6: cross-validate per-module local constants vs ARTIFACT_MIGRATIONS.

For every artifact in the manifest, scan the codebase for module-level
constants whose names follow a recognized pattern and assert the string
value matches the manifest's canonical / legacy_dirname respectively.

Recognized name patterns (per artifact `<name>`, uppercased as `<NAME>`):

    Canonical alias  -> value MUST equal manifest["canonical"]:
        <NAME>_DIR         e.g. AGENT_DOCS_DIR  = ".shipwright/agent_docs"
        <NAME>_DIRNAME     e.g. PLANNING_DIRNAME = ".shipwright/planning"
        <NAME>_PATH        e.g. DESIGNS_PATH     = ".shipwright/designs"

    Legacy alias     -> value MUST equal manifest["legacy_dirname"]:
        LEGACY_<NAME>_DIR
        LEGACY_<NAME>_DIRNAME    e.g. LEGACY_AGENT_DOCS_DIRNAME = "agent_docs"
        LEGACY_<NAME>_PATH

Why this layer exists: Layer-1 canon lint only forbids *legacy*-path
literals in source.  It does NOT validate that a constant claiming to be
the *canonical* path is correct.  A typo like
``PLANNING_DIRNAME = ".shipwright/planing"`` (note the missing "n")
would pass Layer 1, ship silently, and produce empty Path() reads in
production.  Layer 6 closes that gap.

Skipped:
- The manifest itself (`artifact_migrations.py`) -- it documents both
  paths by design.
- Files in ALLOWLIST_FILES below (test fixtures that bind the legacy
  name on purpose).
- Lines carrying the inline opt-out marker.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SHARED_LIB = REPO_ROOT / "shared" / "scripts" / "lib"


# ---------------------------------------------------------------------------
# Manifest loader (file-spec, avoids sys.modules collisions w/ plugin libs).
# ---------------------------------------------------------------------------

def _load_manifest() -> tuple[list[dict], str]:
    spec = importlib.util.spec_from_file_location(
        "_artifact_migrations_layer6",
        SHARED_LIB / "artifact_migrations.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.ARTIFACT_MIGRATIONS, module.INLINE_MARKER


ARTIFACT_MIGRATIONS, INLINE_MARKER = _load_manifest()


# Files where a legacy-bound constant is expected to exist (per design).
# Keys are repo-relative POSIX paths.  Value is a freeform reason string.
ALLOWLIST_FILES: dict[str, str] = {
    "shared/scripts/lib/artifact_migrations.py": "manifest itself",
}


_SUFFIXES = ("_DIR", "_DIRNAME", "_PATH")
_LEGACY_PREFIX = "LEGACY_"


def _name_aliases(artifact_name: str) -> set[str]:
    """Return uppercase aliases recognized for *artifact_name*.

    "planning"   -> {"PLANNING"}
    "agent_docs" -> {"AGENT_DOCS"}
    "designs"    -> {"DESIGNS"}
    """
    return {artifact_name.upper()}


def _classify(constant_name: str, manifest: list[dict]) -> tuple[str, str] | None:
    """Match *constant_name* to (artifact_name, kind) or return None.

    *kind* is ``"canonical"`` or ``"legacy"``.
    """
    if constant_name.startswith(_LEGACY_PREFIX):
        bare = constant_name[len(_LEGACY_PREFIX):]
        kind = "legacy"
    else:
        bare = constant_name
        kind = "canonical"

    for sfx in _SUFFIXES:
        if not bare.endswith(sfx):
            continue
        stem = bare[: -len(sfx)]
        for m in manifest:
            if stem in _name_aliases(m["name"]):
                return m["name"], kind
    return None


def _module_level_string_constants(source: str) -> list[tuple[int, str, str]]:
    """Yield ``(lineno, name, value)`` for each module-level ``NAME = "str"``.

    Only scans top-level ``Assign`` (and ``AnnAssign``) statements -- a
    convenience constant is by definition module-level; values inside
    functions or classes are runtime state, not aliases.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []

    out: list[tuple[int, str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target = node.target
            value = node.value
        else:
            continue
        if not isinstance(target, ast.Name):
            continue
        if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
            continue
        out.append((node.lineno, target.id, value.value))
    return out


def _line_has_inline_marker(source: str, lineno: int) -> bool:
    lines = source.splitlines()
    if 1 <= lineno <= len(lines):
        return INLINE_MARKER in lines[lineno - 1]
    return False


def _iter_python_files(repo_root: Path) -> list[Path]:
    """Walk tracked + untracked .py files, skipping noise dirs."""
    skip_parts = {".git", ".venv", "venv", "node_modules", "__pycache__", ".worktrees"}
    out: list[Path] = []
    for path in repo_root.rglob("*.py"):
        rel = path.relative_to(repo_root)
        if any(part in skip_parts for part in rel.parts):
            continue
        out.append(path)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_manifest_has_at_least_one_artifact():
    """Sanity: the manifest is non-empty.  If it is, this layer is moot."""
    assert len(ARTIFACT_MIGRATIONS) > 0, "ARTIFACT_MIGRATIONS is empty -- nothing to validate"


def test_local_constants_match_manifest():
    """For every <NAME>_DIR/_DIRNAME/_PATH constant in the repo, assert the
    value matches the manifest entry it claims to mirror."""
    failures: list[str] = []
    matched_count = 0

    by_name = {m["name"]: m for m in ARTIFACT_MIGRATIONS}

    for path in _iter_python_files(REPO_ROOT):
        rel = path.relative_to(REPO_ROOT).as_posix()
        if rel in ALLOWLIST_FILES:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        for lineno, name, value in _module_level_string_constants(source):
            classified = _classify(name, ARTIFACT_MIGRATIONS)
            if classified is None:
                continue
            artifact_name, kind = classified
            if _line_has_inline_marker(source, lineno):
                continue

            migration = by_name[artifact_name]
            expected = migration["canonical"] if kind == "canonical" else migration["legacy_dirname"]

            matched_count += 1
            if value != expected:
                failures.append(
                    f"  {rel}:{lineno}  {name} = {value!r}\n"
                    f"      expected {kind} value of artifact `{artifact_name}`: "
                    f"{expected!r}"
                )

    if failures:
        msg = (
            f"\nLayer-6 constants-vs-manifest mismatch ({len(failures)} of "
            f"{matched_count} matched constants drifted from manifest):\n\n"
            + "\n".join(failures)
            + "\n\nFix options per finding:\n"
            f"  1) correct the constant value to match "
            f"shared/scripts/lib/artifact_migrations.py\n"
            f"  2) rename the constant if it should NOT bind to a manifest entry\n"
            f"  3) add the file to ALLOWLIST_FILES in this test if the binding "
            f"is intentional and exempt"
        )
        pytest.fail(msg)

    # Sanity: at least one match across the whole repo, otherwise the test
    # is silently passing because the recognizer is broken.
    assert matched_count > 0, (
        "Layer-6 found no canonical/legacy constants anywhere in the repo. "
        "Either the recognizer is broken or every artifact has been removed "
        "from production code."
    )


# ---------------------------------------------------------------------------
# Recognizer unit tests -- guard the classifier itself
# ---------------------------------------------------------------------------

class TestClassifier:
    def test_canonical_dirname(self):
        assert _classify("PLANNING_DIRNAME", ARTIFACT_MIGRATIONS) == ("planning", "canonical")

    def test_canonical_dir(self):
        assert _classify("AGENT_DOCS_DIR", ARTIFACT_MIGRATIONS) == ("agent_docs", "canonical")

    def test_canonical_path(self):
        assert _classify("DESIGNS_PATH", ARTIFACT_MIGRATIONS) == ("designs", "canonical")

    def test_legacy_dirname(self):
        assert _classify("LEGACY_AGENT_DOCS_DIRNAME", ARTIFACT_MIGRATIONS) == ("agent_docs", "legacy")

    def test_legacy_dir(self):
        assert _classify("LEGACY_PLANNING_DIR", ARTIFACT_MIGRATIONS) == ("planning", "legacy")

    def test_unrelated_constant(self):
        assert _classify("DATABASE_URL", ARTIFACT_MIGRATIONS) is None

    def test_partial_match_does_not_classify(self):
        # ``PLANNINGS_DIR`` -- trailing S, not in aliases.
        assert _classify("PLANNINGS_DIR", ARTIFACT_MIGRATIONS) is None

    def test_legacy_without_known_artifact_does_not_classify(self):
        assert _classify("LEGACY_FOO_DIR", ARTIFACT_MIGRATIONS) is None
