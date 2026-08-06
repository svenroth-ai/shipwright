"""How ``--stamp-adopted`` decides which commit the evidence names — or that none does.

Subject: ``shared/scripts/tools/compliance_adopt_stamp.resolve_adopted_base``
(iterate-2026-08-05-adopt-derived-evidence-rollout, AC-2).

Split from ``test_stamp_adopted_evidence.py``, which covers the delivery. This
file covers the one thing that makes this delivery different from ``--stage`` and
``--pr``: they describe *now* and may resolve ``HEAD`` themselves, while this one
describes *the commit onboarding read* — a fact only the caller holds.

Every test here is a way of NOT knowing the answer, and they all end the same
way: ``no_base``, nothing written. That uniformity is the point. An earlier draft
treated an *absent* base differently from a *malformed* one, which reintroduced
the timing failure the recorded value exists to remove.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
# Unconditional, and in this order: `shared/tests` carries its own `tools/`
# package and must never sit ahead of `shared/scripts` (ADR-045).
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from _compliance_refresh_fixtures import BASE, DASHBOARD, head_sha, seed_repo  # noqa: E402
from tools import compliance_adopt_stamp as adopt_stamp  # noqa: E402
from tools import refresh_compliance_docs as docs  # noqa: E402


@pytest.fixture
def adopted_repo(tmp_path: Path) -> Path:
    return seed_repo(tmp_path / "repo")


def _stamp(root: Path, capsys, *extra: str) -> tuple[int, dict]:
    code = docs.main(["--stamp-adopted", "--project-root", str(root), *extra])
    return code, json.loads(capsys.readouterr().out)


def _banner_of(root: Path) -> str:
    return (root / DASHBOARD).read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("label", "argv"),
    [
        ("absent", ()),
        ("literal HEAD", ("--base", "HEAD")),
        ("malformed", ("--base", "not-a-sha")),
        ("well-formed but absent from this repo", ("--base", BASE)),
    ],
)
def test_no_base_is_claimed_when_it_cannot_be_established(
    adopted_repo, capsys, label, argv,
):
    """Absent is not treated differently from malformed — both mean unavailable.

    An earlier draft resolved ``HEAD`` when ``--base`` was merely absent, which
    reintroduced exactly the timing failure the recorded value was adopted to
    remove: at Step H ``HEAD`` equals the recorded commit only if nothing has
    committed since, which resume, retry and operator intervention all break.
    """
    before = _banner_of(adopted_repo)
    code, report = _stamp(adopted_repo, capsys, *argv)

    assert report["status"] == "no_base", f"{label}: {report}"
    assert code == 0, f"{label}: an unstampable repo is legitimate, not an error"
    assert report.get("base") is None, f"{label}: named a commit anyway"
    assert _banner_of(adopted_repo) == before, (
        f"{label}: the banner was rewritten despite there being nothing to say"
    )


def test_an_abbreviated_base_is_refused_rather_than_resolved(adopted_repo, capsys):
    """A short id is ``no_base``, because git would resolve it as a REF first.

    For a 7-39 hex string git tries ``dwim_ref`` BEFORE short-oid lookup, so in a
    repository carrying a branch or tag literally named ``deadbeef``, ``--base
    deadbeef`` would stamp that branch's tip: a real, plausible, WRONG commit —
    the one outcome this path exists to prevent (Stage-2 code review). Only a
    full 40-hex id is taken as an object regardless of refs.

    Nothing legitimate is lost: ``event_seeder`` records ``commit_at_adoption`` at
    full length. And the degradation is in the safe direction — unstamped and
    honest beats stamped and wrong.
    """
    full = head_sha(adopted_repo)
    before = _banner_of(adopted_repo)

    code, report = _stamp(adopted_repo, capsys, "--base", full[:8])

    assert code == 0 and report["status"] == "no_base", report
    assert _banner_of(adopted_repo) == before


def test_a_padded_base_is_still_accepted(adopted_repo, capsys):
    """``safe_commit`` validates the TRIMMED value, so the trimmed one must be used.

    Interpolating the raw argument sent git a padded string that failed to
    resolve, silently degrading a perfectly establishable commit to ``no_base``
    (Stage-2 code review). Safe direction, but wrong and silent.
    """
    full = head_sha(adopted_repo)
    code, report = _stamp(adopted_repo, capsys, "--base", f"  {full}\n")

    assert code == 0 and report["status"] == "ok", report
    assert report["base"] == full


def test_head_is_never_resolved_by_this_mode(adopted_repo, capsys, monkeypatch):
    """The other modes may fall back to HEAD. This one may not, ever.

    Two properties, because either alone is weak. The call list must contain no
    HEAD-ish revision **as a substring of any argument** — asserting tuple
    membership would miss the natural way to write a fall-through here,
    ``rev-parse --verify "HEAD^{commit}"``, whose element is not equal to
    ``"HEAD"`` (Stage-2 code review). And the list must be empty outright, which
    states the stronger "never reaches git at all" property rather than leaving
    the first assertion to pass vacuously on an empty list.
    """
    calls: list[tuple[str, ...]] = []

    def _spy(real):
        def _wrapped(root, *args, **kwargs):
            calls.append(args)
            return real(root, *args, **kwargs)
        return _wrapped

    # BOTH module objects. `compliance_adopt_stamp` holds the resolver, but the
    # CLI module has its own `rev-parse HEAD` further down `main()` — and the
    # guarantee being pinned is that the mode returns BEFORE reaching it. A name
    # patched on the wrong module object stays unbound where it is actually
    # called (ADR-045), so each is patched where it lives.
    monkeypatch.setattr(adopt_stamp, "git", _spy(adopt_stamp.git))
    monkeypatch.setattr(docs, "git", _spy(docs.git))

    code, report = _stamp(adopted_repo, capsys)

    assert report["status"] == "no_base" and code == 0
    assert not any("HEAD" in arg for call in calls for arg in call), (
        f"resolved HEAD to fill in a base the caller did not supply: {calls}"
    )
    assert calls == [], (
        f"reached git at all for a base the caller did not supply: {calls}"
    )
