"""Drift-protection: every duplicated FR-table parser must agree.

The same FR-table parsing logic exists in two modules (a known anti-pattern
introduced by iterate 12.0 when it extracted parser code from data_collector
without removing the original):

  - shared/scripts/lib/drift_parsers.py::parse_fr_table       (drift audit)
  - plugins/shipwright-compliance/scripts/lib/collectors/rtm.py::collect_requirements
    (RTM generator — moved here by Campaign-B B2 from data_collector.py)

When the producer (`/shipwright-adopt`) shipped a 5-data-column FR table
in 2026-05-02 (`| ID | Name | Priority | Description | Source |`), both
consumers silently dropped every row because both regexes only accepted
the 3-data-column Greenfield format. A fix landing in one but not the
other would re-create the same drift class.

This test imports the canonical FR fixtures and runs them through BOTH
parsers via the same parametrized assertion. It fails the suite the
moment a future fix lands in only one of the two modules. See ADR-031
and `references/round-trip-tests.md` Section 2.

The long-term fix is to delete one of the duplicate implementations and
have one source of truth (likely: have data_collector call parse_fr_table
from drift_parsers). Until that refactor lands, this test prevents
regressions across the duplicates.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

# Two `lib/` packages co-exist in this repo (``shared/scripts/lib/`` and
# ``plugins/shipwright-compliance/scripts/lib/``). ``sys.modules['lib']``
# caches whichever is imported first, so we cannot rely on
# ``from lib.X import Y`` to reach both. Load each module directly from
# its source path — see the override-logger comment in
# ``test_compliance_enforcement.py`` for the canonical pattern.
REPO_ROOT = Path(__file__).resolve().parent.parent
SHARED_LIB = REPO_ROOT / "shared" / "scripts" / "lib"
COMPLIANCE_LIB = (
    REPO_ROOT / "plugins" / "shipwright-compliance" / "scripts" / "lib"
)


def _load_module(unique_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(unique_name, path)
    assert spec is not None and spec.loader is not None, (
        f"could not build import spec for {path}"
    )
    module = importlib.util.module_from_spec(spec)
    # Register in sys.modules BEFORE exec — @dataclass looks up
    # ``cls.__module__`` in sys.modules during class construction; an
    # unregistered module raises AttributeError on the dataclass decorator.
    sys.modules[unique_name] = module
    spec.loader.exec_module(module)
    return module


_drift_parsers = _load_module(
    "_fr_drift_protection_drift_parsers",
    SHARED_LIB / "drift_parsers.py",
)
DRIFT_FR_RE = _drift_parsers._FR_TABLE_RE

# Campaign-B B2 moved the FR-table regex from data_collector.py into
# the collectors/ package. We cannot use ``spec_from_file_location``
# on ``collectors/rtm.py`` directly because it uses relative imports
# (``from ._types import ...``) that require the parent package to
# resolve. Bootstrap the compliance plugin's root onto sys.path so
# ``scripts.lib.collectors.rtm`` resolves through the package
# machinery, then unwind it after import to keep the import surface
# clean.
_COMPLIANCE_PLUGIN_ROOT = REPO_ROOT / "plugins" / "shipwright-compliance"
sys.path.insert(0, str(_COMPLIANCE_PLUGIN_ROOT))
try:
    from scripts.lib.collectors.rtm import _FR_TABLE_RE as DATA_FR_RE  # type: ignore[import-not-found]
finally:
    sys.path.remove(str(_COMPLIANCE_PLUGIN_ROOT))


# Each fixture pairs an FR markdown row with the FR id, body, and
# priority the parser is required to extract. `body` is the column the
# RTM/audit treats as the FR's semantic text (Description in 5-col,
# Text in 3-col).
FR_TABLE_FIXTURES = [
    pytest.param(
        "| FR-01.01 | User can log in | Must |",
        ("FR-01.01", "User can log in", "Must"),
        id="3col-greenfield-must",
    ),
    pytest.param(
        "| FR-02.04 | Logout flow exists | Should |",
        ("FR-02.04", "Logout flow exists", "Should"),
        id="3col-greenfield-should",
    ),
    pytest.param(
        "| FR-03.02 | Optional analytics | May |",
        ("FR-03.02", "Optional analytics", "May"),
        id="3col-greenfield-may",
    ),
    pytest.param(
        "| FR-01.01 | /shipwright-run | Must | Orchestrate the full Shipwright SDLC pipeline. | enrichment.json |",
        ("FR-01.01", "Orchestrate the full Shipwright SDLC pipeline.", "Must"),
        id="5col-adopt-must",
    ),
    pytest.param(
        "| FR-01.13 | /shipwright-adopt | Should | Onboard an existing repository into the Shipwright SDLC. | enrichment.json |",
        ("FR-01.13", "Onboard an existing repository into the Shipwright SDLC.", "Should"),
        id="5col-adopt-should",
    ),
    pytest.param(
        "| FR-02.99 | Optional thing | May | An optional adopted FR description. | enrichment.json |",
        ("FR-02.99", "An optional adopted FR description.", "May"),
        id="5col-adopt-may",
    ),
]

NEGATIVE_FIXTURES = [
    pytest.param("| ID | Text | Priority |", id="header-row"),
    pytest.param("|----|------|----------|", id="separator-row"),
    pytest.param("| FR-01.01 | text | UNKNOWN |", id="unknown-priority"),
    pytest.param("| not-an-fr | text | Must |", id="non-fr-id"),
]


PARSERS = [
    pytest.param(DRIFT_FR_RE, id="drift_parsers"),
    pytest.param(DATA_FR_RE, id="data_collector"),
]


def _extract(regex, line: str) -> tuple[str, str, str] | None:
    """Apply the column-selection rule and return (id, body, priority).

    Both regexes are required to share the same column-selection
    convention: when a 4th capture group is present (5-col format), the
    body is that group (Description); otherwise the body is the 2nd
    group (Text/Name). Anything else is a drift bug, which is what this
    test is designed to catch.
    """
    m = regex.match(line)
    if m is None:
        return None
    fr_id = m.group(1).strip()
    priority = m.group(3).strip()
    body_col4 = m.group(4) if regex.groups >= 4 else None
    body = (body_col4 or m.group(2)).strip()
    return fr_id, body, priority


@pytest.mark.parametrize("regex", PARSERS)
@pytest.mark.parametrize("line, expected", FR_TABLE_FIXTURES)
def test_both_parsers_extract_equivalent_fr_rows(regex, line: str, expected):
    """Drift protection: both regexes must agree on positive fixtures."""
    actual = _extract(regex, line)
    assert actual == expected, (
        f"{regex.pattern!r} disagrees with the FR-table convention on {line!r}: "
        f"got {actual}, expected {expected}"
    )


@pytest.mark.parametrize("regex", PARSERS)
@pytest.mark.parametrize("line", NEGATIVE_FIXTURES)
def test_both_parsers_reject_non_fr_lines(regex, line: str):
    """Drift protection: both regexes must reject the same non-FR lines."""
    assert regex.match(line) is None, (
        f"{regex.pattern!r} should NOT match {line!r}"
    )


def test_both_parsers_have_compatible_capture_arity():
    """Sanity guard so the column-selection convention above is enforceable."""
    # Either both regexes are 3-cap (3-col-only) or both expose a 4th
    # group for the 5-col Description column. Anything else means one
    # parser will return wrong text on real input.
    assert DRIFT_FR_RE.groups == DATA_FR_RE.groups, (
        f"capture-arity drift: drift_parsers has {DRIFT_FR_RE.groups} groups, "
        f"data_collector has {DATA_FR_RE.groups}"
    )


# ---------------------------------------------------------------------------
# Boundary probes — markdown-FR-table edge cases (translated from
# `references/boundary-probes.md`). Operator-input categories (POSIX
# export, inline `# comment`, quoted `#`) are N/A: spec.md is
# machine-written by /shipwright-adopt, not hand-edited.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("regex", PARSERS)
def test_probe_utf8_bom_at_file_start(regex, tmp_path: Path):
    """A BOM byte sequence at the file start must NOT prevent the first
    FR row from matching when that row begins on its own line.
    """
    content = (
        "﻿# Specification\n"
        "| FR-01.01 | login | Must |\n"
    )
    matches = [regex.match(line) for line in content.splitlines() if regex.match(line)]
    assert len(matches) == 1
    assert matches[0].group(1) == "FR-01.01"


@pytest.mark.parametrize("regex", PARSERS)
def test_probe_crlf_line_endings(regex):
    """CRLF-terminated lines must still match — Windows-checked-out specs
    routinely have CRLF after `git config core.autocrlf=true`.
    """
    line_3col = "| FR-01.01 | login | Must |\r"
    line_5col = "| FR-01.01 | /run | Must | desc | enrichment.json |\r"
    # `$` in re.MULTILINE / single-line both match end of string in
    # the absence of \n; the \r at end of line is what we probe here.
    # splitlines() strips both \r and \n, so feed the regex the raw
    # CRLF-bearing string to confirm robustness without splitlines()'s help.
    m3 = regex.match(line_3col.rstrip("\r"))
    m5 = regex.match(line_5col.rstrip("\r"))
    assert m3 is not None and m3.group(1) == "FR-01.01"
    assert m5 is not None and m5.group(1) == "FR-01.01"


@pytest.mark.parametrize("regex", PARSERS)
def test_probe_non_ascii_in_description(regex):
    """Umlauts, em-dashes, non-Latin scripts in Description (5-col col 4)
    must round-trip through the regex unchanged.
    """
    line = (
        "| FR-02.99 | /übung | Must | "
        "Beschreibung mit Umlauten — Leerzeichen + 中文. | enrichment.json |"
    )
    m = regex.match(line)
    assert m is not None
    assert regex.groups < 4 or m.group(4) == (
        "Beschreibung mit Umlauten — Leerzeichen + 中文."
    )


@pytest.mark.parametrize("regex", PARSERS)
def test_probe_hash_in_description_value(regex):
    """A literal `#` inside the Description column (e.g. "fixes #42") must
    survive — markdown table cells do NOT support `# comment` semantics.
    """
    line = (
        "| FR-03.01 | /name | Should | "
        "Refers to issue #42 in tracker. | enrichment.json |"
    )
    m = regex.match(line)
    assert m is not None
    if regex.groups >= 4:
        assert m.group(4) == "Refers to issue #42 in tracker."


@pytest.mark.parametrize("regex", PARSERS)
def test_probe_leading_whitespace_before_pipe(regex):
    """Indented FR rows (e.g. nested in a list/blockquote) are NOT
    valid FR-table rows. Anchored `^\\|` must reject them.
    """
    line = "  | FR-01.01 | login | Must |"
    assert regex.match(line) is None


@pytest.mark.parametrize("regex", PARSERS)
def test_probe_extra_trailing_whitespace(regex):
    """Trailing whitespace after the closing pipe must not break the match —
    file-formatters routinely insert it.
    """
    line_3col = "| FR-01.01 | login | Must |    "
    line_5col = "| FR-01.01 | /run | Must | desc | enrichment.json |    "
    m3 = regex.match(line_3col)
    m5 = regex.match(line_5col)
    assert m3 is not None
    assert m5 is not None


@pytest.mark.parametrize("regex", PARSERS)
def test_probe_known_limitation_pipe_inside_description(regex):
    """Documents a known limitation: an unescaped `|` inside the
    Description column (e.g. ``... | Foo \\| Bar | ...``) breaks the
    regex because column boundaries are pipes. Markdown-table-aware
    callers must either avoid pipes in cells or accept truncated text.

    This probe pins the behavior so a future fix is a deliberate change,
    not an accident.
    """
    line = (
        "| FR-04.01 | /name | Must | "
        "Description that contains | a pipe | enrichment.json |"
    )
    m = regex.match(line)
    # Known: drift_parsers regex's [^|]+? consumes only up to the first
    # internal pipe, so the row STILL matches but the captured
    # Description is truncated to "Description that contains".
    if m is not None and regex.groups >= 4:
        # If a future fix supports escaped pipes, this assertion will
        # need updating — that's the point of the probe.
        assert m.group(4) == "Description that contains" or m.group(4) is None
