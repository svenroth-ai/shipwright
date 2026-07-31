"""Drift-protection: the `touches_build` trigger paths must agree between the
canonical detector and the two documents that promise them.

Registry-driven SSoT meta-test rule (SKILL.md Step 6): when a registry in a
`scripts/lib/*` module names identifiers a document also lists, BOTH directions
of drift protection must exist —

* forward — every entry the detector carries must be named in the SKILL.md Risk
  Taxonomy row (the whole tuple, so a NEW ecosystem cannot be added silently),
  and every Python input must additionally be named in docs/guide.md;
* reverse — every Python build input the SKILL.md row names must actually be
  detected, so the row cannot promise a trigger the detector does not raise.

trg-496e63a7: the detector listed JS build inputs only, so in a Python monorepo
`uv.lock` raised nothing while the docs said "dependency / build-config
changes". Under-reporting in either direction is what that looked like.
"""

import sys
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
SKILL_PATH = PLUGIN_ROOT / "skills" / "iterate" / "SKILL.md"
GUIDE_PATH = PLUGIN_ROOT.parent.parent / "docs" / "guide.md"

sys.path.insert(0, str(PLUGIN_ROOT / "scripts" / "lib"))

from classify_complexity import (  # noqa: E402
    TOUCHES_BUILD_BASENAME_GLOBS,
    TOUCHES_BUILD_FILE_PATTERNS,
    detect_risk_flags,
    touches_build_files,
)

# The Python half of the build-input surface. Kept as an explicit literal so a
# silent REMOVAL from the detector fails here too — deriving it from the
# detector would make the test agree with any regression.
PYTHON_BUILD_INPUTS = (
    "uv.lock", "poetry.lock", "Pipfile", "Pipfile.lock",
    "pyproject.toml", "setup.py", "setup.cfg",
)
PYTHON_BUILD_GLOBS = ("requirements*.txt",)


def _risk_taxonomy_row() -> str:
    """The `touches_build` row of the SKILL.md Risk Taxonomy table.

    Ends in `raise`, not `pytest.fail`: the latter is `NoReturn` at runtime but
    static analysis does not model that, so the declared `-> str` kept an
    implicit `return None` path (CodeQL 1299 on the first push of this PR).
    """
    for line in SKILL_PATH.read_text(encoding="utf-8").splitlines():
        if line.startswith("| `touches_build`"):
            return line
    raise AssertionError("SKILL.md Risk Taxonomy has no `touches_build` row")


def _trigger_cell() -> str:
    """Just the Trigger-Paths column of that row.

    Scoping to the one cell that promises triggers is what makes "every
    backticked token here must fire" a true statement. The full row also
    backticks the flag name, the min-complexity (`small`) and `dev_url` in the
    enforcement prose — none of them filenames.
    """
    cells = _risk_taxonomy_row().split("|")
    assert len(cells) >= 5, "touches_build row is not a 4-column table row"
    return cells[2]


# ── Producer side ───────────────────────────────────────────────────────────

@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("name", PYTHON_BUILD_INPUTS)
def test_python_input_is_in_the_detector(name):
    assert name in TOUCHES_BUILD_FILE_PATTERNS


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("glob", PYTHON_BUILD_GLOBS)
def test_python_glob_is_in_the_detector(glob):
    assert glob in TOUCHES_BUILD_BASENAME_GLOBS


# ── Forward: detector → documents ───────────────────────────────────────────

def _row_names(token: str, row: str) -> bool:
    """Does `row` name this detector entry, literally or as a family?

    The row writes `next.config.*` where the tuple carries four literals
    (`next.config.js/.ts/.mjs/.cjs`), so an exact-substring check alone would
    fail on the JS half. A literal hit counts; so does the `<stem>.*` family
    form that covers it.
    """
    if token in row:
        return True
    stem = token.rsplit(".", 1)[0]
    return f"{stem}.*" in row


@pytest.mark.covers("FR-01.11")
def test_skill_md_row_names_every_detector_entry():
    """Forward drift: tuple ⊆ row — for the WHOLE detector, not just Python.

    Anchored on TOUCHES_BUILD_FILE_PATTERNS itself rather than on this file's
    PYTHON_BUILD_INPUTS literal. Anchoring on the literal would only prove
    `literal ⊆ row`, so adding (say) `Cargo.toml` to the detector tomorrow
    would leave the row still claiming Rust is deliberately absent, with no
    test failing — trg-496e63a7 one ecosystem over.
    """
    row = _trigger_cell()
    missing = [
        name for name in TOUCHES_BUILD_FILE_PATTERNS + TOUCHES_BUILD_BASENAME_GLOBS
        if not _row_names(name, row)
    ]
    assert not missing, (
        f"SKILL.md `touches_build` row does not name {missing}. The detector "
        f"fires on them; the documented trigger column must say so."
    )


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("name", PYTHON_BUILD_INPUTS + PYTHON_BUILD_GLOBS)
def test_guide_names_the_python_input(name):
    text = GUIDE_PATH.read_text(encoding="utf-8")
    assert name in text, (
        f"docs/guide.md does not name {name!r} as a touches_build trigger"
    )


# ── Reverse: documents → detector ───────────────────────────────────────────

@pytest.mark.covers("FR-01.11")
def test_every_filename_the_skill_row_names_actually_fires():
    """The row may not promise a trigger the detector does not raise.

    Takes the row's backtick-quoted tokens (the odd segments of a backtick
    split — never the prose between them) and asserts each is detected from a
    diff.

    A token may be a family (`next.config.*`, `requirements*.txt`). One fill
    cannot instantiate every family, so each wildcard token is probed with a
    small set of fills and must fire for at least one — which is exactly what
    the row claims: that the family is covered.

    An earlier version filtered the whole row on "contains a dot", which
    silently skipped the dotless `Pipfile` — so the row could have promised a
    dotless trigger the detector never fires on, and this test would have said
    nothing. Scoping to the trigger cell removes the need to guess which
    backticked tokens are filenames: in that cell, all of them are.
    """
    candidates = [
        t for t in _trigger_cell().split("`")[1::2]
        if t and "/" not in t and " " not in t
    ]
    assert candidates, "no filename-like tokens parsed out of the row"
    assert "Pipfile" in candidates, (
        "the dotless `Pipfile` must be among the probed tokens — its absence "
        "is what the old dot-based filter hid"
    )

    fills = ("js", "ts", "-dev", "_prod", "json", "yaml")
    unfired = []
    for token in candidates:
        if "*" in token:
            probes = [token.replace("*", f) for f in fills]
        else:
            probes = [token]
        if not any(touches_build_files([f"some/path/{p}"]) for p in probes):
            unfired.append(token)
    assert not unfired, (
        f"SKILL.md `touches_build` row names {unfired} but the detector does "
        f"not fire on them"
    )


@pytest.mark.covers("FR-01.11")
@pytest.mark.parametrize("name", PYTHON_BUILD_INPUTS)
def test_python_input_fires_on_both_surfaces(name):
    """Diff-driven AND message-keyword — Step E only reads the message one."""
    assert touches_build_files([f"plugins/shipwright-plan/{name}"]) is True
    flags = [f["flag"] for f in detect_risk_flags(f"bump the pinned dep in {name}")]
    assert "touches_build" in flags, (
        f"{name} is detected from a diff but not from a message; "
        f"detect_risk_flags is the surface that fires at SKILL.md Step E"
    )
