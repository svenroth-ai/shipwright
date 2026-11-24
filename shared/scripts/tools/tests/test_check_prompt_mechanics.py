"""check_prompt_mechanics.py: a converted skill's prose may not take mechanics back.

Each test builds a tiny throwaway skill and seeds exactly one regression, so a failure names it. One test
runs the real registry against the real thin SKILL.md: the ratchet must pass what P5 delivered.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # shared/

from scripts.tools import check_prompt_mechanics as cpm  # noqa: E402

pytestmark = pytest.mark.covers("FR-01.09")  # the ratchet that keeps the changelog conversion; no AC is claimed

ONE = 'uv run "{plugin_root}/scripts/release.py" prepare --project-root .'
TWO = 'uv run "{plugin_root}/scripts/release.py" sync --project-root .'
KEYS = ["uv run {plugin_root}/scripts/release.py prepare", "uv run {plugin_root}/scripts/release.py sync"]
REPO = Path(__file__).resolve().parents[4]
TILDE_BLOCK = """~~~console
git tag v1
~~~
"""


def fenced(command: str) -> str:
    return f"```bash\n{command}\n```\n"


def _run(tmp_path: Path, prose: str, commands=None, escapes=None, budget: int | None = None) -> list[cpm.Finding]:
    (tmp_path / "SKILL.md").write_text(prose, encoding="utf-8")
    entry = {"path": "SKILL.md", "commands": KEYS if commands is None else commands, "escapes": escapes or []}
    return cpm.check_registry({"skills": [entry], "escape_budget": len(escapes or []) if budget is None else budget}, tmp_path)


def _kinds(findings: list[cpm.Finding]) -> list[str]:
    return [f.kind for f in findings]


def test_a_thin_skill_passes(tmp_path: Path) -> None:
    prose = f"# Skill\n\n```bash\n{ONE} \\\n  --version 1\n```\n\nText with `uv run x && y` inline.\n\n```\nAskUserQuestion: ok\n```\n"
    assert _run(tmp_path, prose) == []


def test_an_and_chain_in_a_block_is_refused(tmp_path: Path) -> None:
    assert _kinds(_run(tmp_path, f"```bash\n{ONE} && echo done\n```\n")) == ["chain"]


def test_a_pipe_is_refused_and_a_pipe_inside_quotes_is_not(tmp_path: Path) -> None:
    assert _kinds(_run(tmp_path, f"```bash\n{ONE} | jq .\n```\n")) == ["chain"]
    assert _run(tmp_path, f'```bash\n{ONE} --note "a | b; c && d"\n```\n') == []


def test_a_redirect_is_not_a_chain(tmp_path: Path) -> None:
    assert _run(tmp_path, f"```bash\n{ONE} 2>&1\n```\n") == []
    assert _kinds(_run(tmp_path, f"```bash\n{ONE} &\n```\n")) == ["chain"]


def test_two_commands_in_one_block_are_refused(tmp_path: Path) -> None:
    assert _kinds(_run(tmp_path, f"```sh\n{ONE}\n{TWO}\n```\n")) == ["multi"]


def test_a_new_shell_command_is_refused(tmp_path: Path) -> None:
    found = _run(tmp_path, "```bash\ngit tag -a v1 -m x\n```\n")
    assert _kinds(found) == ["new-command"] and "git tag -a" in found[0].message


def test_a_known_command_with_a_new_flag_is_not_new(tmp_path: Path) -> None:
    assert _run(tmp_path, f"```bash\n{ONE} --brand-new-flag\n```\n") == []


def test_an_unlabelled_block_that_looks_like_shell_is_checked(tmp_path: Path) -> None:
    assert _kinds(_run(tmp_path, "```\ngit push origin main\n```\n")) == ["new-command"]
    assert _run(tmp_path, "```yaml\ngit push origin main\n```\n") == []


def test_comments_blank_lines_and_prompts_are_not_commands(tmp_path: Path) -> None:
    assert _run(tmp_path, f"```bash\n# why\n\n$ {ONE}\n```\n") == []


def test_an_unparseable_line_is_a_finding_not_a_crash(tmp_path: Path) -> None:
    assert _kinds(_run(tmp_path, '```bash\nuv run "unclosed\n```\n')) == ["new-command"]


def test_an_exact_escape_passes_and_a_stale_one_is_a_finding(tmp_path: Path) -> None:
    prose = f"```bash\n{ONE}\n{TWO}\n```\n"
    escape = {"reason": "pair", "commands": [ONE, TWO]}
    assert _run(tmp_path, prose, escapes=[escape]) == []
    assert _kinds(_run(tmp_path, f"```bash\n{ONE}\n```\n", escapes=[escape])) == ["stale-escape"]
    changed = {"reason": "pair", "commands": [ONE, TWO + " --x"]}
    assert set(_kinds(_run(tmp_path, prose, escapes=[changed]))) == {"multi", "stale-escape"}


def test_the_escape_budget_is_a_cap(tmp_path: Path) -> None:
    prose = f"```bash\n{ONE}\n{TWO}\n```\n"
    escape = {"reason": "pair", "commands": [ONE, TWO]}
    assert _kinds(_run(tmp_path, prose, escapes=[escape], budget=0)) == ["escape-budget"]


def test_a_budget_above_the_count_is_slack_and_a_finding(tmp_path: Path) -> None:
    assert _kinds(_run(tmp_path, fenced(ONE), budget=1)) == ["escape-budget"]


def test_one_escape_excuses_one_block_only(tmp_path: Path) -> None:
    block = fenced(f"{ONE}\n{TWO}")
    escape = {"reason": "pair", "commands": [ONE, TWO]}
    assert _kinds(_run(tmp_path, block + "\n" + block, escapes=[escape])) == ["escape-reuse"]


def test_crlf_prose_is_read_like_lf(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_bytes(f"```bash\r\n{ONE} \\\r\n  --version 1\r\n```\r\n".encode())
    entry = {"path": "SKILL.md", "commands": KEYS}
    assert cpm.check_registry({"skills": [entry], "escape_budget": 0}, tmp_path) == []


def test_tilde_fences_and_console_blocks_are_checked(tmp_path: Path) -> None:
    assert _kinds(_run(tmp_path, TILDE_BLOCK)) == ["new-command"]


def test_an_unregistered_command_substitution_is_refused_even_in_quotes(tmp_path: Path) -> None:
    assert _kinds(_run(tmp_path, fenced(f'{ONE} --x "$(git fetch && git reset --hard)"'))) == ["substitution"]
    assert _kinds(_run(tmp_path, fenced(f"{ONE} --x `date`"))) == ["substitution"]
    assert _run(tmp_path, fenced(f"{ONE} --x '$(not run)'")) == []
    assert set(_kinds(_run(tmp_path, fenced(f"{ONE} --x $(a); b")))) == {"substitution", "chain"}


def test_an_apostrophe_inside_double_quotes_does_not_hide_a_substitution(tmp_path: Path) -> None:
    assert _kinds(_run(tmp_path, fenced(f"""{ONE} --note "don't $(touch /tmp/x)" """))) == ["substitution"]


def test_a_leading_comment_does_not_hide_an_unlabelled_shell_block(tmp_path: Path) -> None:
    assert _kinds(_run(tmp_path, "```\n# publish\ngit push origin main\n```\n")) == ["new-command"]


def test_a_nested_fence_line_does_not_end_the_block_early(tmp_path: Path) -> None:
    prose = f"````bash\n{ONE}\n```\ngit push origin main\n````\n"
    found = _run(tmp_path, prose)
    assert any(f.kind == "new-command" and "git push" in f.message for f in found)


def test_a_registered_substitution_passes(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text(fenced(f'{ONE} --x "$(pwd)"'), encoding="utf-8")
    entry = {"path": "SKILL.md", "commands": KEYS, "substitutions": ["$(pwd)"]}
    assert cpm.check_registry({"skills": [entry], "escape_budget": 0}, tmp_path) == []


def test_a_trailing_comment_is_not_part_of_the_key(tmp_path: Path) -> None:
    assert _run(tmp_path, fenced(f"{ONE} # why")) == []


def test_a_malformed_entry_or_undecodable_skill_is_exit_two(tmp_path: Path, capsys) -> None:
    reg = tmp_path / "r.json"
    reg.write_text('{"escape_budget": 0, "skills": [{"commands": []}]}', encoding="utf-8")
    assert cpm.main(["--project-root", str(tmp_path), "--registry", str(reg)]) == 2
    (tmp_path / "SKILL.md").write_bytes(b"\xff\xfe\x00bad")
    reg.write_text('{"escape_budget": 0, "skills": [{"path": "SKILL.md", "commands": []}]}', encoding="utf-8")
    assert cpm.main(["--project-root", str(tmp_path), "--registry", str(reg)]) == 2
    capsys.readouterr()


def test_a_missing_skill_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(cpm.RegistryError):
        cpm.check_registry({"skills": [{"path": "nope.md"}], "escape_budget": 0}, tmp_path)


def test_a_malformed_registry_is_an_error(tmp_path: Path) -> None:
    bad = tmp_path / "r.json"
    bad.write_text('{"skills": []}', encoding="utf-8")
    with pytest.raises(cpm.RegistryError):
        cpm.load_registry(bad)
    with pytest.raises(cpm.RegistryError):
        cpm.load_registry(tmp_path / "absent.json")


def _registry(tmp_path: Path, command_keys=KEYS) -> Path:
    (tmp_path / "SKILL.md").write_text(f"```bash\n{ONE}\n```\n", encoding="utf-8")
    path = tmp_path / "reg.json"
    path.write_text(json.dumps({"escape_budget": 0, "skills": [{"path": "SKILL.md", "commands": command_keys}]}), encoding="utf-8")
    return path


def test_main_exit_codes_and_output(tmp_path: Path, capsys) -> None:
    ok = _registry(tmp_path)
    assert cpm.main(["--project-root", str(tmp_path), "--registry", str(ok)]) == 0
    assert "clean" in capsys.readouterr().out
    red = _registry(tmp_path, command_keys=[])
    assert cpm.main(["--project-root", str(tmp_path), "--registry", str(red)]) == 1
    assert "new-command" in capsys.readouterr().out
    assert cpm.main(["--project-root", str(tmp_path), "--registry", str(red), "--json"]) == 1
    assert json.loads(capsys.readouterr().out)[0]["kind"] == "new-command"
    assert cpm.main(["--project-root", str(tmp_path), "--registry", str(tmp_path / "absent.json")]) == 2
    assert "unreadable" in capsys.readouterr().err


def test_the_real_registry_passes_the_real_thin_skill() -> None:
    registry = cpm.load_registry(cpm.DEFAULT_REGISTRY)
    assert [e["path"] for e in registry["skills"]] == ["plugins/shipwright-changelog/skills/changelog/SKILL.md"]
    assert cpm.check_registry(registry, REPO) == []


def test_the_real_skill_with_a_seeded_chain_is_refused(tmp_path: Path) -> None:
    """The old behaviour: no check existed, so a chained mechanic in the prose went unnoticed."""
    entry = cpm.load_registry(cpm.DEFAULT_REGISTRY)["skills"][0]
    text = (REPO / entry["path"]).read_text(encoding="utf-8")
    seeded = text.replace('```bash\nuv run "{plugin_root}/scripts/release.py" sync', '```bash\ngit fetch && uv run "{plugin_root}/scripts/release.py" sync')
    assert seeded != text
    found, _ = cpm.check_skill(entry, seeded)
    assert {"chain", "new-command"} <= set(_kinds(found))
