"""Drift guard: the /shipwright-run master hand-off banner must be
surface-aware, detecting the launch surface via ``CLAUDE_CODE_ENTRYPOINT``.

Locks the honest-banner invariants so a future edit can't regress to the
pre-embedded-terminal "open a NEW terminal and paste this command" behaviour,
and so the VS Code extension / desktop limitation stays surfaced:

  * Step 5 detects the surface via ``CLAUDE_CODE_ENTRYPOINT``.
  * A **chat** surface (VS Code extension / desktop) gets an honest warning
    (the pipeline can't launch a bound phase session there) and is pointed at a
    terminal / the Command Center, with ``/shipwright-iterate`` offered for
    single changes.
  * A **terminal** surface keeps BOTH continue paths — the board (Command
    Center) and the paste card (plain terminal / CLI works without the WebUI, P0).
  * Resume Support is surface-aware too (single source of launch-card truth).
"""

from pathlib import Path


def _skill_text(plugin_root: Path) -> str:
    return (plugin_root / "skills" / "run" / "SKILL.md").read_text(encoding="utf-8")


def test_step5_detects_launch_surface(plugin_root):
    text = _skill_text(plugin_root)
    assert "CLAUDE_CODE_ENTRYPOINT" in text, (
        "the master banner must detect the launch surface"
    )


def test_step5_chat_surface_warns_and_redirects(plugin_root):
    text = _skill_text(plugin_root)
    a_start = text.find("**(a) `surface` is chat")
    b_start = text.find("**(b) `surface` is terminal")
    assert a_start != -1 and b_start != -1 and a_start < b_start, (
        "Step 5 must carry explicit (a) chat / (b) terminal branches"
    )
    branch_a = text[a_start:b_start]
    lower = branch_a.lower()
    assert "can't" in lower or "cannot" in lower, (
        "chat branch must state the pipeline can't launch here"
    )
    assert "Command Center" in branch_a, "chat branch must redirect to the Command Center"
    assert "/shipwright-iterate" in branch_a, (
        "chat branch should offer /shipwright-iterate for single changes"
    )


def test_step5_terminal_branch_keeps_board_and_paste(plugin_root):
    text = _skill_text(plugin_root)
    b_start = text.find("**(b) `surface` is terminal")
    assert b_start != -1
    tail = text[b_start:]
    end = tail.find("\n## ")
    branch_b = tail if end == -1 else tail[:end]
    assert "Task Board" in branch_b and "Continue" in branch_b, (
        "terminal branch must offer the board (Command Center) path"
    )
    assert "claude --session-id" in branch_b, (
        "terminal branch must keep the paste card — the plugin works without the "
        "WebUI (P0)"
    )


def test_resume_support_is_surface_aware(plugin_root):
    text = _skill_text(plugin_root)
    resume_start = text.find("## Resume Support")
    assert resume_start != -1, "Resume Support section must exist"
    resume = text[resume_start:]
    assert "CLAUDE_CODE_ENTRYPOINT" in resume, "Resume Support must branch on the surface"
    assert "Continue" in resume, "Resume Support must offer the board Continue"
    assert "claude --session-id" in resume, (
        "Resume Support must keep the plain-terminal paste card"
    )
