"""`check_ac_ratchet_f0.py` - the F0 mirror of ci.yml's `AC coverage ratchet (gate)`.

The property that matters is NO SELF-VOUCHING and NO MUTATION: the manifest the ratchet
reads is regenerated in a scratch copy from F0's retained JUnit, and the real working tree
(whose committed manifest is a tracked file) is left byte-for-byte alone.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import scripts.tools.check_ac_ratchet_f0 as mod  # noqa: E402
from scripts.tools.suite_retention import Retention  # noqa: E402
from scripts.tools.suite_units import Unit  # noqa: E402

MANIFEST_REL = Path(".shipwright/compliance/test-traceability.json")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    plugin = root / "plugins" / "shipwright-x"
    (plugin / "tests").mkdir(parents=True)
    (plugin / "pyproject.toml").write_text("", encoding="utf-8")
    (plugin / "tests" / "test_a.py").write_text("def test_a():\n    pass\n", encoding="utf-8")
    (root / MANIFEST_REL).parent.mkdir(parents=True)
    (root / MANIFEST_REL).write_text('{"committed": true}\n', encoding="utf-8")
    (root / "plugins" / "shipwright-compliance").mkdir()
    (root / "plugins" / "shipwright-compliance" / "marker.txt").write_text("x", encoding="utf-8")
    (root / "shipwright_ac_coverage_baseline.json").write_text("{}", encoding="utf-8")
    (root / ".gitignore").write_text("ignored.txt\n.scratch/\n", encoding="utf-8")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    return root


def _publish(root: Path, run_id: str, outcome: str = "pass") -> None:
    retention = Retention(project_root=root, run_id=run_id)
    report = root.parent / "r.xml"
    report.write_text("<testsuites/>", encoding="utf-8")
    unit = Unit(id="shipwright-x", cwd="plugins/shipwright-x", target="tests")
    retention.record(unit, report, outcome)
    retention.publish()


class TestSnapshotTree:
    def test_copies_tracked_and_untracked_but_not_ignored_or_deleted(self, tmp_path):
        root = _project(tmp_path)
        (root / "untracked.py").write_text("x = 1\n", encoding="utf-8")
        (root / "ignored.txt").write_text("nope", encoding="utf-8")
        (root / "plugins/shipwright-x/tests/test_a.py").unlink()
        dest = tmp_path / "dest"
        dest.mkdir()
        mod.snapshot_tree(root, dest)
        assert (dest / "untracked.py").read_text(encoding="utf-8") == "x = 1\n"
        assert (dest / MANIFEST_REL).is_file()
        assert not (dest / "ignored.txt").exists()
        assert not (dest / "plugins/shipwright-x/tests/test_a.py").exists()

    def test_uses_the_working_tree_bytes_not_the_index(self, tmp_path):
        root = _project(tmp_path)
        (root / "plugins/shipwright-x/tests/test_a.py").write_text("# edited\n", encoding="utf-8")
        dest = tmp_path / "dest"
        dest.mkdir()
        mod.snapshot_tree(root, dest)
        copied = dest / "plugins/shipwright-x/tests/test_a.py"
        assert copied.read_text(encoding="utf-8") == "# edited\n"


class TestSymlinks:
    def test_symlinks_are_skipped_never_followed_or_recreated(self, tmp_path):
        import pytest
        root = _project(tmp_path)
        outside = tmp_path / "outside.txt"
        outside.write_text("secret", encoding="utf-8")
        try:
            (root / "link.txt").symlink_to(outside)
            (root / "dangling.txt").symlink_to(tmp_path / "nowhere")
        except OSError:
            pytest.skip("host cannot create symlinks")
        dest = tmp_path / "dest"
        dest.mkdir()
        mod.snapshot_tree(root, dest)
        assert not (dest / "link.txt").exists() and not (dest / "link.txt").is_symlink()
        assert not (dest / "dangling.txt").is_symlink()


class TestSymlinkedAncestors:
    def test_nothing_is_copied_through_a_symlinked_directory(self, tmp_path):
        import pytest
        outside = tmp_path / "outside"
        outside.mkdir()
        (outside / "leak.py").write_text("secret = 1", encoding="utf-8")
        root = _project(tmp_path)
        try:
            (root / "viadir").symlink_to(outside, target_is_directory=True)
        except OSError:
            pytest.skip("host cannot create symlinks")
        dest = tmp_path / "dest"
        dest.mkdir()
        mod.snapshot_tree(root, dest)
        assert not (dest / "viadir" / "leak.py").exists()
        assert not any(outside.glob("*.tmp"))  # and nothing was written outside scratch
        assert mod._has_symlinked_ancestor(root, root / "viadir" / "leak.py")

    def test_a_link_between_root_and_path_is_detected_on_any_host(self, tmp_path, monkeypatch):
        root = _project(tmp_path)
        linked = root / "plugins"
        real = Path.is_symlink
        monkeypatch.setattr(Path, "is_symlink", lambda self: self == linked or real(self))
        assert mod._has_symlinked_ancestor(root, linked / "shipwright-x" / "tests" / "test_a.py")
        # the root itself being a link is the caller's choice, not an ancestor INSIDE it
        monkeypatch.setattr(Path, "is_symlink", lambda self: self == root or real(self))
        assert not mod._has_symlinked_ancestor(root, linked / "shipwright-x" / "pyproject.toml")

    def test_ordinary_nested_paths_are_not_flagged(self, tmp_path):
        root = _project(tmp_path)
        nested = root / "plugins" / "shipwright-x" / "tests" / "test_a.py"
        assert not mod._has_symlinked_ancestor(root, nested)


class TestRefusals:
    def test_no_retained_run_is_an_infra_fault(self, tmp_path, capsys):
        root = _project(tmp_path)
        assert mod.run(root, "missing") == mod.EXIT_INFRA
        assert "no published F0 retention run" in capsys.readouterr().err

    def test_a_red_retained_run_is_refused(self, tmp_path, capsys):
        root = _project(tmp_path)
        _publish(root, "r1", outcome="fail")
        assert mod.run(root, "r1") == mod.EXIT_INFRA
        assert "not fully green" in capsys.readouterr().err

    def test_regeneration_failure_is_an_infra_fault_and_leaves_no_scratch(
            self, tmp_path, monkeypatch, capsys):
        root = _project(tmp_path)
        _publish(root, "r1")
        seen: list[Path] = []

        def boom(scratch, plugin_root=None):
            seen.append(scratch)
            raise mod._regen.DriftCheckError("regen exploded")

        monkeypatch.setattr(mod._regen, "regenerate_manifest", boom)
        assert mod.run(root, "r1") == mod.EXIT_INFRA
        assert "regen exploded" in capsys.readouterr().err
        assert not seen[0].exists()


class TestNoSelfVouching:
    def _fake_ratchet(self, tmp_path: Path, monkeypatch, exit_code: int) -> Path:
        probe = tmp_path / "probe.json"
        script = tmp_path / "fake_ratchet.py"
        script.write_text(
            "import json, sys\n"
            "from pathlib import Path\n"
            "root = Path(sys.argv[sys.argv.index('--project-root') + 1])\n"
            "evidence = root / '.shipwright/compliance/evidence'\n"
            f"Path({str(probe)!r}).write_text(json.dumps({{\n"
            "  'root': str(root),\n"
            "  'manifest': (root / '.shipwright/compliance/test-traceability.json').read_text(),\n"
            "  'staged': sorted(p.name for p in evidence.glob('junit-*.xml')),\n"
            "}))\n"
            f"print('verdict'); sys.exit({exit_code})\n",
            encoding="utf-8",
        )
        monkeypatch.setattr(mod, "_RATCHET", script)
        return probe

    def _fake_regen(self, monkeypatch) -> None:
        def regen(scratch, plugin_root=None):
            (scratch / MANIFEST_REL).write_text('{"regenerated": true}\n', encoding="utf-8")

        monkeypatch.setattr(mod._regen, "regenerate_manifest", regen)

    def test_ratchet_reads_the_regenerated_manifest_and_real_tree_is_untouched(
            self, tmp_path, monkeypatch, capsys):
        root = _project(tmp_path)
        _publish(root, "r1")
        before = (root / MANIFEST_REL).read_bytes()
        probe = self._fake_ratchet(tmp_path, monkeypatch, exit_code=0)
        self._fake_regen(monkeypatch)

        assert mod.run(root, "r1") == mod.EXIT_OK

        seen = json.loads(probe.read_text(encoding="utf-8"))
        assert seen["manifest"] == '{"regenerated": true}\n'  # not the committed one
        assert seen["staged"] == ["junit-01.xml"]  # F0's retained report, staged in scratch
        assert Path(seen["root"]).resolve() != root.resolve()
        assert (root / MANIFEST_REL).read_bytes() == before
        assert not (root / ".shipwright/compliance/evidence").exists()
        assert not Path(seen["root"]).exists()  # scratch cleaned up
        assert "verdict" in capsys.readouterr().out

    def test_the_ratchet_exit_code_is_relayed(self, tmp_path, monkeypatch):
        root = _project(tmp_path)
        _publish(root, "r1")
        self._fake_ratchet(tmp_path, monkeypatch, exit_code=1)
        self._fake_regen(monkeypatch)
        assert mod.run(root, "r1") == mod.EXIT_BLOCKED


class TestGuardsAndBoundaries:
    def test_a_project_without_the_gate_is_a_noop(self, tmp_path, capsys):
        root = _project(tmp_path)
        (root / "shipwright_ac_coverage_baseline.json").unlink()
        assert mod.run(root, "anything") == mod.EXIT_OK
        assert "SKIP" in capsys.readouterr().out

    def test_main_parses_argv_and_reports_a_missing_run(self, tmp_path):
        root = _project(tmp_path)
        assert mod.main(["--project-root", str(root), "--run-id", "missing"]) == mod.EXIT_INFRA

    def test_a_non_git_root_is_an_infra_fault(self, tmp_path, capsys):
        import shutil
        root = _project(tmp_path)
        _publish(root, "r1")
        shutil.rmtree(root / ".git", ignore_errors=True)
        assert mod.run(root, "r1") == mod.EXIT_INFRA
        assert "scratch manifest" in capsys.readouterr().err

    def test_a_ratchet_timeout_is_exit_2_not_the_blocked_code(self, tmp_path, monkeypatch, capsys):
        root = _project(tmp_path)
        _publish(root, "r1")
        script = tmp_path / "sleepy.py"
        script.write_text("import time\ntime.sleep(30)\n", encoding="utf-8")
        monkeypatch.setattr(mod, "_RATCHET", script)
        monkeypatch.setattr(mod, "_TIMEOUT_SECONDS", 1)
        monkeypatch.setattr(mod._regen, "regenerate_manifest", lambda scratch, plugin_root=None: None)
        assert mod.run(root, "r1") == mod.EXIT_INFRA
        assert "unexpected failure" in capsys.readouterr().err

    def test_scratch_lives_under_the_short_gitignored_dir(self, tmp_path, monkeypatch):
        root = _project(tmp_path)
        _publish(root, "r1")
        seen: list[Path] = []
        monkeypatch.setattr(mod._regen, "regenerate_manifest",
                            lambda scratch, plugin_root=None: seen.append(scratch))
        monkeypatch.setattr(mod, "_RATCHET", tmp_path / "missing.py")
        mod.run(root, "r1")
        assert seen[0].parent == root / ".scratch"


class _Done:
    returncode = 0
    stderr = ""


class TestRegenerateManifestOverride:
    def test_override_passes_code_root_then_data_root_and_freezes(self, tmp_path, monkeypatch):
        import scripts.tools.ci_manifest_drift_check as regen
        calls: list[list[str]] = []
        monkeypatch.setattr(regen.subprocess, "run", lambda argv, **kw: calls.append(argv) or _Done())
        data, code = tmp_path / "data", tmp_path / "code"
        data.mkdir()
        regen.regenerate_manifest(data, plugin_root=code)
        argv = calls[0]
        assert "--frozen" in argv
        assert argv[argv.index("--project") + 1] == str(code)
        assert argv[-2:] == [str(code), str(data)]  # plugin_root, then project_root

    def test_default_keeps_unfrozen_in_tree_behaviour(self, tmp_path, monkeypatch):
        import scripts.tools.ci_manifest_drift_check as regen
        calls: list[list[str]] = []
        monkeypatch.setattr(regen.subprocess, "run", lambda argv, **kw: calls.append(argv) or _Done())
        regen.regenerate_manifest(tmp_path)
        assert "--frozen" not in calls[0]
        in_tree = tmp_path / "plugins" / "shipwright-compliance"
        assert calls[0][calls[0].index("--project") + 1] == str(in_tree)
