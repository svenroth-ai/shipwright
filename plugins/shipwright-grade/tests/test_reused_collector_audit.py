"""Reused-collector audit (Gemini #5 / GPT #14): the adopt detectors we import
are read-only — no package-manager execution, no shell interpolation, no writes,
no symlink-escape. This test pins the audit documented in ``detectors_bridge``.
"""

from __future__ import annotations

from pathlib import Path

from detectors_bridge import _adopt_lib_dir, detect_all
from repo_context import RepoContext
from resolve_target import resolve_target

_REUSED = ("stack_detector", "test_framework_detector", "feature_inferrer", "ci_detector")

# Tokens that would mean a reused detector is not purely read-only.
_FORBIDDEN = (
    "os.system(", "shell=True", "subprocess", "Popen", "check_call",
    ".write_text(", ".write_bytes(", "os.remove(", "os.rmdir(", "shutil.",
    "eval(", "exec(",
)


class TestReusedCollectorsAreReadOnly:
    def test_source_has_no_side_effecting_tokens(self):
        lib_dir = _adopt_lib_dir()
        assert lib_dir is not None, "adopt lib dir must be resolvable in the monorepo"
        for mod in _REUSED:
            src = (lib_dir / f"{mod}.py").read_text(encoding="utf-8")
            for token in _FORBIDDEN:
                assert token not in src, f"{mod}.py contains forbidden token {token!r}"

    def test_detect_all_writes_nothing(self, well_run_repo: Path):
        before = sorted(p.name for p in well_run_repo.iterdir())
        detect_all(well_run_repo)
        after = sorted(p.name for p in well_run_repo.iterdir())
        assert before == after

    def test_detect_all_degrades_on_non_repo(self, non_git_dir: Path):
        # A directory with no manifests → neutral defaults, never a crash.
        out = detect_all(non_git_dir)
        assert out["features"] == []
        assert out["ci"]["provider"] is None


class TestReadTextIsWithinRoot:
    def test_symlink_escape_and_traversal_return_empty(self, well_run_repo: Path):
        ctx = RepoContext(resolve_target(str(well_run_repo)))
        assert ctx.read_text("../secret.txt") == ""
        assert ctx.read_text("../../etc/passwd") == ""
        # a real in-root file still reads
        assert "FastAPI" in ctx.read_text("app/api.py")
