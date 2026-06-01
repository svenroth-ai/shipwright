"""AC-8 — drift protection between `CHURN_ALLOWLIST` and its documented SSoT.

`docs/hooks-and-pipeline.md` carries the "Merge reconciliation of churn
artifacts" table. Per the Registry-driven SSoT meta-test rule, BOTH directions
of drift must fail:

- forward: every relpath in the doc table resolves into `CHURN_ALLOWLIST`;
- reverse: every `CHURN_ALLOWLIST` entry appears in the doc table.

Also pins the two load-bearing invariants in prose (architecture.md excluded;
separate follow-up commit).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib.churn_merge import CHURN_ALLOWLIST  # noqa: E402

DOC = REPO_ROOT / "docs" / "hooks-and-pipeline.md"
_SECTION = "### Merge reconciliation of churn artifacts"
_ROW = re.compile(r"^\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|\s*$")


def _doc_section() -> list[str]:
    lines = DOC.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith(_SECTION))
    out: list[str] = []
    for ln in lines[start + 1:]:
        if ln.startswith("### ") or ln.startswith("## "):
            break
        out.append(ln)
    return out


def _documented_paths() -> dict[str, str]:
    return {m.group(1): m.group(2) for ln in _doc_section() if (m := _ROW.match(ln))}


def test_doc_table_matches_churn_allowlist_both_directions() -> None:
    documented = set(_documented_paths())
    assert documented == set(CHURN_ALLOWLIST), (
        "drift between docs/hooks-and-pipeline.md churn table and CHURN_ALLOWLIST.\n"
        f"  only in doc:       {sorted(documented - set(CHURN_ALLOWLIST))}\n"
        f"  only in allowlist: {sorted(set(CHURN_ALLOWLIST) - documented)}"
    )


def test_each_strategy_is_a_known_keyword() -> None:
    for path, strategy in _documented_paths().items():
        low = strategy.lower()
        assert any(k in low for k in ("union", "regenerate", "ours")), (
            f"{path}: unrecognised resolution strategy {strategy!r}"
        )


def _normalised(text: str) -> str:
    """Collapse backticks, emphasis markers and whitespace so prose assertions
    survive markdown line-wrapping."""
    return " ".join(text.replace("`", "").replace("*", "").split())


def test_architecture_md_is_documented_as_excluded() -> None:
    assert ".shipwright/agent_docs/architecture.md" not in _documented_paths()
    body = _normalised(DOC.read_text(encoding="utf-8"))
    assert "architecture.md is deliberately NOT a churn artifact" in body


def test_followup_commit_invariant_documented() -> None:
    body = _normalised(DOC.read_text(encoding="utf-8"))
    assert "separate, non-merge follow-up commit" in body
    assert "--diff-filter=AM" in body
