"""Config-driven ``test_roots`` for the ``test_links`` collector (iterate: collector-test-roots).

Enables the traceability follow-on: a project may opt extra test roots (``plugins/*/tests``,
``shared/tests``) INTO the collector via ``shipwright_compliance_config.json`` so ``@FR`` tags
written under those dirs actually persist in the regenerated manifest, instead of being scanned
out of scope and silently dropped. The default (config absent) is byte-for-byte unchanged.

Two guardrails proven here:

* **Additive default.** With no ``traceability`` block, ``configured_test_roots`` == the frozen
  ``default_test_roots`` and ``configured_prune_dirs`` == the built-in ``_PRUNE_DIRS`` — every
  existing project + the frozen golden fixtures see zero behavior change.
* **Fixture pollution is fenced.** ``traceability.exclude_dirs`` prunes ``fixtures`` DURING descent
  (``os.walk`` + in-place ``dirnames[:]``), so the collector's OWN traceability mini-repos (which
  carry deliberately fake ``@FR`` tags) never fan a bogus orphan into the real manifest.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib.collectors import _test_links_io as io  # noqa: E402
from scripts.lib.collectors.test_links import build_manifest, generate_file  # noqa: E402

_LIB = _HERE.parent / "scripts" / "lib"

_SPEC = (
    "# Spec\n## Functional Requirements\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-07.01 | Widget renders | Must | unit |\n"
)
_TAGGED = 'import pytest\n\n@pytest.mark.covers("FR-07.01")\ndef test_widget():\n    assert True\n'
# A fixture mini-repo test tagged with an ABSENT FR — a confirmed orphan IF it is ever scanned.
_POISON = 'import pytest\n\n@pytest.mark.covers("FR-99.99")\ndef test_poison():\n    assert True\n'


def _write_config(root: Path, block: dict | None) -> None:
    payload = {"enforcement": {"rtm_coverage_min": 0.7}}
    if block is not None:
        payload["traceability"] = block
    (root / "shipwright_compliance_config.json").write_text(
        json.dumps(payload, indent=2), encoding="utf-8"
    )


def _mono(tmp_path: Path, *, config: dict | None, with_poison: bool = True) -> Path:
    """A monorepo-shaped project: a spec + a tagged plugin test (+ a fixture poison test)."""
    split = tmp_path / ".shipwright" / "planning" / "01-demo"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(_SPEC, encoding="utf-8")
    ptests = tmp_path / "plugins" / "demo" / "tests"
    ptests.mkdir(parents=True)
    (ptests / "test_widget.py").write_text(_TAGGED, encoding="utf-8")
    if with_poison:
        (ptests / "fixtures").mkdir()
        (ptests / "fixtures" / "test_poison.py").write_text(_POISON, encoding="utf-8")
    _write_config(tmp_path, config)
    return tmp_path


def _validator() -> jsonschema.Draft202012Validator:
    schema = json.loads((_LIB / "traceability_schema.json").read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


# --- default preservation (config absent) --------------------------------

def test_configured_roots_default_to_conventional_when_absent(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "e2e").mkdir()
    # no shipwright_compliance_config.json at all
    assert io.configured_test_roots(tmp_path) == io.default_test_roots(tmp_path)
    assert io.configured_prune_dirs(tmp_path) == io._PRUNE_DIRS


def test_configured_roots_default_when_block_present_but_no_test_roots(tmp_path):
    (tmp_path / "tests").mkdir()
    _write_config(tmp_path, {"exclude_dirs": ["fixtures"]})  # block present, test_roots absent
    assert io.configured_test_roots(tmp_path) == io.default_test_roots(tmp_path)


def test_malformed_config_falls_back_to_default(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "shipwright_compliance_config.json").write_text("﻿{ not json", encoding="utf-8")
    # a BOM/garbled config is caught fail-soft — the collector keeps its default scope
    assert io.configured_test_roots(tmp_path) == io.default_test_roots(tmp_path)
    assert io.configured_prune_dirs(tmp_path) == io._PRUNE_DIRS


# --- opt-in resolution ---------------------------------------------------

def test_glob_roots_resolve_to_existing_plugin_dirs(tmp_path):
    for name in ("alpha", "beta"):
        (tmp_path / "plugins" / name / "tests").mkdir(parents=True)
    (tmp_path / "plugins" / "gamma").mkdir(parents=True)  # no tests/ → not a root
    _write_config(tmp_path, {"test_roots": ["plugins/*/tests", "shared/tests"]})
    roots = io.configured_test_roots(tmp_path)
    assert roots == [tmp_path / "plugins" / "alpha" / "tests",
                     tmp_path / "plugins" / "beta" / "tests"]  # shared/tests absent → dropped


def test_present_list_is_authoritative_even_when_it_resolves_to_nothing(tmp_path):
    (tmp_path / "tests").mkdir()  # a default root exists, but the config does NOT include it
    _write_config(tmp_path, {"test_roots": ["shared/tests"]})  # present, resolves to zero dirs
    assert io.configured_test_roots(tmp_path) == []  # present ⇒ exactly those (NOT a silent default)


def test_wrong_type_test_roots_falls_back_to_default(tmp_path):
    (tmp_path / "tests").mkdir()
    _write_config(tmp_path, {"test_roots": "plugins/*/tests"})  # a string, not a list (typo)
    assert io.configured_test_roots(tmp_path) == io.default_test_roots(tmp_path)


def test_non_object_config_root_does_not_crash(tmp_path):
    (tmp_path / "tests").mkdir()
    # valid JSON but a top-level array (not an object) must NOT AttributeError the regen
    (tmp_path / "shipwright_compliance_config.json").write_text("[]", encoding="utf-8")
    assert io.configured_test_roots(tmp_path) == io.default_test_roots(tmp_path)
    assert io.configured_prune_dirs(tmp_path) == io._PRUNE_DIRS


def test_absolute_test_root_entry_is_dropped_not_crashed(tmp_path):
    (tmp_path / "tests").mkdir()
    abs_entry = (tmp_path / "tests").resolve().as_posix()  # an absolute pattern crashes Path.glob
    _write_config(tmp_path, {"test_roots": [abs_entry, "tests"]})
    # the absolute entry is dropped (no crash); the relative one still resolves
    assert io.configured_test_roots(tmp_path) == [tmp_path / "tests"]


def test_recursive_glob_entry_is_skipped_others_kept(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "e2e").mkdir()
    _write_config(tmp_path, {"test_roots": ["tests", "**/e2e"]})  # ** entry skipped, "tests" kept
    assert io.configured_test_roots(tmp_path) == [tmp_path / "tests"]


def test_config_root_escaping_the_project_is_dropped(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (tmp_path / "outside" / "tests").mkdir(parents=True)  # a sibling dir OUTSIDE the project
    _write_config(project, {"test_roots": ["../outside/tests", "tests"]})
    (project / "tests").mkdir()
    # the ../ escape is containment-dropped; only the in-project root survives
    assert io.configured_test_roots(project) == [project / "tests"]


def test_overlapping_roots_yield_each_file_once(tmp_path):
    base = tmp_path / "tests"
    (base / "unit").mkdir(parents=True)
    (base / "unit" / "test_a.py").write_text("def test_a():\n    assert True\n", encoding="utf-8")
    # `tests` and its nested `tests/unit` both resolve; the file under both must be yielded ONCE
    roots = [base, base / "unit"]
    pairs = list(io.iter_test_files(roots, tmp_path))
    assert [rel for _abs, rel in pairs] == ["tests/unit/test_a.py"]


def test_exclude_dirs_extends_prune_set(tmp_path):
    _write_config(tmp_path, {"exclude_dirs": ["fixtures", "sandbox"]})
    prune = io.configured_prune_dirs(tmp_path)
    assert {"fixtures", "sandbox"} <= prune
    assert io._PRUNE_DIRS <= prune  # never drops a built-in prune


# --- integration: plugin-dir tag round-trips into the manifest -----------

@pytest.mark.integration
def test_plugin_dir_tagged_test_round_trips_and_fixtures_are_fenced(tmp_path):
    """cross_component round-trip (producer→file→consumer): a ``@FR``-tagged test under a
    config-opted ``plugins/*/tests`` root reaches the regenerated on-disk manifest, and the
    fixture mini-repo's fake tag is pruned so it never becomes a bogus orphan."""
    root = _mono(tmp_path, config={
        "test_roots": ["plugins/*/tests", "shared/tests"],
        "exclude_dirs": ["fixtures"],
    })
    out = generate_file(root)
    manifest = json.loads(out.read_text(encoding="utf-8"))

    assert not list(_validator().iter_errors(manifest))          # schema-valid artifact on disk
    fr = manifest["requirements"]["01-demo::FR-07.01"]
    links = fr["tests"].get("unit", [])
    assert any(l["path"] == "plugins/demo/tests/test_widget.py::test_widget" for l in links), links
    # the excluded fixture's FR-99.99 tag never fanned an orphan into the real manifest
    assert manifest["orphans"] == []


# --- suite-tag propagation must not fire on embedded TS-in-Python strings -----

_PY_EMBEDS_TS = (
    "# a collector self-test that carries TS test-source as DATA\n"
    "_SUITE = '''\n"
    "describe('widget suite', { tag: ['@FR-07.01'] }, () => {\n"
    "  it('renders default', () => {});\n"
    "});\n"
    "'''\n"
    "def test_builds_from_the_embedded_ts():\n    assert _SUITE\n"
)


def test_describe_it_inside_a_python_string_is_not_a_suite_tag(tmp_path):
    """A ``.py`` test file that embeds a ``describe(... tag ...)`` / ``it()`` block as STRING
    data (exactly what the traceability self-tests do) must NOT propagate a phantom suite tag —
    otherwise scanning the plugin/shared roots fans bogus orphans/coverage into the manifest."""
    split = tmp_path / ".shipwright" / "planning" / "01-demo"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(_SPEC, encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_embed.py").write_text(_PY_EMBEDS_TS, encoding="utf-8")
    manifest = build_manifest(tmp_path, spec_files=[split / "spec.md"], test_roots=[tmp_path],
                              evidence={}, enumerate_untagged=True)
    # FR-07.01 exists but the tag lived only in a Python string → no link, no orphan
    assert manifest["requirements"]["01-demo::FR-07.01"]["tests"] == {}
    assert manifest["orphans"] == []
    # the real Python test is still enumerated as untagged (honest scan)
    assert "tests/test_embed.py::test_builds_from_the_embedded_ts" in manifest["untagged_tests"]


@pytest.mark.integration
def test_without_exclude_the_fixture_tag_would_orphan(tmp_path):
    """The exclude is load-bearing: drop it and the fixture mini-repo's fake FR-99.99 tag DOES
    fan a confirmed orphan — proving the fence in the sibling test is not vacuously green."""
    root = _mono(tmp_path, config={"test_roots": ["plugins/*/tests"]})  # no exclude_dirs
    out = generate_file(root)
    manifest = json.loads(out.read_text(encoding="utf-8"))
    assert any(o["tagged_fr"] == "FR-99.99" and o["category"] == "confirmed_orphan"
               for o in manifest["orphans"]), manifest["orphans"]


def test_iter_test_files_skips_broken_symlink_without_crashing(tmp_path):
    """A dangling symlink named ``test_*.py`` is listed by ``os.walk`` but ``read_text``
    would raise ``FileNotFoundError`` (``errors='ignore'`` swallows only decode errors),
    crashing the whole regen. The ``is_file()`` guard fences it. Matters now the scan
    reaches the wide plugin/shared tree, not just curated ``tests/`` roots."""
    root = tmp_path / "tests"
    root.mkdir()
    (root / "test_real.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")
    broken = root / "test_dangling.py"
    try:
        broken.symlink_to(tmp_path / "no_such_target.py")
    except (OSError, NotImplementedError):
        # OS capability gate, not a missing-binary/import skip: symlink creation needs
        # privilege/developer-mode on Windows. CI runs on ubuntu-latest (see .github/
        # workflows/*.yml — POSIX only), where this always succeeds, so the guard IS
        # exercised in CI; the skip only spares a privilege-less Windows dev box.
        pytest.skip("symlink creation unavailable (Windows without developer-mode)")

    rels = [rel for _abs, rel in io.iter_test_files([root], tmp_path)]

    assert any(r.endswith("tests/test_real.py") for r in rels)
    assert not any("test_dangling.py" in r for r in rels)  # fenced, and no exception raised
