"""P3.6 THE KEYSTONE GATE — the CLI's infrastructure boundaries.

Second half of ``test_check_keystone_ac_gate.py`` (split to keep both modules
under the 300-line source limit). Covers AC-K9(e) (the base-manifest three-way
read), AC-K11 (base resolution through ``_merge_base``'s own verdict, never a
hardcoded ``origin/main``) and the ONE subprocess smoke.

Every case here asserts the gate fails CLOSED. The failure mode this file exists
to prevent is not a wrong verdict but a green one: a base read that quietly
returns ``{}``, or a resolver that quietly returns "nothing changed", both exit 0
on a PR nobody graded.
"""


from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # shared/scripts/tools

import check_keystone_ac_gate as gate  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests dir (helper)

from _keystone_repo import BASE_SPEC, MANIFEST_RELPATH, SPEC_REL  # noqa: E402
from _keystone_repo import bound_manifest as _manifest_with_binding  # noqa: E402
from _keystone_repo import commit_all as _commit_all  # noqa: E402
from _keystone_repo import commit_spec as _commit_spec  # noqa: E402
from _keystone_repo import edit_ac01 as _edit_ac01  # noqa: E402
from _keystone_repo import git as _git  # noqa: E402
from _keystone_repo import make_repo, write_manifest  # noqa: E402
from _keystone_repo import run_gate as _run  # noqa: E402

_TOOLS = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path, manifest_obj=_manifest_with_binding())


# --------------------------------------------------------------------------
# AC-K9(e) — the base-manifest three-way read
# --------------------------------------------------------------------------

def test_an_absent_base_manifest_degrades_loudly_with_its_own_json_key(repo, capsys):
    """AC-K9(e)(i). Case (i) genuinely disarms ``binding_removed`` for this PR —
    which is exactly the state an attacker would want — so the degradation must
    be detectable by KEY, never inferred from prose or from silence."""
    (repo / MANIFEST_RELPATH).unlink()
    base = _commit_all(repo, "a base predating the compliance manifest")
    write_manifest(repo, _manifest_with_binding(bind_ac=False))
    head = _commit_spec(
        repo, BASE_SPEC.replace("The widget must fizz.", "fizz TWICE."), "edit")
    code = gate.main(["--project-root", str(repo), "--head-sha", head, "--base-sha", base])
    payload = json.loads(capsys.readouterr().out)
    assert code == gate.EXIT_OK
    assert "base_manifest_absent" in payload
    assert [f["kind"] for f in payload["findings"]] == []
    assert payload["unbound"] == ["FR-01.01/AC01"], "binding_removed is disarmed — hence the key"


def test_an_unparseable_base_manifest_is_an_infra_fault_not_an_absent_one(repo, capsys):
    """AC-K9(e)(ii). A corrupt EXISTING manifest is categorically unlike an
    honestly-absent one; defaulting it to ``{}`` (the surrounding repo's house
    pattern for base reads) would silently zero every base link count."""
    (repo / MANIFEST_RELPATH).write_text("{not json", encoding="utf-8")
    base = _commit_all(repo, "corrupt the manifest")
    write_manifest(repo, _manifest_with_binding())
    head = _commit_spec(repo, BASE_SPEC, "restore")
    code = gate.main(["--project-root", str(repo), "--head-sha", head, "--base-sha", base])
    payload = json.loads(capsys.readouterr().out)
    assert code == gate.EXIT_INFRA
    assert payload["status"] == "infra_fault"
    assert "not valid JSON" in payload["error"]


def _nested(**node_extra) -> dict:
    """A structurally plausible manifest whose ONE requirement carries ``node_extra``."""
    return {"requirements": {"ns::FR-01.01": {
        "id": "FR-01.01", "status": "active", "spec_path": SPEC_REL,
        "required_layers": ["unit"], "required_layers_source": "inferred_legacy",
        **node_extra,
    }}}


@pytest.mark.parametrize(("bad", "expected"), [
    ({"requirements": []}, "not an object"),
    ({"requirements": "ns::FR-01.01"}, "not an object"),
    ({"generated_at": "2026-09-09"}, "no 'requirements' key"),
    # Tier-3 PR review (BLOCKING) — the first fix stopped at the top level, and so
    # did its tests. `_links_for` spells the same fragile idiom twice more, so
    # these two crashed one and two levels down with the top-level guard in place.
    (_nested(acs=[]), "acs is of type list"),
    (_nested(acs={"AC01": {"tests": []}}), "acs['AC01'].tests is of type list"),
    (_nested(acs={"AC01": {"tests": "unit"}}), "acs['AC01'].tests is of type str"),
])
def test_a_valid_json_but_malformed_head_manifest_exits_two_with_json(repo, capsys, bad, expected):
    """External code review (openai, medium) — the crash path.

    Every reader spells the lookup ``(manifest.get("requirements") or {}).values()``,
    which is safe for missing and falsy and raises ``AttributeError`` on a truthy
    non-mapping. Uncaught that is exit **1 with no stdout**, which reads in a CI log
    exactly like a real hard finding and sends the author to edit a fine spec.
    Asserted through ``main`` (never the helper alone) because the contract under
    test is "exit 2 AND a JSON verdict", not "raises".
    """
    _edit_ac01(repo)
    write_manifest(repo, bad)
    head = _git("rev-parse", "HEAD", cwd=repo)
    code = gate.main(["--project-root", str(repo), "--head-sha", head,
                      "--base-sha", _git("rev-parse", "HEAD~1", cwd=repo)])
    payload = json.loads(capsys.readouterr().out)
    assert code == gate.EXIT_INFRA
    assert payload["status"] == "infra_fault"
    assert expected in payload["error"]


def test_a_non_mapping_node_or_ac_node_is_SKIPPED_not_rejected(repo, capsys):
    """The deliberate asymmetry, pinned so it is not "tidied" into symmetry.

    Validation covers exactly what the readers do NOT guard. Every reader already
    spells `isinstance(node, dict)` / `isinstance(ac_node, dict)`, so rejecting
    those here would make this function a second copy of the manifest schema —
    free to drift from the one the readers actually enforce. `acs` and `tests`
    are validated because nothing guards them.
    """
    manifest = _nested(acs={"AC01": "not a mapping"})
    manifest["requirements"]["ns::garbage"] = ["not", "a", "mapping"]
    _edit_ac01(repo)
    write_manifest(repo, manifest)
    head = _git("rev-parse", "HEAD", cwd=repo)
    code, payload = _run(repo, head, capsys=capsys)
    # Not exit 2: the gate REACHED a verdict on the merits. The fixture repo's base
    # binds AC01, and this head does not, so the verdict is the ordinary one.
    assert code == gate.EXIT_BLOCKED
    assert [f["kind"] for f in payload["findings"]] == ["binding_removed"]


def test_a_malformed_BASE_manifest_is_an_infra_fault_too(repo, capsys):
    """The same validation at the other trust boundary. A base whose
    ``requirements`` is a list would otherwise read as "zero links at base" for
    every AC — silently disarming ``binding_removed``, the one finding the base
    read exists to make possible. The nested case matters for the same reason and
    is the one the Tier-3 PR review named: a base whose ``acs`` is a list is
    ``base_links == 0`` everywhere."""
    write_manifest(repo, {"requirements": []})
    base_flat = _commit_all(repo, "a base with a list-shaped requirements")
    write_manifest(repo, _nested(acs=[]))
    base_nested = _commit_all(repo, "a base with a list-shaped acs")
    write_manifest(repo, _manifest_with_binding())
    head = _commit_spec(
        repo, BASE_SPEC.replace("The widget must fizz.", "fizz TWICE."), "edit")
    for base, expected in ((base_flat, "not an object"), (base_nested, "acs is of type list")):
        code = gate.main(["--project-root", str(repo), "--head-sha", head, "--base-sha", base])
        payload = json.loads(capsys.readouterr().out)
        assert code == gate.EXIT_INFRA
        assert expected in payload["error"]


def test_a_base_ref_git_cannot_resolve_is_an_infra_fault(repo, capsys):
    head = _git("rev-parse", "HEAD", cwd=repo)
    code = gate.main(
        ["--project-root", str(repo), "--head-sha", head, "--base-sha", "0" * 40])
    payload = json.loads(capsys.readouterr().out)
    assert code == gate.EXIT_INFRA
    assert payload["status"] == "infra_fault"


def test_the_empty_link_tripwire_exits_two_not_one(repo, capsys, monkeypatch):
    """Self-review finding. ``EmptyLinkWalk`` marks a bug in the GATE, not a
    finding about the repo. Uncaught, Python exits ``1`` — indistinguishable
    from a real hard finding, so a gate defect would read as "this PR is
    blocked" and send an author editing a spec that is fine. A gate that cannot
    decide is an infrastructure fault: exit ``2``, with JSON."""
    def _boom(*_a, **_k):
        raise gate.EmptyLinkWalk("FR-01.01/AC01: zero links")

    monkeypatch.setattr(gate, "evaluate_keystone", _boom)
    head = _edit_ac01(repo)
    code, payload = _run(repo, head, capsys=capsys)
    assert code == gate.EXIT_INFRA
    assert payload["status"] == "infra_fault"
    assert "defect in the gate" in payload["error"]


def test_a_missing_regenerated_head_manifest_is_an_infra_fault(repo, capsys):
    """The gate must NOT grade a PR when the file the regeneration step is
    supposed to have written is not there — that is a wiring fault, and reading
    "no bindings" out of it would be a silent pass."""
    head = _edit_ac01(repo)
    (repo / MANIFEST_RELPATH).unlink()
    code, payload = _run(repo, head, capsys=capsys)
    assert code == gate.EXIT_INFRA
    assert "AFTER the manifest-regeneration step" in payload["error"]


# --------------------------------------------------------------------------
# AC-K11 — base resolution
# --------------------------------------------------------------------------

def test_an_unresolvable_merge_base_exits_two_naming_the_fetch_remedy(repo, capsys, monkeypatch):
    """AC-K11 — fail-closed, never a green "nothing changed"."""
    monkeypatch.setattr(gate, "_merge_base", lambda root, commit: "")
    head = _git("rev-parse", "HEAD", cwd=repo)
    code = gate.main(["--project-root", str(repo), "--head-sha", head])
    payload = json.loads(capsys.readouterr().out)
    assert code == gate.EXIT_INFRA
    assert "git fetch --no-tags origin" in payload["error"]


def test_merge_base_is_the_resolver_and_no_origin_main_is_required(repo, capsys, monkeypatch):
    """AC-K11's companion, the round-3 finding-3 pin: a repo whose default branch
    is ``master`` (no ``origin/main`` at ALL) must exit on the merits, not 2.

    ``_merge_base`` resolves through ``origin/HEAD`` → ``@{u}`` → ``origin/main``
    → ``origin/master`` → local ``main``/``master``, so a hardcoded
    ``git rev-parse --verify origin/main`` precondition would have redded this
    repo as a false infra fault.
    """
    _git("branch", "-m", "main", "master", cwd=repo)
    head = _edit_ac01(repo)
    base = _git("rev-parse", "HEAD~1", cwd=repo)
    seen: list[str] = []

    def _fake_merge_base(root, commit):
        seen.append(commit)
        return base

    monkeypatch.setattr(gate, "_merge_base", _fake_merge_base)
    code = gate.main(["--project-root", str(repo), "--head-sha", head])
    payload = json.loads(capsys.readouterr().out)
    assert seen == [head], "the CLI must ask _merge_base, not a hardcoded ref"
    assert code == gate.EXIT_OK
    assert payload["base_sha"] == base
    assert _git("rev-parse", "--verify", "--quiet", "master", cwd=repo)


# --------------------------------------------------------------------------
# The one subprocess smoke
# --------------------------------------------------------------------------

def test_the_cli_starts_and_exits_cleanly_as_a_real_subprocess(repo):
    """Deliberately the ONLY subprocess case (see the module docstring). It
    guards one thing the in-process cases structurally cannot: that the module's
    own ``sys.path`` bootstrap works outside pytest's collection side effects.
    """
    head = _edit_ac01(repo)
    base = _git("rev-parse", "HEAD~1", cwd=repo)
    done = subprocess.run(
        [sys.executable, str(_TOOLS / "check_keystone_ac_gate.py"),
         "--project-root", str(repo), "--head-sha", head, "--base-sha", base],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    assert done.returncode == gate.EXIT_OK, done.stderr
    assert json.loads(done.stdout)["changed_acs"] == ["FR-01.01/AC01"]
