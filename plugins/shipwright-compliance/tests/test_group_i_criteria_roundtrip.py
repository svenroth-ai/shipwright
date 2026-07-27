"""I6 against the REAL producers, and the per-file matching rule.

These are the load-bearing tests. The shape cases in
``test_group_i_criteria.py`` prove the parser reads what it was told to read;
these prove it reads what Shipwright actually *writes* — the literal template
shipped in ``spec-generation.md``, the literal output of adopt's
``artifact_writer``, and this repo's own catalogue.

That distinction matters because the failure mode of I6 is not a crash, it is a
false warning in every downstream project: a producer quietly changing its
acceptance-criteria shape would make the check report "no criteria" for
requirements that are fully elaborated. Testing against fixtures copied by hand
would not catch that; testing against the producers does.
"""

from __future__ import annotations

import sys
from contextlib import contextmanager
from pathlib import Path

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT))

from scripts.audit.group_i_criteria import (  # noqa: E402
    frs_without_criteria,
    has_criteria,
)

REPO_ROOT = PLUGIN_ROOT.parent.parent


@contextmanager
def _adopt_lib_namespace():
    """Bind the ``lib`` package to *adopt's* ``scripts/lib`` for one import.

    Every plugin ships its own top-level ``lib`` package, and
    ``artifact_writer`` imports its siblings eagerly (``from lib.spec_table
    import …``). By the time this test runs inside the full compliance suite,
    ``sys.modules['lib']`` is already bound to compliance's own package, so a
    plain ``sys.path`` insert resolves to the wrong one — the ADR-045 collision.
    This test passes in isolation and fails in the suite without the swap, which
    is precisely the failure mode worth pinning rather than skipping past.

    Evicting and restoring keeps the effect scoped: modules already imported
    elsewhere keep their symbol references, and the original binding is put back
    so test-ordering stays irrelevant.
    """
    adopt_scripts = str(REPO_ROOT / "plugins" / "shipwright-adopt" / "scripts")

    def _evict() -> dict:
        doomed = {k: v for k, v in sys.modules.items()
                  if k == "lib" or k.startswith("lib.")}
        for key in doomed:
            del sys.modules[key]
        return doomed

    saved = _evict()
    sys.path.insert(0, adopt_scripts)
    try:
        yield
    finally:
        sys.path.remove(adopt_scripts)
        _evict()
        sys.modules.update(saved)


class _Row:
    """Minimal stand-in for ``group_i.FrRow`` (only id + spec_path are read)."""

    def __init__(self, fr_id: str, spec_path: str) -> None:
        self.id = fr_id
        self.spec_path = spec_path


# ---------------------------------------------------------------------------
# Per-file matching — a shared id must not mask a gap
# ---------------------------------------------------------------------------

def test_same_id_in_two_specs_is_judged_per_file(tmp_path: Path):
    """Criteria in one spec must not satisfy the same id in another.

    Named by the external plan review: a parser pooling ids across all files
    would let an elaborated FR-01.01 in split A silently cover a bare FR-01.01
    in split B.
    """
    good = tmp_path / ".shipwright" / "planning" / "01-a"
    bad = tmp_path / ".shipwright" / "planning" / "02-b"
    good.mkdir(parents=True)
    bad.mkdir(parents=True)
    (good / "spec.md").write_text(
        "### FR-01.01 — elaborated\n\n- (E) Given ... then ...\n", encoding="utf-8",
    )
    (bad / "spec.md").write_text("### FR-01.01 — bare\n\n_TBD._\n", encoding="utf-8")

    rows = [
        _Row("FR-01.01", ".shipwright/planning/01-a/spec.md"),
        _Row("FR-01.01", ".shipwright/planning/02-b/spec.md"),
    ]
    assert frs_without_criteria(tmp_path, rows) == ["FR-01.01"]


def test_fully_elaborated_specs_report_nothing(tmp_path: Path):
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text(
        "### FR-01.01 — elaborated\n\n- (E) Given ... then ...\n", encoding="utf-8",
    )
    rows = [_Row("FR-01.01", ".shipwright/planning/01-a/spec.md")]
    assert frs_without_criteria(tmp_path, rows) == []


def test_unreadable_spec_reports_missing_not_crash(tmp_path: Path):
    rows = [_Row("FR-01.01", ".shipwright/planning/nope/spec.md")]
    assert frs_without_criteria(tmp_path, rows) == ["FR-01.01"]


def test_result_is_sorted_and_deduplicated(tmp_path: Path):
    split = tmp_path / ".shipwright" / "planning" / "01-a"
    split.mkdir(parents=True)
    (split / "spec.md").write_text("nothing here\n", encoding="utf-8")
    rows = [
        _Row("FR-01.03", ".shipwright/planning/01-a/spec.md"),
        _Row("FR-01.01", ".shipwright/planning/01-a/spec.md"),
    ]
    assert frs_without_criteria(tmp_path, rows) == ["FR-01.01", "FR-01.03"]


# ---------------------------------------------------------------------------
# Round-trip against the REAL producers
# ---------------------------------------------------------------------------

def test_project_template_round_trips():
    """The literal AC block in `spec-generation.md` must parse as criteria.

    Reads the shipped reference rather than a copy: if the template changes
    shape, this fails here instead of emitting a false warning in every project
    generated from it.
    """
    template = (
        REPO_ROOT / "plugins" / "shipwright-project" / "skills" / "project"
        / "references" / "spec-generation.md"
    ).read_text(encoding="utf-8")

    # The filled worked example is the shape a real generated spec carries.
    assert has_criteria(template, "FR-01.01") is True
    assert has_criteria(template, "FR-01.04") is True


def test_adopt_emission_round_trips():
    """Adopt's real `build_spec_md` output must parse — both branches.

    An FR carrying mined criteria reads as elaborated; one falling back to the
    `TBD` placeholder reads as missing. That second half is the signal the whole
    check exists for, so it is asserted against the producer, not a fixture.
    """
    with _adopt_lib_namespace():
        from lib.artifact_writer import _render_spec_md

    spec = _render_spec_md(
        project_name="demo",
        split_name="01-adopted",
        product_description="A demo.",
        features=[
            {
                "fr_id": "FR-01.01",
                "label": "Login",
                "acceptance_criteria": ["User can log in with email."],
                "acceptance_source": "tests",
            },
            {"fr_id": "FR-01.02", "label": "Signup", "acceptance_criteria": []},
        ],
        qr_items=[],
        constraints=[],
    )
    assert has_criteria(spec, "FR-01.01") is True
    assert has_criteria(spec, "FR-01.02") is False


def test_this_repos_own_catalogue_is_fully_elaborated():
    """The monorepo's own 18 requirements each carry criteria.

    The direct refutation of the S5 probe (which reports every one of them as
    missing) and a live regression guard: if a future round strips a
    requirement's criteria, this fails rather than the gap living on unnoticed
    for months — the failure this check was built for.
    """
    content = (
        REPO_ROOT / ".shipwright" / "planning" / "01-adopted" / "spec.md"
    ).read_text(encoding="utf-8")
    missing = [
        fid for fid in (f"FR-01.{n:02d}" for n in range(1, 19))
        if not has_criteria(content, fid)
    ]
    assert missing == []
