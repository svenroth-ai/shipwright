"""Operator-run converge against an ADOPTED repo (trg-c1419d00).

An adopted repo receives no copy of ``shared/scripts``, so an operator reconciles
its accepted risks by running ``converge`` from a Shipwright checkout with
``--project-root`` pointed at the adopted repo. Identity, register, and triage all
come from that root — proven here without a network by stubbing the gh seam — and
the adopter-facing instruction in ``docs/security-ci-setup.md`` is pinned so it
can't silently rot (the same convention-drift-guard pattern used elsewhere).

The existing ``test_accepted_risks_converge_cli.py`` stubs ``owner_repo`` root-blind
(``lambda root: "svenroth-ai/shipwright"``), so it never shows identity tracking
the passed root — the exact property the cross-repo operator run depends on.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

import github_code_scanning as gcs  # noqa: E402
from tools import accepted_risks_converge as arc  # noqa: E402

RULE = "py/unused-global-variable"
REGISTER = """\
schema: 1
acceptances:
  - id: ar-live
    target: github-dismissal
    rule: {rule}
    scope:
      tool: CodeQL
      paths: ["a/b.py"]
    expires: 2027-01-01
    rationale_ref: ADR-271
    statement: >-
      a sufficiently long justification for accepting this finding
"""


def _adopted_repo(root: Path) -> Path:
    """A repo with a register at its root and NO ``shared/`` tree of its own."""
    root.mkdir(parents=True, exist_ok=True)
    (root / "shipwright_accepted_risks.yaml").write_text(
        REGISTER.format(rule=RULE), encoding="utf-8"
    )
    return root


def _api_alert(number=1, state="open", path="a/b.py", comment=None) -> dict:
    return {
        "number": number, "state": state, "dismissed_comment": comment,
        "tool": {"name": "CodeQL"}, "rule": {"id": RULE},
        "most_recent_instance": {"location": {"path": path}},
    }


class TestOperatorRunConvergeAgainstAdoptedRepo:
    def test_identity_and_register_come_from_the_targeted_root_not_cwd(
        self, tmp_path, monkeypatch
    ):
        """The operator points ``--project-root`` at the adopted repo; the repo
        slug is read from THAT root's origin (here a root-aware stub), and the
        plan is driven by THAT root's register — so a mutation can only land on
        the repo whose register authorised it, never on the checkout it ran from.
        """
        monkeypatch.setattr(arc.github_api, "owner_repo",
                            lambda root: f"acme/{Path(root).name}")
        monkeypatch.setattr(
            gcs, "list_alerts",
            lambda slug, st: [_api_alert()] if st == "open" else [],
        )
        adopted = _adopted_repo(tmp_path / "adopted-webui")
        slug, plan = arc.build_plan(adopted, now=date(2026, 7, 19))
        assert slug == "acme/adopted-webui"
        assert [a.number for _e, a in plan.to_dismiss] == [1]

    def test_each_adopted_root_resolves_to_its_own_identity(
        self, tmp_path, monkeypatch
    ):
        """Identity tracks the passed root, not a process-global — so one
        operator checkout can converge many adopted repos in turn."""
        monkeypatch.setattr(arc.github_api, "owner_repo",
                            lambda root: f"acme/{Path(root).name}")
        monkeypatch.setattr(gcs, "list_alerts", lambda slug, st: [])
        a = arc.build_plan(_adopted_repo(tmp_path / "repo-a"))[0]
        b = arc.build_plan(_adopted_repo(tmp_path / "repo-b"))[0]
        assert (a, b) == ("acme/repo-a", "acme/repo-b")


class TestAdopterDocsArePinned:
    def test_security_ci_setup_documents_operator_run_converge_for_adopters(self):
        """The primary deliverable of trg-c1419d00 is the adopter-facing
        instruction; pin it so it can't silently rot (convention-drift pattern).
        """
        text = (REPO_ROOT / "docs" / "security-ci-setup.md").read_text(
            encoding="utf-8"
        )
        assert "Adopted repos" in text, (
            "security-ci-setup.md must document operator-run converge for "
            "adopted repos (trg-c1419d00)"
        )
        adopter = text.split("Adopted repos", 1)[1]
        # the operator points --project-root at the adopted repo, from a checkout
        assert "--project-root /path/to/adopted-repo" in adopter
        # and is told the CLI is not shipped into the adopted tree
        assert "shared/scripts" in adopter
