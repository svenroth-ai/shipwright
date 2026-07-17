"""Task C — the enforcing TT5 gate must honour the project's ``traceability.test_roots``.

Before this, ``_layer_coverage_regen._build`` hardcoded ``default_test_roots`` (the eight
conventional dirs) and passed no ``prune_dirs`` → CONFIG-BLIND. Once a monorepo opts
``plugins/*/tests`` + ``shared/tests`` into the collector (``shipwright_compliance_config.json``),
a required layer covered ONLY by a plugin-dir test reads ``ok`` in the committed RTM but
``MISSING`` / false-RED in the gate — the write-then-drop class relocated to the enforcement
path. This pins that the gate now mirrors ``test_links.generate_file``: it scans the
config-opted roots (and excludes ``exclude_dirs``) on EACH of the regenerated base/head trees.

Base-side asymmetry (the tricky part): the gate regenerates base+head via ``git archive`` and
each side resolves config from ITS OWN tree. A base commit predating the ``traceability`` config
has no key → ``configured_test_roots`` already falls back to ``default_test_roots``. These tests
pin: base-without-config + head-with-config → default on base, configured on head, no crash, no
over-scan, and NO false-RED on a plugin-dir-only-covered required layer. NOT ``slow`` — it gates.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import evidence_drop  # noqa: E402
from tools.verifiers.layer_coverage import (  # noqa: E402
    check_cross_layer_coverage,
    check_removal_coverage,
)


def _git_available() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, check=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


pytestmark = pytest.mark.skipif(not _git_available(), reason="git not available")


def _git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {proc.stderr}")
    return proc.stdout.strip()


def _write(root: Path, rel: str, body: str) -> None:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")


def _init(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@t.dev")
    _git(root, "config", "user.name", "t")
    _git(root, "config", "commit.gpgsign", "false")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")  # base ref for _merge_base


def _commit(root: Path, msg: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", msg)
    return _git(root, "rev-parse", "HEAD")


def _seed_medium(root: Path, run_id: str) -> None:
    (root / "shipwright_run_config.json").write_text(json.dumps({
        "iterate_history": [{"run_id": run_id, "complexity": "medium", "type": "feature"}],
    }), encoding="utf-8")


def _junit_pass(test_file: str, name: str) -> str:
    """A minimal JUnit report where ``test_file::name`` is enabled+passing (pytest)."""
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<testsuites><testsuite name="pytest">'
        f'<testcase classname="x" file="{test_file}" name="{name}"></testcase>'
        "</testsuite></testsuites>\n"
    )


def _stage_junit(root: Path, run_id: str, test_file: str, name: str, head_commit: str) -> None:
    report = root / "junit.xml"
    report.write_text(_junit_pass(test_file, name), encoding="utf-8")
    evidence_drop.stage_reports(root, run_id=run_id, junit=report, head_commit=head_commit)


# The FR is covered ONLY by a test living under a NON-conventional plugin root. Explicit
# ``unit`` layer ⇒ a MISSING layer is a HARD gap (not the legacy-advisory valve).
_SPEC = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-08.01 | Widget renders | Must | unit |\n"
)
_SPEC_CHANGED = _SPEC.replace("Widget renders", "Widget renders with totals")  # behaviour delta
_PLUGIN_TEST_REL = "plugins/demo/tests/test_widget.py"
_PLUGIN_TEST = 'import pytest\n\n\n@pytest.mark.covers("FR-08.01")\ndef test_widget():\n    assert True\n'
_CONFIG = json.dumps({"traceability": {
    "test_roots": ["tests", "plugins/*/tests", "shared/tests"], "exclude_dirs": ["fixtures"]}})


def _make_repo(tmp_path: Path, *, head_has_config: bool) -> tuple[Path, str, str]:
    """base: spec + plugin-dir test, NO traceability config (predates it). head: behaviour
    delta on the same FR; config optionally present. Returns (root, run_id, head_sha)."""
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC)
    _write(root, _PLUGIN_TEST_REL, _PLUGIN_TEST)
    _write(root, ".gitignore", ".shipwright/compliance/\n")
    _commit(root, "base: no traceability config")
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_CHANGED)
    if head_has_config:
        _write(root, "shipwright_compliance_config.json", _CONFIG)
    head = _commit(root, "head: behaviour delta (+config)" if head_has_config else "head: behaviour delta")
    run_id = "iterate-cfg" if head_has_config else "iterate-nocfg"
    _seed_medium(root, run_id)
    _stage_junit(root, run_id, _PLUGIN_TEST_REL, "test_widget", head)
    return root, run_id, head


def test_gate_sees_plugin_dir_coverage_when_head_opts_it_in(tmp_path):
    # base predates the config (falls back to default roots), head opts plugins/*/tests in.
    # The plugin-dir test executes-passing ⇒ the required unit layer is covered ⇒ GREEN, no
    # false-RED, and the config-less base build did not crash or over-scan.
    root, run_id, head = _make_repo(tmp_path, head_has_config=True)
    result = check_cross_layer_coverage(root, run_id, head)
    assert result.ok is True and not result.is_skipped, result.detail
    assert "covered+passing" in result.detail  # uniquely the covered-green branch, not "no delta"


def test_gate_misses_plugin_dir_coverage_without_config_load_bearing(tmp_path):
    # The negative control proving the threading is load-bearing (and that the base-side
    # default is what a config-less tree resolves to): with NO traceability config, the gate
    # scans only the conventional roots, never plugins/*/tests, so the ONLY covering test is
    # invisible ⇒ the explicit unit layer reads MISSING ⇒ HARD block.
    root, run_id, head = _make_repo(tmp_path, head_has_config=False)
    result = check_cross_layer_coverage(root, run_id, head)
    assert result.ok is False and not result.is_skipped, result.detail
    assert "unit" in result.detail


# ``configured_test_roots`` has REPLACE semantics — a PRESENT list is used EXACTLY. If the gate
# scanned only that, a config that narrows below the conventional dirs would make the ENFORCING
# gate scan LESS than the historical floor and a removed FR's still-tagged test in a dropped
# conventional dir would escape (false-green). The gate UNIONs with default_test_roots to keep the
# fail-closed floor. These constants build that exact regression scenario.
_SPEC_RM_ACTIVE = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-09.01 | Legacy flow | Should | unit |\n"
)
_SPEC_RM_REMOVED = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n\n"
    "## Removed Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-09.01 | Legacy flow | Should | unit |\n"
)
_LEGACY_TEST = 'import pytest\n\n\n@pytest.mark.covers("FR-09.01")\ndef test_legacy():\n    assert True\n'
_NARROWING_CONFIG = json.dumps({"traceability": {"test_roots": ["plugins/*/tests"]}})  # drops "tests"


def test_removal_gate_keeps_default_floor_when_config_narrows(tmp_path):
    # A config whose REPLACE-narrow test_roots drops the conventional ``tests/`` must NOT let a
    # removed FR's still-tagged test in ``tests/`` escape the enforcing removal gate. The gate
    # UNIONs the configured roots with ``default_test_roots``, so it can never scan below the
    # historical floor — a config-only scan here would be a FALSE-GREEN (the regression the union
    # prevents). Config is present in BOTH base and head (steady state), so this is not the
    # base-side-asymmetry case — it is the narrowing-below-floor case.
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_RM_ACTIVE)
    _write(root, "tests/test_legacy.py", _LEGACY_TEST)                     # a CONVENTIONAL dir
    _write(root, "shipwright_compliance_config.json", _NARROWING_CONFIG)   # but config drops "tests"
    _commit(root, "base: narrowing config, tagged legacy test in tests/")
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_RM_REMOVED)     # FR-09.01 -> Removed
    head = _commit(root, "head: remove FR-09.01, leave its tagged test standing")
    _seed_medium(root, "iterate-floor")

    result = check_removal_coverage(root, "iterate-floor", head)
    assert result.ok is False and not result.is_skipped, result.detail
    assert "test_legacy.py" in result.detail


_SPEC_PLUG_ACTIVE = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-10.01 | Plugin flow | Should | unit |\n"
)
_SPEC_PLUG_REMOVED = (
    "# Spec\n\n## Functional Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n\n"
    "## Removed Requirements\n\n"
    "| FR | Description | Priority | Layers |\n|----|----|----|----|\n"
    "| FR-10.01 | Plugin flow | Should | unit |\n"
)
_PLUG_LEGACY_REL = "plugins/demo/tests/test_plugin_legacy.py"
_PLUG_LEGACY = ('import pytest\n\n\n@pytest.mark.covers("FR-10.01")\n'
                "def test_plugin_legacy():\n    assert True\n")


def test_removal_gate_rescans_base_dirs_when_head_drops_the_config(tmp_path):
    # Doubt #1 (the sharp one): the removal-relevant test lives under the CONFIG-OPTED
    # plugins/*/tests — NOT a default dir — so the union floor (default_test_roots) does NOT cover
    # it. The head commit both moves FR-10.01 to Removed AND deletes the traceability config in the
    # same commit, so head's own config resolves to defaults and never scans plugins/*/tests. Only
    # the base-dir re-scan (_base_test_dirs → extra_roots) keeps the head scanning where the base
    # linked the test, so the still-tagged test is caught as a HARD orphan, not false-green.
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PLUG_ACTIVE)
    _write(root, _PLUG_LEGACY_REL, _PLUG_LEGACY)
    _write(root, "shipwright_compliance_config.json",
           json.dumps({"traceability": {"test_roots": ["plugins/*/tests"]}}))
    _commit(root, "base: config opts plugins/*/tests, FR-10.01 covered there")
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_PLUG_REMOVED)      # FR-10.01 -> Removed
    _git(root, "rm", "-q", "shipwright_compliance_config.json")               # DROP the config
    head = _commit(root, "head: remove FR-10.01, delete config, leave its tagged plugin test")
    _seed_medium(root, "iterate-drop")

    result = check_removal_coverage(root, "iterate-drop", head)
    assert result.ok is False and not result.is_skipped, result.detail
    assert "test_plugin_legacy.py" in result.detail


def test_gate_excludes_fixture_path_so_a_fixture_cannot_fake_a_layer(tmp_path):
    # exclude_dirs is load-bearing at the gate: a behaviour-changed FR covered ONLY by a test
    # under an excluded fixtures/ dir must read MISSING — a fixture mini-repo can't fake a required
    # layer. Drop ``configured_prune_dirs`` from ``_build`` and the fixture is scanned + credited →
    # false-green, so this pins the prune threading (and mirrors generate_file's fixture fence).
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC)                        # FR-08.01 | unit
    _write(root, "plugins/demo/tests/fixtures/test_fake.py", _PLUGIN_TEST.replace("test_widget", "test_fake"))
    _write(root, ".gitignore", ".shipwright/compliance/\n")
    _commit(root, "base: only a fixture-path tagged test, no config")
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_CHANGED)
    _write(root, "shipwright_compliance_config.json", _CONFIG)                     # opts plugins, excl fixtures
    head = _commit(root, "head: behaviour delta, only fixture-path coverage")
    _seed_medium(root, "iterate-fx")
    _stage_junit(root, "iterate-fx", "plugins/demo/tests/fixtures/test_fake.py", "test_fake", head)

    result = check_cross_layer_coverage(root, "iterate-fx", head)
    assert result.ok is False and not result.is_skipped, result.detail  # fixture pruned → unit MISSING
    assert "unit" in result.detail


def test_removal_gate_follows_a_renamed_test_into_a_new_dir_when_config_drops(tmp_path):
    # A test moved (git rename) into a BRAND-NEW plugin dir — neither a base-scanned dir nor a
    # default — while the head removes its FR and drops the config. The rename-target re-scan
    # (extra_roots ∪ rename_map targets) keeps head scanning the new dir, so the still-tagged
    # moved test is caught as HARD, not false-green (base-dir re-scan alone would miss the new dir).
    root = tmp_path / "repo"
    _init(root)
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_RM_ACTIVE.replace("FR-09.01", "FR-13.01"))
    _write(root, "plugins/demo/tests/test_moved.py",
           _LEGACY_TEST.replace("FR-09.01", "FR-13.01").replace("test_legacy", "test_moved"))
    _write(root, "shipwright_compliance_config.json",
           json.dumps({"traceability": {"test_roots": ["plugins/*/tests"]}}))
    _commit(root, "base: config opts plugins/*/tests, FR-13.01 covered there")
    _git(root, "checkout", "-q", "-b", "feature")
    _write(root, ".shipwright/planning/app/spec.md", _SPEC_RM_REMOVED.replace("FR-09.01", "FR-13.01"))
    (root / "plugins" / "moved" / "tests").mkdir(parents=True)
    (root / "plugins/demo/tests/test_moved.py").rename(root / "plugins/moved/tests/test_moved.py")
    _git(root, "rm", "-q", "shipwright_compliance_config.json")
    head = _commit(root, "head: remove FR-13.01, drop config, MOVE its tagged test to a new dir")
    _seed_medium(root, "iterate-move")

    result = check_removal_coverage(root, "iterate-move", head)
    assert result.ok is False and not result.is_skipped, result.detail
    assert "test_moved" in result.detail


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
