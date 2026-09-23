"""Project-boundary and project-root-key-stability tests for
``codex_activation_mint.py`` (R2 — AC0, AC1a mint half). Split out of
``test_codex_hooks_noop_under_claude.py`` (bloat gate, 2026-09-23) — that
file's own docstring documents the shared direct-import convention these
tests also use."""

from __future__ import annotations

import json
import sys
from pathlib import Path

HOOK_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "codex_activation_mint.py"
)
sys.path.insert(0, str(HOOK_SCRIPT.parent))
from codex_activation_mint import handle_payload  # noqa: E402


def _make_bundle(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "BUILD_MANIFEST.json").write_text(
        json.dumps({"version": "0.0.0-test", "files": {"plugin.json": "0" * 64}}),
        encoding="utf-8",
    )
    codex_plugin_dir = root / ".codex-plugin"
    codex_plugin_dir.mkdir(parents=True, exist_ok=True)
    (codex_plugin_dir / "plugin.json").write_text(
        json.dumps({"hooks": {"hooks": {}}}), encoding="utf-8"
    )


def _make_project(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "shipwright_run_config.json").write_text("{}", encoding="utf-8")


class TestProjectBoundaryGuard:
    """Code review HIGH: a genuine Codex bundle plus a NON-Shipwright cwd
    (no config marker, no ``.shipwright/agent_docs/``) must still no-op --
    ``is_codex_runtime()`` alone is bundle-shape only, not project-scoped,
    so without this guard every Codex session anywhere on the machine would
    mint an activation record for whatever directory it happens to run in."""

    def test_non_shipwright_cwd_writes_nothing(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        bundle = tmp_path / "bundle"
        _make_bundle(bundle)
        monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(bundle))
        # tmp_path deliberately carries no Shipwright marker.
        payload = {"session_id": "s1", "turn_id": "t1", "cwd": str(tmp_path), "prompt": "hello"}
        handle_payload(payload)
        assert not (tmp_path / ".shipwright").exists()


class TestProjectRootKeyStability:
    """Code review HIGH: ``project_root`` is ``mint()``'s own exclusive-
    create KEY (alongside ``session_id``), so it must be STABLE across a
    session's calls, not recomputed from whatever the invocation cwd
    happens to be on each call. Pins both calls' ``project_root`` through
    the same git main-repo-root canonicalization
    ``codex_activation_record``'s own ``normalize_cwd()`` already applies to
    the record's ``cwd`` field, so an invocation-cwd difference between two
    calls for the SAME session (subdirectory, worktree) can never split
    state across two different storage paths."""

    def test_varying_invocation_cwd_still_shares_one_record(self, monkeypatch, tmp_path):
        bundle = tmp_path / "bundle"
        _make_bundle(bundle)
        monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(bundle))

        import lib.codex_activation_record as car

        canonical_root = tmp_path / "canonical-repo"
        _make_project(canonical_root)
        # The hook's own resolver now delegates directly to the library's
        # normalize_cwd(), so patching car.git_base alone covers both.
        monkeypatch.setattr(car.git_base, "main_repo_root", lambda p: canonical_root)

        first_payload = {
            "session_id": "s1",
            "turn_id": "t1",
            "cwd": str(tmp_path / "worktrees" / "foo"),
            "prompt": "ordinary first message, unarmed",
        }
        handle_payload(first_payload)

        second_payload = {
            "session_id": "s1",
            "turn_id": "t2",
            "cwd": str(tmp_path / "main-checkout"),  # deliberately a DIFFERENT literal cwd
            "prompt": "ordinary second message, unarmed",
        }
        handle_payload(second_payload)

        record_dir = canonical_root / ".shipwright" / "runtime" / "codex-activation"
        assert record_dir.is_dir()
        records = list(record_dir.glob("*.json"))
        assert len(records) == 1  # not split across two different project_root paths
        record = json.loads(records[0].read_text(encoding="utf-8"))
        assert record["turn_id"] == "t1"  # first call's verdict, unchanged by the second
