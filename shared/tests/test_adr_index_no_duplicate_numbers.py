"""AC5 — no *new* ADR spec-folder numeric-prefix collision.

This is a backsliding guard, not an allocator: the final design (see the
iterate spec for iterate-2026-08-08-index-readers-adr-lock,
``### Architecture Review``) retired hand-guessed numbers entirely — new ADR
spec files are named ``<run_id_sanitized>-<slug>.md`` (F3.md), which cannot
collide because ``run_id`` is already globally unique. This test only
catches someone reverting to the old ``<NNN>-<slug>.md`` shape and guessing
a number that is already taken.

Baseline: ``<project_root>/shipwright_adr_collision_baseline.json``,
regenerated only by ``scripts/tools/rebuild_adr_collision_baseline.py`` —
never by this test (a self-regenerating guard would silently absorb a
same-run collision as "baseline" and protect nothing — external-review
finding 5).

Rule, per pinned number: ``actual_files`` must be a SUBSET of
``pinned_files`` (shrinking — renaming a grandfathered file away — is always
allowed and must never fail the guard). For a number NOT in the baseline: at
most one file.
"""

from __future__ import annotations

from pathlib import Path

from lib import adr_collision_baseline as baseline_mod
from lib.adr_index import adr_spec_folder

_REPO_ROOT = Path(__file__).resolve().parents[2]


def test_this_repos_committed_baseline_covers_every_actual_collision():
    folder = adr_spec_folder(_REPO_ROOT)
    pinned = baseline_mod.load(_REPO_ROOT)
    actual = baseline_mod.collect_collisions(folder)

    extra = baseline_mod.unpinned_collisions(actual, pinned)
    assert not extra, (
        f"New numeric-prefix ADR collision(s) not covered by the pinned "
        f"baseline: {extra}. Name new ADR spec files "
        "<run_id_sanitized>-<slug>.md instead of guessing a number "
        "(see F3.md); a knowingly-accepted collision must be pinned via "
        "scripts/tools/rebuild_adr_collision_baseline.py."
    )


def test_guard_actually_fails_on_a_fresh_unpinned_collision(tmp_path):
    """Prove the guard logic (the SHIPPED helper, not a re-typed copy) can
    fail, not just pass."""
    folder = tmp_path / "adr"
    folder.mkdir()
    (folder / "500-a.md").write_text("# A\n", encoding="utf-8")
    (folder / "500-b.md").write_text("# B\n", encoding="utf-8")

    actual = baseline_mod.collect_collisions(folder)
    pinned: dict[str, list[str]] = {}  # nothing pinned for 500

    extra = baseline_mod.unpinned_collisions(actual, pinned)
    assert extra == {"500": ["500-a.md", "500-b.md"]}


def test_shrinking_a_pinned_number_is_allowed(tmp_path):
    """Renaming ONE of a pinned TRIPLE away must not fail the guard — the
    subset rule (Opus finding 7), not exact membership. Pinning only a pair
    would make ``collect_collisions`` drop the remainder as a non-collision
    before the subset rule is ever exercised (a single file is not a
    collision) — a triple keeps a real 2-file collision on the ground for
    the rule to actually check."""
    folder = tmp_path / "adr"
    folder.mkdir()
    (folder / "097-a.md").write_text("# A\n", encoding="utf-8")
    (folder / "097-b.md").write_text("# B\n", encoding="utf-8")
    # 097-c.md renamed away — only a and b remain on disk

    actual = baseline_mod.collect_collisions(folder)
    pinned = {"97": ["097-a.md", "097-b.md", "097-c.md"]}

    assert actual == {"97": ["097-a.md", "097-b.md"]}  # still a real collision
    assert baseline_mod.unpinned_collisions(actual, pinned) == {}  # but fully covered


def test_a_new_run_id_named_file_is_never_treated_as_a_collision(tmp_path):
    """Freeform (non-numeric-prefix) filenames are outside this guard's
    scope entirely — that is the whole point of the final naming design."""
    folder = tmp_path / "adr"
    folder.mkdir()
    (folder / "iterate-2026-08-08-index-readers-adr-lock-adr-naming.md").write_text(
        "# ADR naming\n", encoding="utf-8"
    )
    (folder / "iterate-2026-08-08-some-other-run-adr-naming.md").write_text(
        "# Other\n", encoding="utf-8"
    )
    assert baseline_mod.collect_collisions(folder) == {}


def test_guard_module_never_imports_the_regeneration_tool():
    """A self-regenerating guard would silently absorb a same-run collision
    as 'baseline' and protect nothing (external-review finding 5). Checks
    actual import statements (AST), not the docstring, which legitimately
    names the tool as the documented remedy."""
    import ast
    import inspect

    tree = ast.parse(inspect.getsource(baseline_mod))
    imported_modules = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    assert not any("rebuild_adr_collision_baseline" in m for m in imported_modules)
