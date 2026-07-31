"""The delivery ladder's calls to the outside world
(iterate-2026-07-31-f11-delivery-truth).

Stage 1 review rejected the first version of this diff partly because this module had
**no tests at all** — every other test injected host fakes, so not one of these
functions was ever executed, while the ledger claimed 0 testable-but-untested. Two of
the untested things were load-bearing:

* ``read_capability`` reading ``repos/{repo}/branches/{base}`` → ``.protected`` IS the
  external reviewer's HIGH fix. Asserting it only in a docstring is asserting nothing.
* ``gh_json`` answering ``None`` on failure is the rule the entire merge licence rests
  on: an unreadable fact must stay unreadable, because a fact read as ``False`` would
  license a self-merge on a repository that can arm perfectly well.

Every function here already carried an injection seam (``reader=``, ``run=``) put there
for exactly this purpose. Seams nobody drives are decoration.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "shared" / "scripts"))

from lib import pr_delivery_host as host  # noqa: E402


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


def _recorder(*results):
    """A `run`/`gh` stand-in that records argv and returns each result in turn."""
    calls: list[list[str]] = []
    queue = list(results)

    def run(argv, **kwargs):
        calls.append(list(argv))
        return queue.pop(0) if len(queue) > 1 else queue[0]

    run.calls = calls  # type: ignore[attr-defined]
    return run


# --- gh_json: an unreadable fact is never a false one -------------------------

def test_gh_json_parses_a_successful_call(monkeypatch):
    # Patched by MODULE OBJECT, never by the "lib.pr_delivery_host" string (ADR-045):
    # the same module can be imported under two names and the string form patches the
    # copy nobody is calling.
    monkeypatch.setattr(host, "gh", lambda args, cwd=None: _Proc(0, '{"a": 1}'))
    assert host.gh_json(["api", "x"]) == {"a": 1}


def test_gh_json_is_none_on_a_failed_call(monkeypatch):
    monkeypatch.setattr(host, "gh", lambda args, cwd=None: _Proc(1, "", "boom"))
    assert host.gh_json(["api", "x"]) is None


def test_gh_json_is_none_on_unparseable_output(monkeypatch):
    """A zero exit with garbage on stdout is still an unreadable fact."""
    monkeypatch.setattr(host, "gh", lambda args, cwd=None: _Proc(0, "not json"))
    assert host.gh_json(["api", "x"]) is None


# --- read_capability: the two facts the ladder branches on --------------------

def test_read_capability_reads_the_repo_switch_and_the_BRANCH_protection():
    """The HIGH fix, pinned. `protected` on the BRANCH object — not the rulesets
    endpoint, which reports rulesets only and answers [] for a classic-protection
    repo while arming works perfectly."""
    reader = _recorder({"allow_auto_merge": True}, {"protected": False})
    caps = host.read_capability("o/r", "main", reader=reader)

    assert caps == {"allow_auto_merge": True, "base_protected": False}
    endpoints = [next(a for a in call if a.startswith("repos/")) for call in reader.calls]
    assert endpoints == ["repos/o/r", "repos/o/r/branches/main"]
    assert not any("rules/branches" in e for e in endpoints), (
        "the rulesets endpoint must NOT be the discriminator — it cannot see classic "
        "branch protection"
    )


def test_an_unreadable_capability_is_none_not_false():
    """The distinction the merge licence rests on. False means 'the host cannot arm,
    go ahead and merge yourself'; None means 'we do not know', which must deny it."""
    reader = _recorder(None, None)
    caps = host.read_capability("o/r", "main", reader=reader)
    # The emphasis first, so it is the assertion that can actually fire: False would say
    # "the host cannot arm, go ahead and merge yourself".
    assert caps["base_protected"] is not False
    assert caps["allow_auto_merge"] is not False
    assert caps == {"allow_auto_merge": None, "base_protected": None}


def test_a_half_readable_capability_keeps_the_readable_half():
    reader = _recorder({"allow_auto_merge": False}, None)
    caps = host.read_capability("o/r", "main", reader=reader)
    assert caps["allow_auto_merge"] is False
    assert caps["base_protected"] is None


def test_read_capability_quotes_a_slashed_branch_name_into_the_path():
    """A base like `release/1.0` must reach the endpoint intact."""
    reader = _recorder({"allow_auto_merge": True}, {"protected": True})
    host.read_capability("o/r", "release/1.0", reader=reader)
    assert "repos/o/r/branches/release/1.0" in reader.calls[1]
