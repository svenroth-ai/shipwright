"""Drift protection for the shared requirement-elicitation module — reverse
direction (every requirement-elicitation surface still cites the module),
plus the FR-01.16 AC09 dynamic-discovery mechanism itself.

Split from `test_requirement_elicitation_refs.py` (the forward direction) to
stay under the 300-LOC bloat-baseline cap; see that file's docstring for the
shared context.

This mirrors `test_fr_authoring_refs.py`, the sibling guard for the
FR-authoring rulebook — with one deliberate divergence (FR-01.16 AC09, trg
P4.3): the set of reference docs that must cite the module is not a
hand-maintained tuple. It is *discovered* by
`_elicitation_discovery.discover_elicitation_reference_docs()` (split into its
own module — test-only tooling, not production code), which globs every
plugin's `references/*.md` doc and keeps the ones carrying the
`"recommended answer"` marker — the Pocock-style "one question at a time, each
with a recommended answer" grilling-rule phrase every genuine
requirement-elicitation surface's doc carries inside its own prose. A new
elicitation surface is picked up automatically, without editing this file.
See `_elicitation_discovery.py`'s docstring for why the marker is deliberately
not the `"requirement-elicitation.md"` citation string itself — that would
collapse discovery and this file's reverse citation-check into one, defeating
the reverse check's purpose.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _elicitation_discovery import (  # noqa: E402
    ELICITATION_SURFACE_MARKER,
    discover_elicitation_reference_docs,
    doc_cites_the_module,
)


REPO_ROOT = Path(__file__).resolve().parents[2]

#: Snapshot of the 4 currently-known citing docs — kept as an explicit literal
#: (mirroring `test_touches_build_python_inputs_sync.py`'s `PYTHON_BUILD_INPUTS`
#: precedent) so a silent regression in discovery itself (e.g. the glob root or
#: marker breaking) is caught here too. This is a regression pin on today's
#: known state, NOT the mechanism that decides which docs get reverse-checked
#: below — that mechanism is `discover_elicitation_reference_docs()` itself,
#: which extends to a genuinely new surface without this tuple changing.
#:
#: `test_fr_authoring_refs.py`'s sibling `CITING_DOCS` is a separate,
#: still-hardcoded enumeration for a different SSoT guard (the FR-authoring
#: rulebook) — intentionally left as-is (out of scope, P4.3), not an
#: oversight; a future sub-iterate could apply the same discovery treatment
#: there (external plan-review, round 1, GLM low finding).
KNOWN_CITING_DOCS = (
    "plugins/shipwright-project/skills/project/references/interview-protocol.md",
    "plugins/shipwright-adopt/skills/adopt/references/step-c-interview.md",
    "plugins/shipwright-iterate/skills/iterate/references/path-a-feature.md",
    "plugins/shipwright-iterate/skills/iterate/references/path-b-change.md",
)

#: Computed once at collection time — drives the reverse parametrized test
#: below. Adding a 5th real elicitation-surface doc under any plugin's
#: `references/` dir makes it appear here (and be reverse-checked) without
#: touching this file.
DISCOVERED_ELICITATION_DOCS = discover_elicitation_reference_docs(REPO_ROOT)


# --------------------------------------------------------------------------- #
# Reverse — every requirement-elicitation surface still cites the module.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "doc", DISCOVERED_ELICITATION_DOCS,
    ids=lambda p: p.relative_to(REPO_ROOT).as_posix(),
)
@pytest.mark.covers("FR-01.16/AC09")
def test_elicitation_surface_cites_the_module(doc):
    assert doc_cites_the_module(doc), (
        f"{doc.relative_to(REPO_ROOT).as_posix()} elicits requirements "
        f"(carries the {ELICITATION_SURFACE_MARKER!r} marker) but no longer "
        f"cites shared/requirement-elicitation.md — the method would "
        f"silently stop being applied"
    )


@pytest.mark.covers("FR-01.16/AC09")
def test_discovery_finds_at_least_the_known_citing_docs():
    """AC1 — the discovery function, run against the real repo, still finds
    (at least) the 4 currently-known docs.

    A SUBSET check (external plan-review, round 1, OpenAI medium finding #2)
    rather than exact-set equality: exact equality would fail the moment a
    legitimate 5th elicitation surface is added with the marker, reintroducing
    exactly the "remember to extend a list" maintenance burden AC09 exists to
    remove. A subset check still catches BOTH failure modes a stricter reader
    might worry it misses — a partial regression (discovery silently finding
    only 2 of 4) and a total vacuous pass (discovery finding nothing) both
    make the subset relation false, so neither slips through silently
    (external plan-review, round 1, GLM low "vacuous-pass hazard" finding).
    """
    assert DISCOVERED_ELICITATION_DOCS, (
        "discover_elicitation_reference_docs(REPO_ROOT) found nothing — the "
        "glob root or marker is broken, which would make the reverse "
        "citation-check above parametrize over an empty, vacuously-passing "
        "list"
    )
    expected = {REPO_ROOT / rel for rel in KNOWN_CITING_DOCS}
    discovered = set(DISCOVERED_ELICITATION_DOCS)
    missing = expected - discovered
    assert not missing, (
        f"discover_elicitation_reference_docs(REPO_ROOT) is missing "
        f"{sorted(p.relative_to(REPO_ROOT).as_posix() for p in missing)} — "
        f"expected at least {sorted(KNOWN_CITING_DOCS)}"
    )


#: A small, curated set of real `references/*.md` docs that discuss adjacent
#: concepts (the coverage checklist's `Basis: assumed` stop-condition,
#: elicitation prose in general) WITHOUT carrying the elicitation-surface
#: marker itself — near-misses a broadened marker would plausibly start
#: sweeping in. Verified today (P4.3 precedent research): `spec-generation.md`
#: contains `"Basis: assumed"` but not `"recommended answer"`.
KNOWN_NON_ELICITATION_NEAR_MISSES = (
    "plugins/shipwright-project/skills/project/references/spec-generation.md",
)


def test_discovery_marker_does_not_sweep_in_known_near_misses():
    """Marker-precision guard, distinct from the AC1 subset check above:
    catches a marker gone generic (e.g. broadened to a common word/phrase)
    WITHOUT reintroducing any burden on a legitimate new elicitation surface.

    Two earlier versions of this test failed exactly that bar. Round 1
    (external code review) added an exact-set snapshot assertion
    (`discovered == KNOWN_CITING_DOCS`); PR-review gate (round 3,
    openai/gpt-5.6-luna) correctly flagged that a legitimate 5th surface
    would fail CI until a human manually extended the tuple. Round 2
    replaced it with a count ceiling (`len(discovered) <= 20`); the same
    gate correctly flagged that a 21st legitimate surface would fail for
    the identical reason — any ceiling on the COUNT of matches is, in the
    limit, exactly the same "list someone must remember to extend" burden
    FR-01.16 AC09 exists to eliminate. This version tests marker precision
    against a fixed, curated set of docs already known NOT to carry the
    marker (a negative control), which can never fail due to a new,
    legitimately-marked surface being added — only if the marker itself
    degrades into something that starts matching these known near-misses.
    """
    near_misses = {REPO_ROOT / rel for rel in KNOWN_NON_ELICITATION_NEAR_MISSES}
    swept_in = near_misses & set(DISCOVERED_ELICITATION_DOCS)
    assert not swept_in, (
        f"ELICITATION_SURFACE_MARKER now matches known non-elicitation "
        f"doc(s) {sorted(p.relative_to(REPO_ROOT).as_posix() for p in swept_in)} "
        f"— it has become too broad; tighten it rather than adding these to "
        f"KNOWN_CITING_DOCS"
    )


@pytest.mark.covers("FR-01.16/AC09")
def test_discovery_is_dynamic_a_new_reference_doc_is_picked_up(tmp_path):
    """AC2 — a reference doc added under any plugin's `references/` dir that
    carries the elicitation-surface marker is picked up WITHOUT editing this
    test file. Proven via a temp fixture tree (not a real 5th plugin), so the
    proof is the mechanism itself, not another hardcoded path added to
    `KNOWN_CITING_DOCS` in a different shape.
    """
    fixture_doc = (
        tmp_path / "plugins" / "shipwright-fakeplugin" / "skills" / "fakeskill"
        / "references" / "new-elicitation-surface.md"
    )
    fixture_doc.parent.mkdir(parents=True)
    fixture_doc.write_text(
        "Ask one question at a time, each with a recommended answer.\n",
        encoding="utf-8",
    )
    discovered = discover_elicitation_reference_docs(tmp_path)
    assert discovered == (fixture_doc,), (
        "a new reference doc carrying the elicitation-surface marker must be "
        "discovered dynamically, from an arbitrary root, without editing "
        "this test file"
    )


def test_discovery_signal_is_not_the_reverse_citation_string(tmp_path):
    """AC3 — the discovery signal must not simply be the string
    `"requirement-elicitation.md"`; that would collapse discovery and the
    reverse citation-check above into one, defeating the reverse check's
    purpose. A fixture doc that cites the module but does NOT carry the
    elicitation-surface marker must not be discovered.
    """
    fixture_doc = (
        tmp_path / "plugins" / "shipwright-fakeplugin" / "skills" / "fakeskill"
        / "references" / "cites-but-is-not-a-surface.md"
    )
    fixture_doc.parent.mkdir(parents=True)
    fixture_doc.write_text(
        "See shared/requirement-elicitation.md for background reading.\n",
        encoding="utf-8",
    )
    discovered = discover_elicitation_reference_docs(tmp_path)
    assert fixture_doc not in discovered, (
        "discovery must key on the elicitation-surface marker, not on the "
        "'requirement-elicitation.md' citation string — otherwise a doc "
        "could vacuously 'discover' itself by citing the module without "
        "actually being a grilling surface"
    )


def test_a_discovered_but_uncited_fixture_doc_fails_the_reverse_check(tmp_path):
    """The AC2 dynamic-discovery proof above shows the helper RETURNS a
    fixture path; this proves a dynamically discovered doc that fails to
    cite the module is actually caught by `doc_cites_the_module()` — the
    exact function `test_elicitation_surface_cites_the_module` runs against
    every real discovered doc — not merely that discovery is wired in
    without being enforced (external plan-review, round 1, OpenAI medium
    finding #3).
    """
    fixture_doc = (
        tmp_path / "plugins" / "shipwright-fakeplugin" / "skills" / "fakeskill"
        / "references" / "surface-without-citation.md"
    )
    fixture_doc.parent.mkdir(parents=True)
    fixture_doc.write_text(
        "Ask one question at a time, each with a recommended answer.\n",
        encoding="utf-8",
    )
    discovered = discover_elicitation_reference_docs(tmp_path)
    assert discovered == (fixture_doc,)
    assert not doc_cites_the_module(fixture_doc), (
        "a discovered elicitation surface that never cites "
        "shared/requirement-elicitation.md must be reported as failing"
    )


def test_project_interview_protocol_wires_the_context_producer():
    """§4/§7 require a sharpened term to land in `CONTEXT.md` the moment it is
    resolved, not batched after the interview. `write_context_term.py` is the
    producer (P4.1); this pins that `/shipwright-project`'s interview protocol
    actually calls it — a prompt-only guarantee, so this is the only test that
    can exist for it (elicitation §6's `enforced`/`prompt-only` table)."""
    doc = REPO_ROOT / "plugins/shipwright-project/skills/project/references/interview-protocol.md"
    body = doc.read_text(encoding="utf-8")
    assert "write_context_term.py" in body, (
        "interview-protocol.md must call the write_context_term.py producer "
        "at the point a term is sharpened (requirement-elicitation.md §4/§7)"
    )
    # It must be described as happening DURING the turn, not batched — the
    # distinction the sub-iterate spec calls out explicitly.
    assert "before the next" in body.lower() or "same turn" in body.lower(), (
        "the wiring must instruct writing CONTEXT.md during the sharpening "
        "turn, not deferred to end-of-interview"
    )
    # Pin the invocation's own flags, not just the script name (external code
    # review, P4.1) — a flag rename in the wired snippet must fail loudly
    # rather than leave this test passing against a broken command. The
    # wired invocation is --payload-file, not --term/--definition/--avoid
    # (P4.1 final review, GitHub required-check finding): free interview
    # text must never be substituted into a shell-quoted --term/--definition
    # argument — a single quote in the text breaks the quoting outright and
    # the rest is interpreted as shell syntax — so that legacy flag path is
    # deliberately NOT the documented invocation any more.
    for flag in ("--project-root", "--payload-file"):
        assert flag in body, (
            f"the write_context_term.py invocation in interview-protocol.md "
            f"is missing {flag!r} — the wired command must stay runnable"
        )
    for key in ('"term"', '"definition"'):
        assert key in body, (
            f"the write_context_term.py --payload-file JSON shape in "
            f"interview-protocol.md is missing {key!r}"
        )
    assert "Write tool" in body, (
        "interview-protocol.md must instruct writing the --payload-file "
        "JSON via the Write tool (never a shell command) — that is the "
        "whole point of --payload-file: no shell ever parses free "
        "interview text, closing the quote-breakout vulnerability"
    )
    # A --term-shaped invocation belongs only in prose as a warning example
    # (the "never hand-assemble a --term '<value>' shell invocation" line
    # above) — never inside a fenced bash block an agent could copy and
    # actually run (P4.1 final-review deferred finding: the doc guard above
    # checked --payload-file was present but never checked a --term-shaped
    # snippet was absent from the runnable blocks).
    fenced_bash_blocks = re.findall(r"```bash\r?\n(.*?)```", body, re.DOTALL)
    assert fenced_bash_blocks, "expected at least one fenced bash block wiring the producer"
    for block in fenced_bash_blocks:
        assert "--term" not in block, (
            f"a --term-shaped bash snippet must never appear in a fenced "
            f"code block — --payload-file is the only sanctioned runnable "
            f"invocation; found in: {block!r}"
        )
