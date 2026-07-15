"""TT1 hardening regressions (doubt-reviewer HIGH findings).

Two confirmed HIGHs:

* **Obj1 (ADR-045)** — ``build_manifest`` must succeed even when ``sys.modules['lib']``
  is ALREADY bound to the compliance-local ``lib`` package (as a sibling test does at
  collection time). Before the ``_lib_loader`` fix this raised ``ImportError: cannot
  import name 'fr_tag_grammar' from 'lib'`` — the order-fragile CI-red/local-green class.
* **Obj2 (frozen-schema)** — ``@pytest.mark.covers("FR-..", "")`` makes the frozen grammar
  emit ``InvalidTag(raw="")``; the frozen schema pins ``invalidTag.raw`` to ``minLength: 1``,
  so a naive pass-through ships a schema-invalid artifact. The collector must coerce the
  empty raw and (Obj4) ``generate_file`` must validate the manifest fail-closed before write.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import jsonschema
import pytest

_HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(_HERE.parent))

from scripts.lib.collectors import test_links as tl  # noqa: E402
from scripts.lib.collectors.test_links import build_manifest  # noqa: E402

_LIB = _HERE.parent / "scripts" / "lib"


def _validator() -> jsonschema.Draft202012Validator:
    schema = json.loads((_LIB / "traceability_schema.json").read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def _by_id(manifest: dict, fr_id: str) -> dict:
    return next(r for r in manifest["requirements"].values() if r["id"] == fr_id)


_SPEC = (
    "# Spec\n## Functional Requirements\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-08.01 | Sign in | Must | unit |\n"
)


def _mini_repo(tmp_path: Path, test_body: str) -> Path:
    (tmp_path / "spec.md").write_text(_SPEC, encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_x.py").write_text(test_body, encoding="utf-8")
    return tmp_path


# --- Obj1: ADR-045 pre-bound compliance-local lib ------------------------

def test_build_manifest_robust_to_prebound_compliance_local_lib(tmp_path):
    saved = {k: v for k, v in sys.modules.items() if k == "lib" or k.startswith("lib.")}
    for key in list(saved):
        sys.modules.pop(key, None)
    sys.path.insert(0, str(_HERE.parent / "scripts"))
    try:
        import lib  # noqa: PLC0415 — binds sys.modules['lib'] to the COMPLIANCE-local package
        assert "shipwright-compliance" in Path(lib.__file__).as_posix()  # sanity: it's ours
        assert not hasattr(lib, "fr_tag_grammar")                        # has no shared submodule
        root = _mini_repo(tmp_path, 'import pytest\n@pytest.mark.covers("FR-08.01")\ndef test_x():\n assert True\n')
        manifest = build_manifest(
            root, spec_files=[root / "spec.md"], test_roots=[root],
            evidence={}, enumerate_untagged=True,
        )
        # succeeds (pre-fix: ImportError) and the tag binds
        assert any("test_x" in link["path"] for link in _by_id(manifest, "FR-08.01")["tests"]["unit"])
    finally:
        for key in [k for k in sys.modules if k == "lib" or k.startswith("lib.")]:
            sys.modules.pop(key, None)
        sys.modules.update(saved)


# --- Obj2 + Obj4: empty covers arg -> schema-valid + fail-closed write ----

def test_covers_empty_string_yields_schema_valid_manifest(tmp_path):
    root = _mini_repo(
        tmp_path,
        'import pytest\n@pytest.mark.covers("FR-08.01", "")\ndef test_x():\n assert True\n',
    )
    manifest = build_manifest(
        root, spec_files=[root / "spec.md"], test_roots=[root],
        evidence={}, enumerate_untagged=True,
    )
    assert not list(_validator().iter_errors(manifest))          # schema-valid despite covers("")
    raws = [t["raw"] for t in manifest["invalid_tags"]]
    assert "" not in raws and all(len(r) >= 1 for r in raws)      # no empty raw survives
    assert any(t["raw"] == "<empty>" and t.get("reason") for t in manifest["invalid_tags"])
    # the valid FR-08.01 tag on the SAME marker still binds (only the empty arg is invalid)
    assert any("test_x" in link["path"] for link in _by_id(manifest, "FR-08.01")["tests"]["unit"])


def test_generate_file_fails_closed_on_invalid_manifest(tmp_path, monkeypatch):
    # If a future producer/schema drift assembles an invalid manifest, generate_file
    # must RAISE (fail-closed) rather than silently write a corrupt artifact.
    monkeypatch.setattr(tl, "build_manifest", lambda *a, **k: {"schema_version": 2})
    with pytest.raises(ValueError, match="schema"):
        tl.generate_file(tmp_path)
