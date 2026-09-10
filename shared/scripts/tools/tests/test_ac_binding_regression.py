"""Direct unit tests for ``verifiers._ac_binding_regression`` (P3.7 feeder b,
arm 2) — the pure ``head_and_base_minted``/``binding_regressions`` pair, over
a real git repo (``_keystone_repo.py``, shared with the P3.6 keystone-gate
tests and ``test_check_orphan_ac_binding.py``, which exercises this module
only indirectly through the CLI).

External code review (glm, low) found the boundary conditions
``binding_regressions`` itself pins in its docstring — an AC absent at base,
and an AC whose digest changed at base — had no DIRECT test, only indirect
CLI coverage. Added here rather than folded into the CLI test module, so a
regression in the pure function's own guard is caught without a git
fixture's incidental behaviour masking it.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

from verifiers import _ac_binding_regression as arm2  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (helper)

from _keystone_repo import BASE_SPEC  # noqa: E402
from _keystone_repo import bound_manifest as _manifest_with_binding  # noqa: E402
from _keystone_repo import commit_spec as _commit_spec  # noqa: E402
from _keystone_repo import make_repo  # noqa: E402


def test_an_unreadable_base_text_is_lenient_not_a_readerror(tmp_path):
    """External code review (glm, medium): the docstring has always claimed
    the base side is lenient (warning, treated as empty) — an earlier version
    of the code raised ``ReadError`` on a ``None`` base read instead,
    contradicting it. A bogus ``base_sha`` (not a real commit) makes
    ``spec_text_at`` return ``None`` via a real git failure, not a mock."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding())
    head_manifest = _manifest_with_binding()
    head_minted, base_minted, warnings = arm2.head_and_base_minted(
        root, "0" * 40, "HEAD", head_manifest, head_manifest,
    )
    assert head_minted  # head side read fine
    assert base_minted == {}  # base treated as empty, not raised
    assert any("could not be read" in w for w in warnings)


def test_binding_regressions_skips_an_ac_absent_at_base():
    """A key present at head but absent at base (a newly-minted AC) is never
    a "regression" — nothing to regress FROM."""
    head_minted = {("FR-01.01", "AC01"): "digest-a"}
    base_minted: dict[tuple[str, str], str] = {}
    head_manifest = _manifest_with_binding(bind_ac=False)
    base_manifest = _manifest_with_binding(bind_ac=True)  # would look like a drop if compared
    out = arm2.binding_regressions(head_minted, base_minted, head_manifest, base_manifest)
    assert out == set()


def test_binding_regressions_skips_a_changed_digest():
    """A REAL edit (digest differs base->head) routes through P3.6's own
    ``binding_removed`` (design §7), not this arm — even with base_links>0
    and head_links=0, a changed digest must stay silent here."""
    head_minted = {("FR-01.01", "AC01"): "digest-after-edit"}
    base_minted = {("FR-01.01", "AC01"): "digest-before-edit"}
    head_manifest = _manifest_with_binding(bind_ac=False)  # 0 links at head
    base_manifest = _manifest_with_binding(bind_ac=True)   # >=1 link at base
    out = arm2.binding_regressions(head_minted, base_minted, head_manifest, base_manifest)
    assert out == set()


def test_binding_regressions_flags_an_unchanged_digest_that_lost_its_links():
    """Sanity check the positive case alongside the two negatives above: same
    digest at base and head, links at base, none at head -> a finding."""
    head_minted = {("FR-01.01", "AC01"): "digest-unchanged"}
    base_minted = {("FR-01.01", "AC01"): "digest-unchanged"}
    head_manifest = _manifest_with_binding(bind_ac=False)
    base_manifest = _manifest_with_binding(bind_ac=True)
    out = arm2.binding_regressions(head_minted, base_minted, head_manifest, base_manifest)
    assert out == {("FR-01.01", "AC01")}


def test_head_and_base_minted_reads_real_criteria_over_a_real_commit_pair(tmp_path):
    """Not a git-failure path: confirms the happy path still reads real spec
    text at two real commits, unchanged by the leniency fix above."""
    root = make_repo(tmp_path)
    base_sha = _commit_head_of(root)
    head_sha = _commit_spec(
        root, BASE_SPEC.replace("must whirr.", "must whirr loudly."), "reword AC03",
    )
    from _keystone_repo import manifest as _bare_manifest  # noqa: PLC0415

    m = _bare_manifest()
    head_minted, base_minted, warnings = arm2.head_and_base_minted(
        root, base_sha, head_sha, m, m,
    )
    assert warnings == []
    assert ("FR-01.01", "AC01") in head_minted
    assert ("FR-01.01", "AC01") in base_minted


def _commit_head_of(root: Path) -> str:
    from _keystone_repo import git as _git  # noqa: PLC0415

    return _git("rev-parse", "HEAD", cwd=root)
