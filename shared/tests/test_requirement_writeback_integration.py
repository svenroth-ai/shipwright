"""The requirement write-back loop, end to end, in one repository.

The unit tests prove each piece. This proves the pieces *compose* — that the
loop the work exists to close actually closes: a design round rethinks a flow and
the requirement follows it; a build section meets a contradiction, a person
resolves it toward the mockup, and the correction is recorded and verifiable;
and a shared touch the section genuinely needed is accounted for rather than
silently absorbed.

Origin: trg-e9e5188e (FR-01.04, FR-01.05).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts" / "tools"))

from check_section_file_attribution import main as check_main  # noqa: E402
from lib.requirement_impact_store import (  # noqa: E402
    declaration_dir,
    find_declaration,
    read_declarations,
)
from record_requirement_impact import main as record_main  # noqa: E402

SPEC = ".shipwright/planning/01-checkout/spec.md"
SECTION_FILE = ".shipwright/planning/01-checkout/sections/01-payment.md"
DESIGN_RUN = "design-run-2026-07-27"
BUILD_RUN = "build-run-2026-07-27"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True,
                   capture_output=True, text=True)


def _write(repo: Path, rel: str, text: str) -> None:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


@pytest.fixture
def project(tmp_path: Path) -> Path:
    """A project whose requirement describes a one-step checkout."""
    _git(tmp_path, "init", "-q", "-b", "main")
    _git(tmp_path, "config", "user.email", "t@t")
    _git(tmp_path, "config", "user.name", "t")
    _write(tmp_path, SPEC,
           "# Checkout\n\n"
           "| FR-01.09 | Checkout | Must | The customer pays in one step. |\n\n"
           "### FR-01.09\n"
           "- (E) Given a basket, when the customer checks out, then they pay "
           "in one step.\n")
    _write(tmp_path, SECTION_FILE,
           "# Section: 01-payment\n\n"
           "## Files to Create/Modify\n"
           "- `src/checkout/pay.ts` — the payment step\n\n"
           "## Verification\n- [ ] tests pass\n")
    _write(tmp_path, ".shipwright/designs/screens/03-checkout.html", "<html>one step</html>")
    _write(tmp_path, "src/checkout/pay.ts", "export const pay = () => {};\n")
    _write(tmp_path, "src/lib/money.ts", "export const fmt = (n: number) => `${n}`;\n")
    _git(tmp_path, "add", "-A")
    _git(tmp_path, "commit", "-qm", "base")
    return tmp_path


def _snapshot(project, run_id, phase, scope):
    """Start a round/section: capture the requirement baseline it will be judged against."""
    record_main(["--project-root", str(project), "--run-id", run_id,
                 "--phase", phase, "--scope", scope, "--snapshot-baseline"])


def test_the_loop_closes_from_design_round_through_build_section(project, capsys):
    # --- Design round 2: feedback adds a confirmation step. That is BEHAVIOUR,
    # so the requirement must be corrected before the design can be approved.
    _snapshot(project, DESIGN_RUN, "design", "round-2")
    capsys.readouterr()
    _write(project, ".shipwright/designs/screens/03-checkout.html",
           "<html>review, then confirm</html>")
    _write(project, SPEC,
           "# Checkout\n\n"
           "| FR-01.09 | Checkout | Must | The customer reviews the order, then "
           "confirms payment. |\n\n"
           "### FR-01.09\n"
           "- (E) Given a basket, when the customer checks out, then they review "
           "the order and confirm before paying.\n")

    assert record_main([
        "--project-root", str(project), "--run-id", DESIGN_RUN,
        "--phase", "design", "--scope", "round-2",
        "--impact", "modify", "--fr", "FR-01.09", "--worktree",
    ]) == 0
    capsys.readouterr()

    design_decl, design_problems = find_declaration(
        declaration_dir(project), run_id=DESIGN_RUN, phase="design", scope="round-2")
    assert design_problems == []
    assert design_decl["impact"] == "modify"
    assert design_decl["touch_check"]["spec_files"] == [SPEC]

    _git(project, "add", "-A")
    _git(project, "commit", "-qm", "design round 2")

    # --- Build: the section still says "one step" while the approved mockup shows
    # a confirm step. A person resolves it toward the mockup, so the requirement
    # is corrected — and the section touches one shared file it genuinely needs.
    _write(project, "src/checkout/pay.ts",
           "export const pay = () => confirmFirst();\n")
    _write(project, "src/lib/money.ts",
           "export const fmt = (n: number) => `${n}`;\nexport const total = () => 0;\n")
    _write(project, SPEC,
           "# Checkout\n\n"
           "| FR-01.09 | Checkout | Must | The customer reviews the order, then "
           "confirms payment. |\n\n"
           "### FR-01.09\n"
           "- (E) Given a basket, when the customer checks out, then they review "
           "the order and confirm before paying.\n"
           "- (E) Given the confirm step, when the customer confirms, then the "
           "order total is shown before the charge.\n")
    _git(project, "add", "-A")
    _git(project, "commit", "-qm", "section 01-payment")

    assert record_main([
        "--project-root", str(project), "--run-id", BUILD_RUN,
        "--phase", "build", "--scope", "01-payment",
        "--impact", "modify", "--fr", "FR-01.09",
        "--contradiction", "operator chose the mockup; FR-01.09 corrected to match",
        "--base-ref", "HEAD~1", "--head-ref", "HEAD",
        "--extra", "src/lib/money.ts=payment step needs a shared total formatter",
    ]) == 0
    capsys.readouterr()

    # --- Everything the section changed is accounted for.
    assert check_main([
        "--project-root", str(project), "--section-file", SECTION_FILE,
        "--run-id", BUILD_RUN, "--scope", "01-payment",
        "--base-ref", "HEAD~1", "--head-ref", "HEAD",
    ]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["unattributed"] == []
    assert payload["attributed_extras"] == ["src/lib/money.ts"]

    # --- Both declarations survive as a readable record of what each phase did.
    records, problems = read_declarations(declaration_dir(project))
    assert problems == []
    assert {(r["phase"], r["run_id"]) for r in records} == {
        ("design", DESIGN_RUN), ("build", BUILD_RUN)}
    assert any("mockup" in (r.get("contradiction") or "") for r in records)


def test_a_behaviour_round_that_skips_the_write_back_is_refused(project, capsys):
    """The failure this whole mechanism exists to make impossible.

    The round snapshots its baseline, changes only the mockup, then claims the
    requirement changed. Before the baseline existed this PASSED, because the
    untracked spec.md the project phase wrote was listed as "changed".
    """
    _snapshot(project, DESIGN_RUN, "design", "round-2")
    capsys.readouterr()
    _write(project, ".shipwright/designs/screens/03-checkout.html",
           "<html>review, then confirm</html>")

    rc = record_main([
        "--project-root", str(project), "--run-id", DESIGN_RUN,
        "--phase", "design", "--scope", "round-2",
        "--impact", "modify", "--fr", "FR-01.09", "--worktree",
    ])

    assert rc == 1
    assert json.loads(capsys.readouterr().out)["error"] == \
        "requirement_impact_no_spec_touched"
    # The baseline directory exists (the round snapshotted one), but no
    # DECLARATION was written — the rejection left nothing behind.
    records, problems = read_declarations(declaration_dir(project))
    assert records == [] and problems == []


def test_a_silent_shared_touch_is_caught_by_the_section_check(project, capsys):
    _write(project, "src/checkout/pay.ts", "export const pay = () => {};\n// edit\n")
    _write(project, "src/lib/money.ts", "export const fmt = () => 'changed';\n")
    _git(project, "add", "-A")
    _git(project, "commit", "-qm", "section 01-payment with an unrecorded shared edit")

    record_main([
        "--project-root", str(project), "--run-id", BUILD_RUN,
        "--phase", "build", "--scope", "01-payment",
        "--impact", "none", "--reason", "section built as specified",
        "--base-ref", "HEAD~1", "--head-ref", "HEAD",
    ])
    capsys.readouterr()

    rc = check_main([
        "--project-root", str(project), "--section-file", SECTION_FILE,
        "--run-id", BUILD_RUN, "--scope", "01-payment",
        "--base-ref", "HEAD~1", "--head-ref", "HEAD",
    ])

    assert rc == 1
    assert json.loads(capsys.readouterr().out)["unattributed"] == ["src/lib/money.ts"]
