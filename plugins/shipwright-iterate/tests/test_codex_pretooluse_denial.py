"""Tests for ``codex_pretooluse_gate.py`` (R2 — AC1a, PreToolUse half).

Direct-import convention mirrors ``test_codex_hooks_noop_under_claude.py``:
insert the hook's own directory on ``sys.path`` and import its functions
directly, so ``is_codex_runtime()``'s env-var/bundle-shape fixtures and the
activation record's own storage can be set up precisely per test.

Per the mini-plan's Step 6 scope decision: the allow/deny matrix is built
here for the ``Bash`` class only (confirmed live by R0) plus default-deny for
every other/unrecognized class. Full per-real-class fixture coverage beyond
the synthetic "unknown class" case below is DEFERRED to this run's end-of-run
live payload-capture probe (Step 2/10) — Codex's complete locally-hook-
visible tool-name inventory beyond ``Bash``/``Agent`` is not yet captured."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

HOOK_SCRIPT = (
    Path(__file__).resolve().parent.parent / "scripts" / "hooks" / "codex_pretooluse_gate.py"
)
sys.path.insert(0, str(HOOK_SCRIPT.parent))
import codex_pretooluse_gate  # noqa: E402
from codex_pretooluse_gate import handle_payload  # noqa: E402

sys.path.insert(0, str(HOOK_SCRIPT.parent.parent.parent.parent / "shared" / "scripts"))
from lib.codex_activation_record import mint  # noqa: E402


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
    """Marks *root* as a Shipwright project (``is_shipwright_project``'s
    config-marker arm) -- required since the HIGH project-boundary guard
    (code review) so fixtures anchored on a bare ``tmp_path`` still resolve
    as in-scope."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "shipwright_run_config.json").write_text("{}", encoding="utf-8")


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for var in (
        "SHIPWRIGHT_PLUGIN_ROOT",
        "PLUGIN_ROOT",
        "CLAUDE_PLUGIN_ROOT",
        "SHIPWRIGHT_PROJECT_ROOT",
    ):
        monkeypatch.delenv(var, raising=False)


@pytest.fixture
def bundle_env(monkeypatch, tmp_path):
    """A real Codex bundle resolvable via SHIPWRIGHT_PLUGIN_ROOT, and the
    hook's own git-root resolver made a no-op (returns cwd unchanged) so the
    test's own tmp_path IS the record storage root, deterministically."""
    monkeypatch.chdir(tmp_path)
    bundle = tmp_path / "bundle"
    _make_bundle(bundle)
    _make_project(tmp_path)
    monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(bundle))
    import lib.codex_activation_record as car

    # The hook's own resolver now delegates directly to the library's
    # normalize_cwd(), so patching car.git_base alone covers both.
    monkeypatch.setattr(car.git_base, "main_repo_root", lambda p: Path(p))
    return tmp_path


def _mint_armed(project_root: Path, session_id: str = "s1") -> None:
    mint(
        project_root,
        session_id=session_id,
        turn_id="t1",
        cwd=str(project_root),
        armed=True,
        skill_id="shipwright-iterate:iterate",
        args={},
    )


def _mint_unarmed(project_root: Path, session_id: str = "s1") -> None:
    mint(project_root, session_id=session_id, turn_id="t1", cwd=str(project_root), armed=False)


def _payload(session_id: str, cwd: Path, tool_name: str, command: str | None = None) -> dict:
    payload = {"session_id": session_id, "turn_id": "t2", "cwd": str(cwd), "tool_name": tool_name}
    if command is not None:
        payload["tool_input"] = {"command": command}
    return payload


class TestAC0NoOpUnderClaude:
    def test_no_op_when_plugin_root_not_set(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        _mint_armed(tmp_path)
        payload = _payload("s1", tmp_path, "Bash", "rm -rf /")
        assert handle_payload(payload) is None

    def test_no_op_with_wrong_value_plugin_root(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        unrelated = tmp_path / "unrelated"
        unrelated.mkdir()
        monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(unrelated))
        _mint_armed(tmp_path)
        payload = _payload("s1", tmp_path, "Bash", "rm -rf /")
        assert handle_payload(payload) is None


class TestAC1aThreeFixtures:
    @pytest.mark.covers("FR-01.21/AC06")
    def test_armed_wrong_first_call_denies(self, bundle_env):
        """@covers FR-01.21/AC06 — an armed session's first non-setup call is
        denied with the resolved setup command in the reason."""
        _mint_armed(bundle_env)
        payload = _payload("s1", bundle_env, "Bash", "ls -la")
        decision = handle_payload(payload)
        assert decision is not None
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert "setup_iterate_worktree.py" in reason
        assert "uv run" in reason
        assert "{shared_root}" not in reason  # a real resolved path, not an unresolved template

    def test_armed_correct_first_call_allows(self, bundle_env):
        _mint_armed(bundle_env)
        payload = _payload("s1", bundle_env, "Bash", "uv run setup_iterate_worktree.py --slug x")
        assert handle_payload(payload) is None

    def test_unarmed_never_denies(self, bundle_env):
        """@covers FR-01.21/AC06 — an unarmed session's first call is never
        denied, regardless of what it calls first. It now returns a visible
        allow-warning (see TestUnarmedVisibilityWarning below), not bare
        ``None`` — the assertion here is specifically "never a deny"."""
        _mint_unarmed(bundle_env)
        payload = _payload("s1", bundle_env, "Bash", "rm -rf /")
        decision = handle_payload(payload)
        assert decision is not None
        assert decision["hookSpecificOutput"]["permissionDecision"] != "deny"


class TestUnarmedVisibilityWarning:
    """@covers FR-01.21/AC06 — R0-named gap 2 (Unarmed-launch visibility):
    the fail-open default must never be silent. The session's genuinely-
    first eligible PreToolUse call, when unarmed, surfaces a visible,
    non-blocking warning exactly once — never a deny."""

    def test_first_unarmed_call_returns_visible_allow_warning(self, bundle_env):
        _mint_unarmed(bundle_env)
        payload = _payload("s1", bundle_env, "Bash", "ls -la")
        decision = handle_payload(payload)

        assert decision is not None
        output = decision["hookSpecificOutput"]
        assert output["hookEventName"] == "PreToolUse"
        assert output["permissionDecision"] == "allow"
        reason = output["permissionDecisionReason"]
        assert "unarmed" in reason.lower()
        assert "not" in reason.lower()  # "will NOT be enforced"

    def test_second_unarmed_call_is_silent(self, bundle_env):
        """The warning fires exactly once — consume()'s own exclusivity
        settles the session on the first eligible call; a later call in the
        same unarmed session gets plain silent allow, not a repeat warning."""
        _mint_unarmed(bundle_env)
        first = _payload("s1", bundle_env, "Bash", "ls -la")
        first_decision = handle_payload(first)
        assert first_decision is not None  # the warning, once

        second = _payload("s1", bundle_env, "Bash", "rm -rf /")
        assert handle_payload(second) is None  # settled -> silent from here on


class TestUnknownClassDefaultDeny:
    def test_unrecognized_tool_class_denies_by_default(self, bundle_env):
        """Synthetic fixture proving the default-deny path for any class
        other than the currently-confirmed `Bash` -- NOT a real Codex tool
        name, per the mini-plan's deferred-live-probe scope decision."""
        _mint_armed(bundle_env)
        payload = _payload("s1", bundle_env, "SomeUnconfirmedLocalTool")
        decision = handle_payload(payload)
        assert decision is not None
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"


class TestSecondCallNeverReEvaluates:
    def test_second_call_after_settled_always_allows(self, bundle_env):
        """Wiring test: the settled-flag is Step 4's own consume()
        exclusivity, not re-proved here -- this proves the hook does not
        somehow re-derive or re-check after the first call already decided."""
        _mint_armed(bundle_env)
        first = _payload("s1", bundle_env, "Bash", "ls -la")
        first_decision = handle_payload(first)
        assert first_decision is not None  # first call denied, as expected

        second = _payload("s1", bundle_env, "Bash", "rm -rf /")
        assert handle_payload(second) is None  # settled -> always allow now

    def test_second_call_after_allowed_first_still_allows(self, bundle_env):
        _mint_armed(bundle_env)
        first = _payload("s1", bundle_env, "Bash", "uv run setup_iterate_worktree.py")
        assert handle_payload(first) is None

        second = _payload("s1", bundle_env, "Bash", "rm -rf /")
        assert handle_payload(second) is None


class TestProjectBoundaryGuard:
    """Code review HIGH: a genuine Codex bundle plus a NON-Shipwright cwd
    (no config marker, no ``.shipwright/agent_docs/``) must still no-op --
    ``is_codex_runtime()`` alone is bundle-shape only, not project-scoped,
    so without this guard an armed-and-unsettled record for an unrelated
    directory would still gate every tool call in it."""

    def test_non_shipwright_cwd_never_denies(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        bundle = tmp_path / "bundle"
        _make_bundle(bundle)
        monkeypatch.setenv("SHIPWRIGHT_PLUGIN_ROOT", str(bundle))
        import lib.codex_activation_record as car

        monkeypatch.setattr(car.git_base, "main_repo_root", lambda p: Path(p))
        # tmp_path deliberately carries no Shipwright marker.
        _mint_armed(tmp_path)
        payload = _payload("s1", tmp_path, "Bash", "rm -rf /")
        assert handle_payload(payload) is None


class TestMainNeverRaises:
    def test_main_never_raises_on_garbage_stdin(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
        assert codex_pretooluse_gate.main() == 0

    def test_main_never_raises_on_non_dict_json(self, monkeypatch):
        monkeypatch.setattr(sys, "stdin", io.StringIO("[1, 2, 3]"))
        assert codex_pretooluse_gate.main() == 0

    def test_no_op_when_session_id_absent(self, bundle_env):
        payload = {"cwd": str(bundle_env), "tool_name": "Bash", "tool_input": {"command": "ls"}}
        assert handle_payload(payload) is None
