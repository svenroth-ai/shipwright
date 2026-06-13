"""D2 review-cascade remediation (part 2) — FIX C / D / E.

Split from ``test_sweep_outbox_review_cascade.py`` (FIX A/B) so each module stays
under the 300-LOC guideline. REAL git / worktrees / the real ``integrate_main``
path — nothing mocked.

* FIX C (exactly-once is integrate-provided): two branches sweep the SAME line;
  merging through the real ``integrate_main.integrate`` yields EXACTLY one copy.
* FIX D (staged-diff gate): an EOL-only materialization diff → ``no_change``,
  not a spurious ``error``.
* FIX E (routing invariant guard): every BACKGROUND-hook triage producer routes
  to the outbox on idle main (hardcoded ``to_outbox=True`` or a
  ``should_route_to_outbox(...)`` computation) — a regression that wires a
  tracked-defaulting producer would re-arm the integrate-block D2 removed.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

_SHARED_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
_REPO_ROOT = Path(__file__).resolve().parents[2]
# Order matters: shared/scripts precedes shared/tests so ``from tools import
# integrate_main`` resolves to shared/scripts/tools, not the test package.
sys.path.insert(0, str(Path(__file__).resolve().parent))  # shared/tests (helper)
sys.path.insert(0, str(_SHARED_SCRIPTS))  # shared/scripts — wins for ``tools``

import _sweep_helpers as h  # noqa: E402
from lib.churn_merge import validate_triage_text  # noqa: E402
from lib.sweep_outbox import sweep_outbox_to_branch  # noqa: E402
from tools import integrate_main  # noqa: E402

TRIAGE = h.TRIAGE


@pytest.fixture
def repo(git_origin_repo):
    work, origin = git_origin_repo
    h.set_identity(work)
    return work, origin


# --------------------------------------------------------------------------- #
# FIX C — exactly-once across concurrent identical sweeps is integrate-provided
# --------------------------------------------------------------------------- #


def test_two_branches_same_line_exactly_once_via_integrate(repo) -> None:
    """Two SEPARATE iterate branches each sweep the SAME identical outbox line L
    (byte-identical on both branches' tracked logs). Merge branch X into origin,
    integrate origin into branch Y via the REAL ``integrate_main.integrate``, then
    merge Y. L must appear EXACTLY once in the final origin log and validate.

    This proves the doubt-2 claim: exactly-once across concurrent identical
    sweeps is guaranteed by integrate_main's unconditional dedup
    (``resolve_churn_conflicts`` → ``dedup_triage_lines``), NOT by merge=union
    alone — a bare ``git merge`` of two sides both carrying L would duplicate
    until the next integrate."""
    work, _ = repo
    h.seed_tracked(work, h.item("trg-aaaa"))

    # Branch X sweeps L.
    wtx = h.make_worktree(work, "fixc-x")
    h.write_outbox(work, h.item("trg-L"))
    rx = sweep_outbox_to_branch(work, wtx, default_branch="main")
    assert rx.status == "committed" and rx.swept == 1, rx.to_dict()

    # Branch Y sweeps the SAME L (the outbox still holds it — not origin-delivered).
    assert h.item("trg-L") in h.outbox_lines(work)
    wty = h.make_worktree(work, "fixc-y")
    ry = sweep_outbox_to_branch(work, wty, default_branch="main")
    assert ry.status == "committed" and ry.swept == 1, ry.to_dict()

    # Merge X into origin/main (X is the first PR to land).
    h.git(work, "fetch", "origin")
    h.git(work, "merge", "--no-ff", "--no-edit", "iterate/fixc-x")
    h.git(work, "push", "origin", "main")

    # Integrate origin/main into branch Y via the REAL integrate (NOT bare merge):
    # both Y's HEAD and origin/main now carry L, so the integrate's dedup is the
    # only thing that collapses them to one.
    res = integrate_main.integrate(wty, "iterate-fixc", do_fetch=True)
    assert res["status"] == "ok", res

    # Merge Y into origin too (Y is the second PR).
    h.git(wty, "push", "origin", "HEAD:main")

    # Final origin log: L appears EXACTLY once, and validates.
    origin_text = h.git(work, "show", f"origin/main:{TRIAGE}").stdout
    occurrences = sum(1 for ln in origin_text.splitlines() if ln.strip() == h.item("trg-L"))
    assert occurrences == 1, f"expected exactly-once, got {occurrences}\n{origin_text}"
    assert validate_triage_text(origin_text) == []


# --------------------------------------------------------------------------- #
# FIX D — EOL-only materialization diff → no_change, NOT a spurious error
# --------------------------------------------------------------------------- #


def _seed_eol_lf(work) -> None:
    """Seed origin/main with an ``eol=lf``-attributed triage log so the index is
    ALWAYS LF regardless of the working-copy line endings (the substrate for an
    EOL-only staged-diff)."""
    (work / ".shipwright").mkdir(parents=True, exist_ok=True)
    (work / TRIAGE).write_text(
        "\n".join([h.HEADER, h.item("trg-aaaa")]) + "\n", encoding="utf-8", newline="\n"
    )
    (work / ".gitattributes").write_text(
        f"{TRIAGE} merge=union eol=lf\n", encoding="utf-8", newline="\n"
    )
    (work / ".gitignore").write_text(f"{h.OUTBOX}\n", encoding="utf-8", newline="\n")
    h.git(work, "add", "--", TRIAGE, ".gitattributes", ".gitignore")
    h.git(work, "commit", "-m", "seed eol=lf")
    h.git(work, "push", "origin", "main")
    h.git(work, "remote", "set-head", "origin", "main")


def test_eol_only_diff_is_no_change_not_error(repo) -> None:
    """FIX D: when the materialized log differs from the worktree-raw bytes by EOL
    alone (so ``deduped_text != worktree_raw`` is TRUE) but git's index — governed
    by ``eol=lf`` — sees NO staged change, the staged-diff gate must report
    ``no_change`` instead of attempting a "nothing to commit" commit that would
    surface a spurious ``error``.

    Construction (the real autocrlf shape): the branch HEAD already carries line
    B as LF; the WORKING file is rewritten to CRLF and missing B; the outbox
    supplies B. The sweep re-materializes B into the CRLF working file
    (``deduped_text != worktree_raw`` → enters the commit block), but ``git add``
    normalizes CRLF→LF, matching the committed HEAD → empty staged diff."""
    work, _ = repo
    _seed_eol_lf(work)
    wt = h.make_worktree(work, "fixd-eol")
    # Branch HEAD/index carries HEADER,A,B as LF (B is committed on the branch).
    (wt / TRIAGE).write_text(
        "\n".join([h.HEADER, h.item("trg-aaaa"), h.item("trg-bbbb")]) + "\n",
        encoding="utf-8", newline="\n",
    )
    h.git(wt, "add", "--", TRIAGE)
    h.git(wt, "commit", "-m", "branch adds B")
    head_before = h.git(wt, "rev-parse", "HEAD").stdout.strip()
    # Working file: CRLF and MISSING B → git diff sees a (delete-B) change, so
    # _read_text yields CRLF with [HEADER, A], eol=CRLF.
    (wt / TRIAGE).write_bytes(
        ("\r\n".join([h.HEADER, h.item("trg-aaaa")]) + "\r\n").encode("utf-8")
    )
    # Outbox supplies B → deduped re-adds it; the rematerialized CRLF file
    # normalizes to the LF HEAD on ``git add`` → no staged delta.
    h.write_outbox(work, h.item("trg-bbbb"))

    result = sweep_outbox_to_branch(work, wt, default_branch="main")

    # The gate fires: no_change, NOT a spurious error from "nothing to commit".
    assert result.status == "no_change", result.to_dict()
    assert result.reason == "no_branch_change", result.to_dict()
    # HEAD did not move (no spurious commit attempt landed).
    assert h.git(wt, "rev-parse", "HEAD").stdout.strip() == head_before


# --------------------------------------------------------------------------- #
# FIX E — routing invariant guard (static/source-level assertion)
# --------------------------------------------------------------------------- #

# Each BACKGROUND-hook-invoked triage producer (Stop / SessionStart fan-out) MUST
# route to the gitignored outbox on idle main: either hardcode ``to_outbox=True``
# or compute ``should_route_to_outbox(...)`` on its append. If a future hook wires
# a producer that defaults to the TRACKED log on idle main, it re-arms the
# integrate-block that D2 removed (background drift orphans on local main). The
# in-phase / tracked producers (security / performance / artifact_sync) are
# CORRECTLY tracked and deliberately excluded here — do NOT add them.
_BACKGROUND_PRODUCERS = {
    # NOTE: plugin_sync_reminder_on_stop was removed from this set
    # (iterate-2026-06-13-triage-not-current-work) — it no longer files ANY
    # triage item (the block-once reminder is the whole surface), so it is no
    # longer a background triage producer and routes nothing to the outbox.
    "check_drift": "shared/scripts/hooks/check_drift.py",
    "phase_quality_triage_bundle": "shared/scripts/lib/phase_quality/_triage_bundle.py",
    "compliance_triage_bundle": "plugins/shipwright-compliance/scripts/audit/triage_bundle.py",
    "triage_add": "shared/scripts/tools/triage_add.py",
}

# Either a literal hardcoded ``to_outbox=True`` OR a routing computation that
# derives the flag from ``should_route_to_outbox(...)`` / ``route(...)``.
_HARDCODED_RE = re.compile(r"to_outbox\s*=\s*True")
_ROUTE_RE = re.compile(r"should_route_to_outbox\s*\(|=\s*bool\(\s*route\(|=\s*route\(")


@pytest.mark.parametrize("name,rel", sorted(_BACKGROUND_PRODUCERS.items()))
def test_background_producer_routes_to_outbox(name: str, rel: str) -> None:
    """Source-level invariant: every background triage producer either hardcodes
    ``to_outbox=True`` or computes ``should_route_to_outbox(...)`` for its append.

    Static assertion (grep the call site) — purpose is to surface a REGRESSION
    where a hook wires a tracked-defaulting producer, which would re-arm the
    integrate-block D2 removed. The tracked in-phase producers (security /
    performance / artifact_sync) are intentionally NOT in this set."""
    src = (_REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "append_triage_item" in src, f"{name}: not a triage producer anymore?"
    routes = bool(_HARDCODED_RE.search(src)) or bool(_ROUTE_RE.search(src))
    assert routes, (
        f"{name} ({rel}) no longer routes to the outbox on idle main — it must "
        f"hardcode to_outbox=True or compute should_route_to_outbox(...). A "
        f"tracked-defaulting background producer re-arms the integrate-block D2 "
        f"removed."
    )
