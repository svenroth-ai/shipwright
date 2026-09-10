"""``check_orphan_ac_binding.py`` — P3.7 feeder (b), "a test whose AC vanished",
HARD from day one (SPEC §8 E2). Both arms, over a real git repo
(``_keystone_repo.py``, shared with the P3.6 keystone-gate tests).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

import check_orphan_ac_binding as gate  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (helper)

from _keystone_repo import BASE_SPEC, SPEC_REL  # noqa: E402
from _keystone_repo import bound_manifest as _manifest_with_binding  # noqa: E402
from _keystone_repo import commit_all as _commit_all  # noqa: E402
from _keystone_repo import commit_spec as _commit_spec  # noqa: E402
from _keystone_repo import git as _git  # noqa: E402
from _keystone_repo import make_repo, write_manifest  # noqa: E402

_TOOLS = Path(__file__).resolve().parents[1]


def _run(root: Path, head_sha: str, base_sha: str = "HEAD~1", capsys=None) -> tuple[int, dict]:
    resolved = _git("rev-parse", base_sha, cwd=root) if base_sha else ""
    argv = ["--project-root", str(root), "--head-sha", head_sha]
    if resolved:
        argv += ["--base-sha", resolved]
    code = gate.main(argv)
    payload = json.loads(capsys.readouterr().out)
    return code, payload


def test_a_docs_only_commit_is_clean(capsys, tmp_path):
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding())
    (root / "README.md").write_text("hi\n", encoding="utf-8")
    code, payload = _run(root, _commit_all(root, "docs"), capsys=capsys)
    assert code == gate.EXIT_OK
    assert payload["status"] == "clean"
    assert payload["orphaned_bindings"] == []
    assert payload["binding_regressions"] == []


# --------------------------------------------------------------------------
# Arm 1 -- orphaned bindings (SPEC §8 E2(b) shapes ii/iii)
# --------------------------------------------------------------------------

def test_deleting_a_bound_criterion_outright_orphans_its_binding(capsys, tmp_path):
    """Shape (ii): the criterion is gone, but the manifest (regenerated from a
    NOT-YET-updated @covers tag) still carries a binding under its old id."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding())
    head = _commit_spec(
        root, BASE_SPEC.replace("- [AC01] The widget must fizz.\n", ""), "delete AC01")
    code, payload = _run(root, head, capsys=capsys)
    assert code == gate.EXIT_BLOCKED
    assert payload["orphaned_bindings"] == ["FR-01.01/AC01"]


def test_id_rotation_orphans_the_old_id(capsys, tmp_path):
    """Shape (iii): `[AC01] foo` -> `[AC55] foo` (same wording). The old
    binding, still filed under AC01 in the (stale, not-yet-regenerated-by-a-
    real-collector-run) manifest, now names an id the spec no longer mints."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding())
    head = _commit_spec(
        root, BASE_SPEC.replace("[AC01] The widget must fizz.", "[AC55] The widget must fizz."),
        "rotate AC01 -> AC55")
    code, payload = _run(root, head, capsys=capsys)
    assert code == gate.EXIT_BLOCKED
    assert payload["orphaned_bindings"] == ["FR-01.01/AC01"]


def test_deleting_the_whole_spec_file_still_orphans_its_bound_acs(capsys, tmp_path):
    """External code review (openai, HIGH). Deleting the ENTIRE spec file (not
    just one criterion) is a genuine ABSENCE at head, not a read FAULT --
    `spec_text_at` returns `""` for it, and `read_binding_state` now proceeds
    with zero minted criteria for that FR rather than excluding it. An
    earlier version silently excluded this case, which made the HARD orphan
    check fail open on exactly the PR it exists to catch."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding())
    (root / SPEC_REL).unlink()
    head = _commit_all(root, "delete the whole spec file")
    code, payload = _run(root, head, capsys=capsys)
    assert code == gate.EXIT_BLOCKED
    assert payload["orphaned_bindings"] == ["FR-01.01/AC01"]


def test_an_unbound_ac_with_no_prior_binding_is_not_an_orphan(capsys, tmp_path):
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding(bind_ac=False))
    head = _commit_spec(root, BASE_SPEC.replace("must whirr.", "must whirr loudly."), "reword")
    code, payload = _run(root, head, capsys=capsys)
    assert code == gate.EXIT_OK
    assert payload["orphaned_bindings"] == []


# --------------------------------------------------------------------------
# Arm 2 -- binding regressions on unchanged text (SPEC §8 E2(b) shape i, the
# two-PR sequence, closed at PR1 rather than waited-out to PR2)
# --------------------------------------------------------------------------

def test_dropping_a_binding_with_no_criterion_text_change_is_a_regression(capsys, tmp_path):
    """PR1 of the two-PR sequence: the `@covers` tag loses its `/AC01` suffix
    (modelled here as the manifest simply losing its `acs` entry for AC01,
    exactly what the real collector would regenerate), while AC01's own text
    in spec.md is untouched. base_links=1 (fixture), head_links=0 (this
    commit) -> a HARD finding, even though NOTHING in spec.md changed."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding(bind_ac=True))
    write_manifest(root, _manifest_with_binding(bind_ac=False))
    head = _commit_all(root, "drop the AC01 binding, spec untouched")
    code, payload = _run(root, head, capsys=capsys)
    assert code == gate.EXIT_BLOCKED
    assert payload["binding_regressions"] == ["FR-01.01/AC01"]
    assert payload["orphaned_bindings"] == []  # arm 1 genuinely cannot see this shape


def test_editing_the_criterion_in_the_same_pr_is_not_a_regression(capsys, tmp_path):
    """A REAL edit routes through P3.6's own `binding_removed` (design §7),
    not this arm -- this arm is scoped to UNCHANGED text only, so it must
    stay silent here or the two checks would double-report the same PR."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding(bind_ac=True))
    write_manifest(root, _manifest_with_binding(bind_ac=False))
    head = _commit_spec(
        root, BASE_SPEC.replace("The widget must fizz.", "The widget must fizz TWICE."),
        "edit AC01 text AND drop its binding in the same PR")
    code, payload = _run(root, head, capsys=capsys)
    assert code == gate.EXIT_OK
    assert payload["binding_regressions"] == []


def test_a_never_bound_ac_staying_unbound_is_not_a_regression(capsys, tmp_path):
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding(bind_ac=False))
    (root / "README.md").write_text("noop\n", encoding="utf-8")
    head = _commit_all(root, "docs")
    code, payload = _run(root, head, capsys=capsys)
    assert code == gate.EXIT_OK
    assert payload["binding_regressions"] == []


def test_an_infra_fault_from_arm_2_still_carries_arm_1s_orphan_finding(capsys, tmp_path):
    """Doubt review, low: arm ordering -- if arm 2 raises (a genuine
    cross-spec-path collision at head), arm 1's already-computed
    `orphaned_bindings` must not be discarded from the infra-fault payload;
    an author facing both a real orphan and this fault should see both."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding())
    second_rel = "docs/spec2.md"
    (root / second_rel).write_text(
        "# Spec 2\n\n## 2. Functional Requirements\n\n### FR-01.02: Gadgets\n\n"
        "- [AC03] A duplicate anchor for the SAME (fr, ac) in a second document.\n",
        encoding="utf-8",
    )
    m = _manifest_with_binding()
    m["requirements"]["ns::FR-01.02-dup"] = {
        "id": "FR-01.02", "status": "active", "spec_path": second_rel, "acs": {},
    }
    write_manifest(root, m)
    head = _commit_spec(
        root, BASE_SPEC.replace("- [AC01] The widget must fizz.\n", ""),
        "delete AC01 (a real orphan) + add a colliding second FR-01.02 doc")
    code, payload = _run(root, head, capsys=capsys)
    assert code == gate.EXIT_INFRA
    assert payload["orphaned_bindings"] == ["FR-01.01/AC01"]


def test_the_cli_starts_and_exits_cleanly_as_a_real_subprocess(tmp_path):
    """Deliberately the ONLY subprocess case in this module (house convention,
    ``test_keystone_gate_infra.py``)."""
    root = make_repo(tmp_path, manifest_obj=_manifest_with_binding())
    head = _commit_spec(
        root, BASE_SPEC.replace("- [AC01] The widget must fizz.\n", ""), "delete AC01")
    base = _git("rev-parse", "HEAD~1", cwd=root)
    done = subprocess.run(
        [sys.executable, str(_TOOLS / "check_orphan_ac_binding.py"),
         "--project-root", str(root), "--head-sha", head, "--base-sha", base],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert done.returncode == gate.EXIT_BLOCKED, done.stderr
    assert json.loads(done.stdout)["orphaned_bindings"] == ["FR-01.01/AC01"]
