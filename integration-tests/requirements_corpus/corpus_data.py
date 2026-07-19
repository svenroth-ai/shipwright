"""Fixture markdown for the requirements golden corpus, as data.

Each fixture is a mapping of project-root-relative POSIX path -> file content.
Two sentinels express filesystem SHAPES that content cannot:

``DIR``   create this path as an empty directory
``FILE``  create this path as a regular file where a directory is expected

The sentinels exist because part of the frozen surface is what each discovery
walk does at unusual filesystem shapes: ``.shipwright/planning`` as a *file*
(4 targets raise ``NotADirectoryError``, the rest degrade), ``spec.md`` as a
*directory* (drift_parsers swallows the OSError, rtm raises), and a split
directory carrying no ``spec.md`` at all.
"""

from __future__ import annotations

DIR = "<<DIR>>"
FILE = "<<FILE>>"

PLANNING = ".shipwright/planning"
AGENT_SPEC = ".shipwright/agent_docs/spec.md"

# --- table shapes -----------------------------------------------------------
# The five historical shapes recorded in the campaign SPEC section 2.1, plus a
# reordered variant. Column ORDER is load-bearing for the two positional
# parsers, so these are not interchangeable.

_GREENFIELD_TEMPLATE = """# Split 01 -- Auth

## Requirements

| ID | Requirement | Priority | Layers |
|----|-------------|----------|--------|
| FR-01.01 | User can log in | Must | unit, e2e |
| FR-01.02 | User can log out | Should | unit |
"""

_GREENFIELD_EXAMPLE = """# Split 02 -- Dashboard

## Requirements

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-02.01 | Dashboard shows recent activity | Must |
| FR-02.02 | Optional analytics panel | May |
"""

_ADOPT_ON_DISK = """# Split 01 -- Adopted

## Requirements

| ID | Name | Priority | Description | Source |
|----|------|----------|-------------|--------|
| FR-01.01 | /shipwright-run | Must | Orchestrate the full pipeline. | enrichment.json |
| FR-01.02 | /shipwright-plan | Should | Deep planning with external review. | enrichment.json |
"""

# FR-04.02 carries the `(inferred)` layers marker and FR-04.03 carries a
# layers cell with NO canonical layer. Both drive branches in
# _requirement_parse that no other fixture reaches: the inferred_legacy
# provenance path, and the SS11-R4 "named layers column, nothing canonical
# in it" guard that feeds `invalid_layers`. Added after adversarial review
# found them unexercised -- same blind-spot class as the lowercase-priority
# gap that survived mutation test A.
_ADOPT_WRITER = """# Split 04 -- Adopt writer shape

## Requirements

| ID | Name | Priority | Description | Source | Layers |
|----|------|----------|-------------|--------|--------|
| FR-04.01 | /shipwright-test | Must | Run the test suites. | enrichment.json | unit, e2e |
| FR-04.02 | /shipwright-deploy | Should | Deploy to a target. | enrichment.json | unit (inferred) |
| FR-04.03 | /shipwright-preview | May | Local preview. | enrichment.json | int, db |
"""

# Header is ``FR``, not ``ID`` -- the traceability-fixture shape.
# FROZEN-BUG (FV-4): group_i._column_map requires cells[0] == "id" exactly, so
# it maps NOTHING here and drops every row in the file. Flipped by S4.
_FIXTURE_FR_HEADER = """# Split 05 -- Traceability fixture shape

| FR | Description | Priority | Layers |
|----|-------------|----------|--------|
| FR-05.01 | Coverage is reported per layer | Must | unit |
"""

# FROZEN-BUG (FV-1 mechanism): drift_parsers._FR_TABLE_RE pins Must|Should|May
# to data column 3. Reordering the columns yields ZERO rows from both
# positional parsers -- and zero rows makes T1 SKIP instead of FAIL. Flipped
# by S4.
_REORDERED = """# Split 06 -- Reordered columns

| ID | Priority | Requirement | Layers |
|----|----------|-------------|--------|
| FR-06.01 | Must | Reordered table still describes a requirement | unit |
"""

# FROZEN-BUG (FV-3): the header declares three columns but the row carries
# five. drift_parsers/rtm are header-blind, so regex group 4 fires and the
# RTM displays "extra" as the requirement text instead of "ok". This is live
# wrong data in a shipped audit artifact. Flipped by S4.
_HEADER_BLIND = """# Split 07 -- Header-blind mis-extraction

| ID | Requirement | Priority |
|----|-------------|----------|
| FR-07.01 | ok | Should | extra | cells |
"""

# The last two rows probe the PRIORITY VOCABULARY axis, which is load-bearing
# for the positional parsers: drift_parsers/rtm require an exact-case
# Must|Should|May in data column 3 and DROP the whole row otherwise, while
# _requirement_parse silently coerces an unrecognised value to "Must" and
# group_i/_backfill_spec_parse never read priority at all. Without these rows a
# change to the priority alternation is invisible to the corpus -- verified by
# mutation testing during S1, which is how the gap was found.
# FR-01.08 exercises group_i's _UNESCAPED_PIPE_RE (the only parser that
# treats `\|` as escaped rather than as a cell boundary), and the repeated
# FR-01.01 exercises I4 -- the ONLY Group I check that can ever emit `fail`,
# and therefore the only one whose red path was otherwise unreachable.
_MALFORMED = r"""# Split 01 -- Broken

| ID | Requirement | Priority |
| FR-01.01 | ragged |
| FR-01.02 | no close pipe | Must
| FR-01.03 | ok | Should | extra | cells |
FR-01.04 | not a table row at all | Must |
  | FR-01.05 | indented row | Must |
| FR-01.06 | lowercase priority | must |
| FR-01.07 | unrecognised priority | HIGH |
| FR-01.08 | escaped \| pipe in text | Must |
| FR-01.01 | duplicate of the first id | Must |
"""

# Exercises the three FR-id strictness tiers in one table:
#   FR-1.1     loose+medium accept, strict rejects
#   FR-7       loose accepts (unanchored FR-[\\d.]+), medium+strict reject
#   FR-99.99   all three accept
#   FR-001.001 loose+medium accept, strict rejects
_ID_STRICTNESS = """# Split 01 -- Live

## Requirements

| ID | Requirement | Priority | Layers |
|----|-------------|----------|--------|
| FR-01.01 | Canonical two-digit id | Must | unit |
| FR-1.1 | Single-digit id | Must | unit |
| FR-7 | Bare id, no dot | Must | unit |
| FR-99.99 | High canonical id | Should | unit |
| FR-001.001 | Three-digit id | May | unit |

### Removed Requirements

| ID | Requirement | Priority | Layers |
|----|-------------|----------|--------|
| FR-01.09 | Retired capability | Must | unit |

## Next

| FR-01.20 | Row after a later heading | Must | unit |

## FR-Fold-Map

Skipping these lines is load-bearing, not cosmetic: without it the folded ids
below parse as live requirements. Two parsers call `fold_map_line_numbers` to
avoid exactly that.

| FR-01.30 | folded into | FR-01.01 |
| FR-01.31 | folded into | FR-01.01 |
"""

# --- fixtures ---------------------------------------------------------------

FIXTURES: dict[str, dict[str, str]] = {
    # No .shipwright at all. Distinct from "empty" on purpose: this is the
    # cause T1 conflates with a zero-row parse (FV-1). Keeping them apart
    # means S4 updates exactly one assertion.
    "absent": {},

    # The .shipwright/planning dir exists, with no splits inside it.
    "empty": {PLANNING: DIR},

    # planning is a regular FILE. 3 of the 15 walks raise NotADirectoryError
    # here; the rest degrade. Without this fixture that divergence is untested.
    "planning-file": {PLANNING: FILE},

    "greenfield-multi-split": {
        AGENT_SPEC: "# Project spec\n\nTop-level greenfield spec.\n",
        f"{PLANNING}/01-auth/spec.md": _GREENFIELD_TEMPLATE,
        f"{PLANNING}/02-dashboard/spec.md": _GREENFIELD_EXAMPLE,
        f"{PLANNING}/03-reporting/spec.md": _GREENFIELD_TEMPLATE.replace(
            "FR-01.", "FR-03."
        ).replace("Split 01 -- Auth", "Split 03 -- Reporting"),
    },

    "brownfield-single-split": {
        f"{PLANNING}/01-adopted/spec.md": _ADOPT_ON_DISK,
    },

    # THE fixture for FV-1. A populated spec that the POSITIONAL parsers read as
    # zero rows, because the priority column is not third. This is the state
    # that makes T1 SKIP rather than FAIL -- and it is materially different from
    # `absent` (no planning tree at all), which SHOULD skip. Today T1 cannot
    # tell them apart; keeping the two fixtures separate means S4 updates
    # exactly one assertion and the diff shows which cause changed.
    # The inverse of `planning-file`: a FILE position occupied by a directory.
    # drift_parsers guards on .exists() (true for a dir) then swallows OSError,
    # so it degrades; rtm has no try/except at all, so it raises. Two functions
    # the campaign SPEC calls mirrors of each other, diverging exactly where S2
    # unifies them. (Added after adversarial review.)
    "spec-dir": {f"{PLANNING}/01-spec-is-a-dir/spec.md": DIR},

    "zero-row-parse": {
        f"{PLANNING}/01-reordered-only/spec.md": _REORDERED,
    },

    "malformed": {
        f"{PLANNING}/01-broken/spec.md": _MALFORMED,
    },

    "mixed-shape": {
        f"{PLANNING}/01-greenfield-template/spec.md": _GREENFIELD_TEMPLATE,
        f"{PLANNING}/02-greenfield-example/spec.md": _GREENFIELD_EXAMPLE,
        f"{PLANNING}/03-adopt-disk/spec.md": _ADOPT_ON_DISK.replace(
            "FR-01.", "FR-03."
        ),
        f"{PLANNING}/04-adopt-writer/spec.md": _ADOPT_WRITER,
        f"{PLANNING}/05-fixture-fr/spec.md": _FIXTURE_FR_HEADER,
        f"{PLANNING}/06-reordered/spec.md": _REORDERED,
        f"{PLANNING}/07-header-blind/spec.md": _HEADER_BLIND,
    },

    # Every axis on which the 15 walks disagree, in one tree.
    "edge": {
        AGENT_SPEC: "# Project spec\n\nTop-level spec present.\n",
        "spec.md": "# Repo-root spec\n\nOnly backfill_test_links looks here.\n",
        f"{PLANNING}/01-live/spec.md": _ID_STRICTNESS,
        # Hidden split: included by ALL 15 walks. pathlib's glob/rglob DO match
        # a leading dot (unlike the shell and unlike the stdlib glob module), so
        # the glob-based walks see it exactly like the iterdir-based ones. An
        # earlier comment here claimed the opposite; the matrix disagrees --
        # ".hidden-split/spec.md" is in the recorded value of every walk that
        # returns paths. Corrected in S2 against the baseline, not from memory.
        f"{PLANNING}/.hidden-split/spec.md": _GREENFIELD_TEMPLATE,
        # iterate/: 3 walks exclude it, 4 include it, 1 yields EVERY *.md.
        f"{PLANNING}/iterate/spec.md": _GREENFIELD_TEMPLATE,
        f"{PLANNING}/iterate/iterate-2026-01-01-example.md": "# An iterate spec\n",
        # A loose spec.md directly under the planning dir itself --
        # seen by exactly 1 of the 15 walks.
        f"{PLANNING}/spec.md": "# Loose spec\n\nDirectly under the planning dir.\n",
        # A split directory carrying no spec.md.
        f"{PLANNING}/02-no-spec": DIR,
        # Nested one level deeper -- only the rglob walks descend this far.
        f"{PLANNING}/03-nested/deeper/spec.md": _GREENFIELD_EXAMPLE,
    },
}

FIXTURE_NAMES: tuple[str, ...] = tuple(FIXTURES)

# Declared because every name here is consumed by OTHER modules (the realm
# collector, the matrix tests) and none is referenced within this file --
# without __all__ that reads as dead module-level state.
__all__ = ["DIR", "FILE", "PLANNING", "AGENT_SPEC", "FIXTURES", "FIXTURE_NAMES"]
