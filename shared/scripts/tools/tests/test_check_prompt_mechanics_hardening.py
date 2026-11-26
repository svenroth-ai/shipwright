"""check_prompt_mechanics.py, fix round: the ways a mechanic could hide from the gate, and the registry contract.

Every test seeds one evasion that the first version let through, plus the pin of the real registry.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # shared/

from scripts.tools import check_prompt_mechanics as cpm  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.09")  # the ratchet that keeps the changelog conversion; no AC is claimed

GH = "gh pr create"
KEYS = ["gh pr create"]


def _kinds(text: str, subs: list[str] | None = None) -> set[str]:
    entry = {"path": "S.md", "commands": KEYS, "substitutions": subs or []}
    found, _ = cpm.check_skill(entry, text)
    return {f.kind for f in found}


@pytest.mark.parametrize("command", [
    GH + " --title \\' ; git push --force origin main",
    GH + ' --title \\" ; git push --force origin main',
    GH + " --title a\\;b ; rm -rf x",
])
def test_a_backslash_outside_quotes_does_not_hide_a_chain(command: str) -> None:
    assert "chain" in _kinds(f"```bash\n{command}\n```\n")


def test_an_escaped_operator_is_not_a_chain() -> None:
    assert _kinds(f"```bash\n{GH} --title a\\;b\n```\n") == set()


def test_a_comment_after_a_word_ends_the_command_and_an_inner_hash_does_not() -> None:
    assert _kinds(f"```bash\n{GH} --title x # && rm -rf y\n```\n") == set()
    assert "chain" in _kinds(f"```bash\n{GH} --title a#b ; rm -rf y\n```\n")


def test_a_closer_must_be_at_least_as_long_and_an_info_string_never_closes() -> None:
    text = f"````text\nsome prose\n````\n\n```bash\n{GH} --x && git push\n```\n"
    assert "chain" in _kinds(text)
    assert [b[2] for b in cpm.fenced_blocks("````text\na\n```\nb\n````\n")] == [["a", "```", "b"]]
    assert [b[2] for b in cpm.fenced_blocks("```bash\na\n```bash\nb\n```\n")] == [["a", "```bash", "b"]]


def test_a_block_after_a_short_fence_line_is_still_read() -> None:
    text = f"```text\nprose\n```\n\n~~~bash\n{GH} --x ; git push\n~~~\n"
    assert "chain" in _kinds(text)


@pytest.mark.parametrize("command", [f"{GH} --x <(git fetch)", f"{GH} --x >(tee log)"])
def test_process_substitution_is_a_substitution(command: str) -> None:
    assert _kinds(f"```bash\n{command}\n```\n") == {"substitution"}


def test_process_substitution_inside_quotes_is_data() -> None:
    assert _kinds(f"```bash\n{GH} --x '<(a)' \"<(b)\"\n```\n") == set()


@pytest.mark.parametrize("label", ["text", "ps1", "cmd", "powershell", "sh", "txt", "{.bash}"])
def test_every_label_except_the_non_shell_list_is_checked(label: str) -> None:
    assert "new-command" in _kinds(f"```{label}\ngit push origin main\n```\n")


@pytest.mark.parametrize("label", ["yaml", "yml", "json", "python", "markdown", "md", "toml", "diff"])
def test_the_non_shell_labels_are_skipped(label: str) -> None:
    assert _kinds(f"```{label}\ngit push origin main\n```\n") == set()


def test_an_unlabelled_block_is_shell_when_any_line_starts_like_a_command() -> None:
    assert "new-command" in _kinds("```\ncd /tmp\ngit push origin main\n```\n")
    assert "new-command" in _kinds("```\nsome note\nnpm publish\n```\n")
    assert "new-command" in _kinds("```\nTOKEN=x curl http://e\n```\n")
    assert "new-command" in _kinds("```\n./release.sh\n```\n")
    assert _kinds("```\nAskUserQuestion:\n  question: ok?\n  options:\n    - Accept\n```\n") == set()


def test_a_blockquote_fence_is_read_through() -> None:
    assert "new-command" in _kinds("> ```bash\n> git push origin main\n> ```\n")


def _validate(registry: object) -> None:
    cpm.validate_registry(registry)


GOOD = {"escape_budget": 0, "skills": [{"path": "S.md", "commands": [], "substitutions": [], "escapes": []}]}


@pytest.mark.parametrize("mutate", [
    lambda r: r.update(escape_budget=True),
    lambda r: r.update(escape_budget="1"),
    lambda r: r["skills"][0].update(commands="uv run x"),
    lambda r: r["skills"][0].update(commands=[1]),
    lambda r: r["skills"][0].update(substitutions="$(pwd)"),
    lambda r: r["skills"][0].update(path=""),
    lambda r: r["skills"][0].update(escapes={}),
    lambda r: r["skills"][0].update(escapes=[{"commands": ["a"]}]),
    lambda r: r["skills"][0].update(escapes=[{"reason": " ", "commands": ["a"]}]),
    lambda r: r["skills"][0].update(escapes=[{"reason": "r", "commands": "a"}]),
    lambda r: r["skills"][0].update(escapes=[{"reason": "r", "commands": []}]),
    lambda r: r.update(skills="x"),
])
def test_a_malformed_registry_is_a_registry_error_never_a_traceback(mutate) -> None:
    registry = json.loads(json.dumps(GOOD))
    mutate(registry)
    with pytest.raises(cpm.RegistryError):
        _validate(registry)


def test_a_good_registry_validates_and_a_non_object_does_not() -> None:
    _validate(GOOD)
    with pytest.raises(cpm.RegistryError):
        _validate([])


def test_the_real_registry_is_pinned() -> None:
    """Widening the registry (a command, a substitution, an escape, the budget) is a test edit, seen in review."""
    registry = cpm.load_registry(cpm.DEFAULT_REGISTRY)
    assert registry["escape_budget"] == 0  # P8a (F2): the preview and the real aggregate call are two blocks now, the one escape went
    (entry,) = registry["skills"]
    assert entry["path"] == "plugins/shipwright-changelog/skills/changelog/SKILL.md"
    assert entry["commands"] == [
        "uv run {plugin_root}/scripts/release.py prepare",
        "uv run {plugin_root}/scripts/release.py aggregate",
        "uv run {plugin_root}/scripts/release.py cancel",  # P8a fix round (D84): Cancel puts back the drop files an Edit changed
        "uv run {plugin_root}/scripts/release.py sync",
        "uv run {plugin_root}/scripts/release.py commit-and-tag",
        "git push origin HEAD",  # P8a (F3, D7): the branch is pushed right before the PR is opened, one literal outward line
        "uv run {plugin_root}/scripts/release.py pr-body",  # P8b (Q10, D15): the PR body as a file for --body-file
        "gh pr create",
        "uv run {plugin_root}/scripts/release.py record-event",
        "gh pr merge",
        "uv run {plugin_root}/scripts/release.py push-tag",
        "uv run {shared_root}/scripts/tools/publish_release_notes.py",
        "uv run {plugin_root}/scripts/release.py close-phase",
    ]
    assert entry["substitutions"] == ["$(pwd)"]
    assert entry["escapes"] == []


def test_every_head_push_block_of_the_changelog_skill_is_exactly_the_no_follow_tags_line() -> None:
    """P8a fix round: the registry keys a command by the words before its first flag, so `git push origin HEAD --tags` would pass
    the gate as the same command. The changelog's head push must never carry the release tag before the merge."""
    registry = cpm.load_registry(cpm.DEFAULT_REGISTRY)
    (entry,) = registry["skills"]
    text = (cpm.DEFAULT_REGISTRY.parents[2] / entry["path"]).read_text(encoding="utf-8")
    pushes = [c for _, lang, body in cpm.fenced_blocks(text) if cpm.is_shell_block(lang, body)
              for c in cpm.logical_commands(body) if cpm.command_key(c) == "git push origin HEAD"]
    assert pushes == ["git push origin HEAD --no-follow-tags"], pushes
