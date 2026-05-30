"""Drift guard: SSoT template <-> framework ``.gitignore`` artifact block.

The canonical ``.shipwright/`` artifact-ignore rules live in
``shared/templates/shipwright-gitignore.template`` (the SSoT propagated to
every consuming project by adopt/project) AND inside a marker-delimited
block in the framework's own ``.gitignore``. These two MUST stay congruent:
a future ADR that adds a gitignored ``.shipwright/`` dir has to edit the
template, and this test fails until the framework block is updated to match
(or vice-versa) — so the change auto-propagates instead of silently
diverging.

Comments and blank lines inside either block are ignored; only the actual
gitignore rule-lines (in order) are compared.
"""

from __future__ import annotations

from pathlib import Path

from lib.gitignore_canon import (
    BEGIN_MARKER,
    END_MARKER,
    extract_marked_rules,
    read_canonical_rules,
)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FRAMEWORK_GITIGNORE = _REPO_ROOT / ".gitignore"
_TEMPLATE = _REPO_ROOT / "shared" / "templates" / "shipwright-gitignore.template"


def test_template_marked_rules_nonempty() -> None:
    assert read_canonical_rules(_TEMPLATE), "template SSoT has no canonical rules"


def test_framework_gitignore_has_managed_markers() -> None:
    text = _FRAMEWORK_GITIGNORE.read_text(encoding="utf-8")
    assert BEGIN_MARKER in text, "framework .gitignore missing BEGIN marker"
    assert END_MARKER in text, "framework .gitignore missing END marker"
    assert text.index(BEGIN_MARKER) < text.index(END_MARKER), "markers out of order"


def test_template_and_framework_block_are_congruent() -> None:
    template_rules = read_canonical_rules(_TEMPLATE)
    framework_rules = extract_marked_rules(
        _FRAMEWORK_GITIGNORE.read_text(encoding="utf-8")
    )
    assert framework_rules == template_rules, (
        "Drift between the canonical gitignore SSoT template and the "
        "framework's own .gitignore artifact block.\n"
        f"  template ({_TEMPLATE}):\n    {template_rules}\n"
        f"  framework ({_FRAMEWORK_GITIGNORE}):\n    {framework_rules}\n"
        "A future ADR adding a gitignored .shipwright/ dir must update BOTH "
        "(edit the template; mirror the rule into the framework block)."
    )


def test_runtime_reexclude_present_in_template() -> None:
    """Links this drift guard to ``test_runtime_dir_gitignored.py``.

    That test guards the framework's actual ``runtime/`` behavior; this one
    guards that the same re-exclude lives in the SSoT template so it
    propagates to consuming projects (the gap that left webui dirty).
    """
    assert "/.shipwright/agent_docs/runtime/" in read_canonical_rules(_TEMPLATE)
