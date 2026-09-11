"""``verifiers/_ac_baseline_growth.py`` — direct unit tests, real git (no
mocked reader), mirroring the house convention `test_ac_binding_regression.py`
already set for a pure module split out of a CLI (Stage-2 code review finding
4 on the P3.7 sub-iterate)."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

from verifiers._ac_baseline_growth import baseline_grown_since_parent  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (helper)

from _keystone_repo import commit_all, make_repo  # noqa: E402

BASELINE_REL = "shipwright_ac_coverage_baseline.json"


def _write_baseline(root: Path, unbound: list[str]) -> None:
    (root / BASELINE_REL).write_text(
        json.dumps({"schema_version": 1, "unbound": unbound}), encoding="utf-8",
    )


def test_a_newly_grandfathered_entry_is_reported(tmp_path):
    """The direct case: a same-PR `--write` that adds an unbound AC to the
    baseline in the SAME commit that unbound it — the escape external code
    review (openai, HIGH) found a plain push re-run could not see."""
    root = make_repo(tmp_path)
    _write_baseline(root, ["FR-01.01/AC01"])
    commit_all(root, "parent: baseline has AC01 grandfathered")
    _write_baseline(root, ["FR-01.01/AC01", "FR-01.01/AC02"])
    commit_all(root, "head: self-grandfather AC02 too")

    grown, warnings = baseline_grown_since_parent(
        root, root / BASELINE_REL, {"FR-01.01/AC01", "FR-01.01/AC02"},
    )
    assert grown == ["FR-01.01/AC02"]
    assert warnings == []


def test_a_stable_baseline_reports_no_growth(tmp_path):
    root = make_repo(tmp_path)
    _write_baseline(root, ["FR-01.01/AC01"])
    commit_all(root, "parent")
    (root / "README-unrelated.md").write_text("noise", encoding="utf-8")
    commit_all(root, "head: unrelated change, baseline untouched")

    grown, warnings = baseline_grown_since_parent(
        root, root / BASELINE_REL, {"FR-01.01/AC01"},
    )
    assert grown == []
    assert warnings == []


def test_shrinking_the_baseline_is_not_growth(tmp_path):
    """Binding an AC (removing it from the baseline) is always welcome per
    the baseline's own `$comment` — must never be reported as growth."""
    root = make_repo(tmp_path)
    _write_baseline(root, ["FR-01.01/AC01", "FR-01.01/AC02"])
    commit_all(root, "parent")
    _write_baseline(root, ["FR-01.01/AC01"])
    commit_all(root, "head: AC02 got bound, removed from baseline")

    grown, warnings = baseline_grown_since_parent(
        root, root / BASELINE_REL, {"FR-01.01/AC01"},
    )
    assert grown == []
    assert warnings == []


def test_the_commit_that_first_introduces_the_baseline_is_not_growth(tmp_path):
    """A parent commit with no baseline file at all is a BOOTSTRAP, not a
    growth event — the baseline gaining its very first entries must not
    block the PR that introduces it."""
    root = make_repo(tmp_path)  # parent: no baseline file
    _write_baseline(root, ["FR-01.01/AC01", "FR-01.01/AC02"])
    commit_all(root, "head: introduce the baseline for the first time")

    grown, warnings = baseline_grown_since_parent(
        root, root / BASELINE_REL, {"FR-01.01/AC01", "FR-01.01/AC02"},
    )
    assert grown == []
    assert warnings == []


def test_a_repo_with_no_parent_commit_fails_open_with_a_warning(tmp_path):
    """A single-commit repo (or a shallow checkout) has no `HEAD~1` to diff
    against — this auxiliary signal must fail OPEN (never block on its own
    infra fault), unlike the primary gate's fail-CLOSED default."""
    root = make_repo(tmp_path)  # exactly one commit
    grown, warnings = baseline_grown_since_parent(
        root, root / BASELINE_REL, {"FR-01.01/AC01"},
    )
    assert grown == []
    assert warnings and "HEAD~1" in warnings[0]


def test_a_multi_commit_push_needs_the_before_sha_not_bare_head_tilde_1(tmp_path):
    """External code review (openai, HIGH, second round): a push can carry
    more than one commit. If growth happens in an EARLIER commit of the push
    and the pushed tip leaves the baseline untouched, `HEAD~1` (the tip's
    immediate parent) already contains the grown entry and misses it — only
    diffing against the push's own `before` SHA (main's tip before the WHOLE
    push landed) catches it."""
    root = make_repo(tmp_path)
    _write_baseline(root, ["FR-01.01/AC01"])
    before_sha = commit_all(root, "before: main's tip prior to this push")
    _write_baseline(root, ["FR-01.01/AC01", "FR-01.01/AC02"])
    commit_all(root, "push commit 1 of 2: self-grandfather AC02")
    (root / "README-unrelated.md").write_text("noise", encoding="utf-8")
    commit_all(root, "push commit 2 of 2 (the pushed tip): unrelated, baseline untouched")

    # The bug this closes: comparing against the immediate parent (this
    # push's own commit 1) already contains AC02 — it is invisible.
    grown_vs_head_tilde_1, _ = baseline_grown_since_parent(
        root, root / BASELINE_REL, {"FR-01.01/AC01", "FR-01.01/AC02"},
    )
    assert grown_vs_head_tilde_1 == [], (
        "sanity check: HEAD~1 alone must NOT catch this — it is the whole bug"
    )

    # The fix: comparing against `before` (the push's real pre-image) does.
    grown_vs_before, warnings = baseline_grown_since_parent(
        root, root / BASELINE_REL, {"FR-01.01/AC01", "FR-01.01/AC02"}, before_sha,
    )
    assert grown_vs_before == ["FR-01.01/AC02"]
    assert warnings == []


def test_an_unresolvable_parent_sha_fails_open_with_a_warning(tmp_path):
    """GitHub sends an all-zeros `before` on a brand-new branch's first push
    — not a real commit. Must fail open (never block), but — unlike a real
    parent commit that simply predates the baseline file (a legit bootstrap,
    silent) — an explicitly-supplied SHA that resolves to NOTHING is a fault
    worth surfacing (external code review, glm, low): the push CI path is
    exactly where an unresolvable `before` would otherwise vanish with zero
    telemetry."""
    root = make_repo(tmp_path)
    _write_baseline(root, ["FR-01.01/AC01"])
    commit_all(root, "head")

    grown, warnings = baseline_grown_since_parent(
        root, root / BASELINE_REL, {"FR-01.01/AC01"}, "0" * 40,
    )
    assert grown == []
    assert warnings and "does not resolve to a commit" in warnings[0]


def test_a_baseline_path_outside_project_root_fails_open(tmp_path):
    """`--baseline` can point anywhere; `relative_to` raises on a path
    outside `project_root` (external code review, glm, low) — must fail
    open like every other unreadable-parent case, not escape as a crash."""
    root = make_repo(tmp_path)
    (root / "README-unrelated.md").write_text("noise", encoding="utf-8")
    commit_all(root, "head")  # a real parent commit, so HEAD~1 itself resolves fine
    outside = tmp_path / "elsewhere" / "baseline.json"
    outside.parent.mkdir()
    outside.write_text(json.dumps({"unbound": []}), encoding="utf-8")

    grown, warnings = baseline_grown_since_parent(root, outside, {"FR-01.01/AC01"})
    assert grown == []
    assert warnings and "not under --project-root" in warnings[0]


def test_an_unparseable_parent_baseline_fails_open_with_a_warning(tmp_path):
    root = make_repo(tmp_path)
    (root / BASELINE_REL).write_text("not json", encoding="utf-8")
    commit_all(root, "parent: corrupt baseline")
    _write_baseline(root, ["FR-01.01/AC01"])
    commit_all(root, "head")

    grown, warnings = baseline_grown_since_parent(
        root, root / BASELINE_REL, {"FR-01.01/AC01"},
    )
    assert grown == []
    assert warnings and "not valid JSON" in warnings[0]


def test_a_baseline_shadowed_by_a_directory_at_the_parent_warns_not_bootstraps(tmp_path):
    """Stage-3 doubt review (high): a genuine git-level read fault at the
    parent commit — here, the path being a TREE instead of a blob — must be
    distinguishable from "the file simply doesn't exist yet" (a legit
    bootstrap). Both used to surface as a bare non-zero exit from a raw
    ``git show``; routing through ``git_blob_read.blob_oid`` (which checks
    the entry's git object type) tells them apart and this one must warn."""
    root = make_repo(tmp_path)
    (root / BASELINE_REL).mkdir()
    (root / BASELINE_REL / "not-a-baseline.txt").write_text("oops", encoding="utf-8")
    commit_all(root, "parent: the baseline path is a directory, not a file")
    shutil.rmtree(root / BASELINE_REL)
    _write_baseline(root, ["FR-01.01/AC01"])
    commit_all(root, "head: the baseline path is now a real file")

    grown, warnings = baseline_grown_since_parent(
        root, root / BASELINE_REL, {"FR-01.01/AC01"},
    )
    assert grown == []
    assert warnings and "not a regular file" in warnings[0]


def test_a_non_utf8_parent_baseline_does_not_raise(tmp_path):
    """Stage-3 doubt review (high): the parent-blob read must never raise —
    a raw ``subprocess.run(..., text=True)`` decodes strictly and would let
    an invalid byte in a historically-committed baseline escape as an
    uncaught ``UnicodeDecodeError``, which reaches `main()`'s catch-all and
    returns EXIT_INFRA — indistinguishable, at the CI shell-exit-code level,
    from EXIT_BLOCKED. Reading through ``_run_git`` (``errors=\"ignore\"``)
    must keep this on the ordinary fail-open path instead."""
    root = make_repo(tmp_path)
    (root / BASELINE_REL).write_bytes(b'{"unbound": ["FR-01.01/AC01\xff\xfe"]}')
    commit_all(root, "parent: baseline contains an invalid UTF-8 byte")
    _write_baseline(root, ["FR-01.01/AC01"])
    commit_all(root, "head")

    grown, warnings = baseline_grown_since_parent(  # must not raise
        root, root / BASELINE_REL, {"FR-01.01/AC01"},
    )
    assert grown == []
    assert isinstance(warnings, list)
