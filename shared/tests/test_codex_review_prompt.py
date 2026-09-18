"""`lib/codex_review_prompt.py` — prompt-building and env-scrubbing helpers
for the Codex-CLI internal-review transport. Split from
`test_codex_review_transport.py` to stay under the 300-line source cap
(iterate-2026-09-18-codex-review-tier-config), mirroring the production
module split (`lib.codex_review_transport` -> `lib.codex_review_prompt`).

Covers the Internal Plan Review findings that are load-bearing here: env
allowlisting (finding #2), the stripped/adapted prompt (finding #9).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from lib import codex_review_prompt as prompt_lib  # noqa: E402


def test_strip_frontmatter_removes_leading_yaml_block() -> None:
    text = "---\nname: code-reviewer\nmodel: inherit\n---\nBody text here."
    assert prompt_lib.strip_frontmatter(text) == "Body text here."


def test_strip_frontmatter_is_noop_without_frontmatter() -> None:
    text = "Body text here."
    assert prompt_lib.strip_frontmatter(text) == text


def test_build_prompt_appends_transport_addendum_and_boundary() -> None:
    prompt = prompt_lib.build_prompt("---\nmodel: inherit\n---\nReview the diff.", {})
    assert prompt.startswith("Review the diff.")
    assert "behavior_snapshot.py" in prompt
    assert prompt_lib.INJECTION_BOUNDARY in prompt


def test_build_prompt_includes_the_review_subject() -> None:
    """Regression for code-reviewer REJECT 2026-09-17: the transport had no
    channel for the review subject at all — every reviewer .md says it
    receives spec + diff (or plan + spec) file paths, so without this the
    reviewer must guess what it is reviewing."""
    prompt = prompt_lib.build_prompt(
        "Review the diff.",
        {"Spec file (spec.md)": "spec contents here", "Diff file (diff.patch)": "diff contents here"},
    )
    assert "spec contents here" in prompt
    assert "diff contents here" in prompt
    assert "What you are reviewing" in prompt


def test_scrubbed_env_excludes_api_keys_and_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-anthropic-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-openrouter-secret")
    monkeypatch.setenv("GITHUB_TOKEN", "ghp-secret")
    monkeypatch.setenv("PATH", "/usr/bin")

    env = prompt_lib.scrubbed_env()

    for leaked in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "GITHUB_TOKEN"):
        assert leaked not in env
    assert env.get("PATH") == "/usr/bin"


def test_scrubbed_env_is_a_subset_of_the_allowlist_regardless_of_shape(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC3 requires the invariant itself — no `*_API_KEY`/`*_TOKEN`-shaped
    variable reaches the child — not just that today's four known-bad names
    are absent. An allowlist not-yet-seen name (`FIREBASE_API_KEY`,
    `AZURE_TOKEN`) would leak past a test that only checks the four named
    ones (external code review, MEDIUM, 2026-09-17); asserting the result is
    a subset of the allowlist proves the invariant for every possible name,
    named or not."""
    for shaped in ("FIREBASE_API_KEY", "AZURE_TOKEN", "STRIPE_API_KEY", "SLACK_BOT_TOKEN"):
        monkeypatch.setenv(shaped, "leak-me-not")

    env = prompt_lib.scrubbed_env()

    assert set(env) <= set(prompt_lib._ENV_ALLOWLIST)


def test_scrubbed_env_forwards_windows_subprocess_variables(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression for code-reviewer REJECT 2026-09-17: this feature's primary
    trigger is Codex CLI driving on Windows, and the repo's own recorded
    convention (conventions.md, trg-eed74a42) says a Windows subprocess needs
    SystemDrive/LOCALAPPDATA/APPDATA alongside SystemRoot/USERPROFILE/HOME."""
    monkeypatch.setenv("SystemRoot", "C:\\Windows")
    monkeypatch.setenv("SystemDrive", "C:")
    monkeypatch.setenv("APPDATA", "C:\\Users\\x\\AppData\\Roaming")
    monkeypatch.setenv("LOCALAPPDATA", "C:\\Users\\x\\AppData\\Local")

    env = prompt_lib.scrubbed_env()

    for windows_var in ("SystemRoot", "SystemDrive", "APPDATA", "LOCALAPPDATA"):
        assert windows_var in env
