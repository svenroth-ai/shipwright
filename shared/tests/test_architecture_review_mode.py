"""Tests for the architecture review mode.

The architecture pass asks one question the plan review never asks — *should this
be built at all* — and earns a different answer from the same two models only
because its INPUT differs: a short brief instead of the plan, with the author's
rejection reasons deliberately withheld.

So these tests guard the input path above all else — that the mode demands a
brief and cannot be run against a plan by accident, and that `{BRIEF}` is a known
placeholder rather than a token that renders literally. A mode that silently
reviewed the plan would pass every other assertion and be worthless.

What the shipped prompts and template must SAY lives next door in
`test_architecture_review_prompts.py`; this file owns what the CLI DOES.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_SHARED = Path(__file__).resolve().parents[1]
_TOOLS_DIR = _SHARED / "scripts" / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

_CLI = _TOOLS_DIR / "external_review.py"
_STRIP_KEYS = {
    "OPENROUTER_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY",
}


def _keyless_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _STRIP_KEYS}


@pytest.fixture
def brief_and_spec(tmp_path):
    spec = tmp_path / "spec.md"
    brief = tmp_path / "architecture_brief.md"
    spec.write_text("# Spec\nStop the thing from breaking.", encoding="utf-8")
    brief.write_text(
        "# Architecture Brief\n\n## The problem\nX fails weekly.\n\n"
        "## Options on the table\n- A: do nothing\n- B: a queue\n",
        encoding="utf-8",
    )
    return spec, brief


@pytest.fixture
def fake_plugin(tmp_path):
    """--plugin-root is required by the CLI shape but unused in this mode."""
    root = tmp_path / "fake-plugin"
    root.mkdir()
    return root



# ---- AC1: the brief is mandatory -------------------------------------------

def test_architecture_mode_requires_brief_file(brief_and_spec, fake_plugin, tmp_path):
    """Symmetric with `code` requiring --diff-file: a missing brief is a usage
    error (exit 2), never a silent fall-through to --plan-file."""
    spec, _ = brief_and_spec
    result = subprocess.run(
        [sys.executable, str(_CLI), "--mode", "architecture",
         "--spec-file", str(spec), "--plugin-root", str(fake_plugin)],
        capture_output=True, text=True, env=_keyless_env(), cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "--brief-file" in result.stderr


def test_architecture_mode_rejects_plan_file_as_a_foreign_flag(
    brief_and_spec, fake_plugin, tmp_path
):
    """Passing --plan-file instead of --brief-file must be diagnosed AS THAT.

    This is the regression that would quietly destroy the whole pass: the CLI
    would review the plan under the architecture prompt, the envelope would look
    identical, and the anchoring the mode exists to avoid would be back.

    The assertion is on the foreign-flag message, not merely on exit 2. Written
    the loose way (asserting only `"--brief-file" in stderr`) this test passed
    against an implementation with the foreign-flag loop deleted, because the
    missing-flag branch says "--brief-file is required" too — it was a duplicate
    of the test above, pinning nothing (Stage-2 code review, medium).
    """
    spec, brief = brief_and_spec
    result = subprocess.run(
        [sys.executable, str(_CLI), "--mode", "architecture",
         "--spec-file", str(spec), "--plan-file", str(brief),
         "--plugin-root", str(fake_plugin)],
        capture_output=True, text=True, env=_keyless_env(), cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "--plan-file belongs to --mode plan" in result.stderr, (
        "a mismatched flag must name itself — 'is required' tells the operator "
        "nothing about the plan they just handed an architecture review"
    )


def test_empty_brief_is_an_error_not_a_skip(fake_plugin, tmp_path):
    """The opposite of code mode's empty-diff skip, deliberately.

    An empty diff has nothing to review; an empty brief means the pass's only
    input was never written, and the providers would still answer — a plausible
    `approve` over nothing, recorded as a completed review.
    """
    spec = tmp_path / "spec.md"
    brief = tmp_path / "architecture_brief.md"
    spec.write_text("# Spec", encoding="utf-8")
    brief.write_text("   \n\n", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(_CLI), "--mode", "architecture",
         "--spec-file", str(spec), "--brief-file", str(brief),
         "--plugin-root", str(fake_plugin)],
        capture_output=True, text=True, env=_keyless_env(), cwd=tmp_path,
    )
    assert result.returncode == 1
    assert "Brief is empty" in json.loads(result.stdout)["error"]

    # A BOM is not whitespace to Python, so `.strip()` alone let PowerShell's
    # `Set-Content -Encoding UTF8 ""` — which writes exactly BOM+CRLF — through
    # as a non-empty brief, and both models were asked to judge one invisible
    # character (Stage-3 doubt review, low).
    brief.write_bytes(b"\xef\xbb\xbf\r\n")
    result = subprocess.run(
        [sys.executable, str(_CLI), "--mode", "architecture",
         "--spec-file", str(spec), "--brief-file", str(brief),
         "--plugin-root", str(fake_plugin)],
        capture_output=True, text=True, env=_keyless_env(), cwd=tmp_path,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["success"] is False
    assert "Brief is empty" in payload["error"]


def test_injected_content_is_never_rescanned_for_placeholders():
    """A placeholder inside the INJECTED text must survive as a literal.

    Chained `str.replace` rescans what the previous call produced, so a diff
    containing `{BRIEF}` was rendered once per occurrence — measured
    `('Diff:\\n{DIFF}', 'a{BRIEF}b')` → `'Diff:\\naa{BRIEF}bb'`, i.e. the whole
    diff duplicated AND a literal placeholder leaking into the prompt. Every
    diff of this very change carries `{BRIEF}` literals, so the repo's own next
    `--mode code` review was the trigger (Stage-2 code review, high).
    """
    import external_review

    # `{SPEC}` inside the PRIMARY is the case that actually regressed for the
    # three pre-existing modes, and the one the pre-change chain got wrong:
    # `.replace("{DIFF}", p)` injected the diff, then `.replace("{SPEC}", s)`
    # rescanned it and spliced the whole spec into the middle of the diff. A
    # fixture using only `{BRIEF}` pins nothing there — the old chain never
    # substituted `{BRIEF}` at all, so it produced the identical string and the
    # test passed against the bug (Stage-3 doubt review, medium).
    rendered = external_review._render_user_prompt(
        "Diff:\n{DIFF}\nSpec: {SPEC}", "a{SPEC}b{BRIEF}c", "S{PLAN}")
    assert rendered == "Diff:\na{SPEC}b{BRIEF}c\nSpec: S{PLAN}", (
        "one pass over the TEMPLATE only — injected primary/spec content must "
        "never be re-substituted"
    )


def test_foreign_flag_is_rejected_in_a_pre_existing_mode_too(brief_and_spec, fake_plugin, tmp_path):
    """The one-flag-per-mode rule TIGHTENED the three older modes as a side effect.

    `--mode code --plan-file X` used to be silently ignored; the `_MODE_INPUT`
    table now makes it exit 2. Every shipped invocation passes exactly one input
    flag, so nothing breaks — but the generalization is behavior this diff
    introduced, and asserting it only for architecture mode would leave the
    wider half unpinned (Stage-1 spec review, low).
    """
    spec, brief = brief_and_spec
    result = subprocess.run(
        [sys.executable, str(_CLI), "--mode", "code",
         "--spec-file", str(spec), "--diff-file", str(brief),
         "--brief-file", str(brief), "--plugin-root", str(fake_plugin)],
        capture_output=True, text=True, env=_keyless_env(), cwd=tmp_path,
    )
    assert result.returncode == 2
    assert "--brief-file belongs to --mode architecture" in result.stderr


def test_architecture_mode_missing_brief_path_reports_it(fake_plugin, tmp_path):
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec", encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(_CLI), "--mode", "architecture",
         "--spec-file", str(spec), "--brief-file", str(tmp_path / "nope.md"),
         "--plugin-root", str(fake_plugin)],
        capture_output=True, text=True, env=_keyless_env(), cwd=tmp_path,
    )
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["success"] is False
    assert "Brief not found" in payload["error"]


# ---- AC3: {BRIEF} is a known placeholder -----------------------------------

def test_brief_placeholder_is_substituted():
    import external_review

    rendered = external_review._render_user_prompt(
        "spec={SPEC} brief={BRIEF}", "THE-BRIEF", "THE-SPEC")
    assert rendered == "spec=THE-SPEC brief=THE-BRIEF"


def test_brief_placeholder_emits_no_unknown_warning(capsys):
    """{BRIEF} must be in the known set — otherwise every architecture run
    prints a spurious developer warning on stderr."""
    import external_review

    external_review._render_user_prompt("{SPEC}{BRIEF}", "b", "s")
    assert "unknown placeholder" not in capsys.readouterr().err


def test_unknown_placeholder_still_warns(capsys):
    import external_review

    external_review._render_user_prompt("{MYSTERY}", "b", "s")
    assert "unknown placeholder {MYSTERY}" in capsys.readouterr().err


# ---- AC4: same envelope, same two reviewers --------------------------------

def test_architecture_mode_emits_the_standard_envelope(
    brief_and_spec, fake_plugin, tmp_path
):
    """Same shape as every other mode, incl. verdicts/contradiction.

    A consumer must never have to special-case this mode — `record_review_pass
    --from external-review-json` reads exactly one envelope shape.
    """
    spec, brief = brief_and_spec
    result = subprocess.run(
        [sys.executable, str(_CLI), "--mode", "architecture",
         "--spec-file", str(spec), "--brief-file", str(brief),
         "--plugin-root", str(fake_plugin)],
        capture_output=True, text=True, env=_keyless_env(), cwd=tmp_path,
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["provider"] == "none"
    assert set(payload["reviews"]) == {"glm", "openai"}
    for key in ("verdicts", "statuses", "contradiction", "review_schema"):
        assert key in payload, f"envelope is missing {key}"
