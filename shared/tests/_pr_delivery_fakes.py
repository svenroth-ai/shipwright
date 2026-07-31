"""Fakes for the F11 delivery ladder (iterate-2026-07-31-f11-delivery-truth).

Shared by the unit suites (``shared/tests/test_deliver_pr*.py``) and the composition
test (``integration-tests/``), which drive the SAME ladder through different amounts of
real machinery: the unit suites inject a fake watcher, the composition test runs the
real watcher and readiness with only the host faked.

:class:`_Host` mirrors the production ``lib.pr_delivery_host.Host`` bundle, so a test
cannot leave one member real by accident — the footgun that bundle exists to remove.
``argv`` is recorded rather than ignored, because ``--repo`` being present on every gh
call is itself a tested guarantee (Stage 2, security).

Underscore-prefixed so pytest does not collect it as a test module.
"""

from __future__ import annotations

HEAD = "iterate/f11-delivery-truth"
BASE = "main"
REPO = "o/r"
SHA = "a" * 40

#: Distinguishes "not supplied" from an explicit None (an unreadable preflight).
_UNSET = object()

PROTECTED_REFUSAL = (
    "GraphQL: Pull request Protected branch rules not configured for this branch "
    "(enablePullRequestAutoMerge)"
)


class _Proc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class _Host:
    """A recording fake of everything outside the process, shaped like the real bundle."""

    repo_args = ("--repo", REPO)

    def __init__(self, *, arm=_Proc(0), merge=_Proc(0), capability=None,
                 pr_views=None, verify_ok=True, refresh=None, sha=SHA,
                 preflight=_UNSET):
        self._arm, self._merge = arm, merge
        self._capability = capability or {"allow_auto_merge": True, "base_protected": True}
        self._pr_views = list(pr_views or [])
        #: The ladder reads the PR ONCE up front to check it is this run's, before
        #: the arm (which is itself a mutating command). Served separately so a
        #: test can make the preflight fail without disturbing the later reads.
        self._preflight = _open_pr() if preflight is _UNSET else preflight
        self._preflight_served = False
        self._verify_ok, self._refresh, self._sha = verify_ok, refresh, sha
        self.calls: list[str] = []
        #: Full argv of every gh call, so flag sets can be pinned behaviourally.
        self.argv: list[list[str]] = []
        self.arm_args: list[str] = []

    # --- the gh seam ---------------------------------------------------------

    def gh(self, args, *, cwd=None):
        self.argv.append(list(args))
        if args[:2] == ["api", "-X"]:
            self.calls.append("delete ref")
            return _Proc(0)
        if args[:2] == ["pr", "merge"]:
            if "--auto" in args:
                self.calls.append("arm")
                self.arm_args = list(args)
                return self._arm
            self.calls.append("merge " + " ".join(args[3:]))
            return self._merge
        raise AssertionError(f"unexpected gh call: {args}")

    def gh_json(self, args, *, cwd=None):
        self.argv.append(list(args))
        self.calls.append("pr view")
        if not self._preflight_served:
            self._preflight_served = True
            return self._preflight
        return self._pr_views.pop(0) if self._pr_views else None

    # `Host.call`/`call_json` append repo_args; mirror that so tests see the same argv.
    def call(self, args, *, cwd=None):
        return self.gh([*args, *self.repo_args], cwd=cwd)

    def call_json(self, args, *, cwd=None):
        return self.gh_json([*args, *self.repo_args], cwd=cwd)

    # --- the other four seams -----------------------------------------------

    def capability(self, repo, base, *, cwd=None, reader=None):
        self.calls.append("capability")
        return self._capability

    def verify(self, project_root, run_id, commit, *, timeout=None):
        self.calls.append(f"verify {commit[:6]}")
        return self._verify_ok

    def refresh(self, project_root, run_id, branch, *, timeout=None):
        self.calls.append("refresh")
        return self._refresh or {"ok": True, "pushed": False}

    def head_sha(self, project_root):
        return self._sha


def _watcher(*verdicts):
    """A watch() that returns each verdict in turn and records its kwargs."""
    seen: list[dict] = []
    queue = list(verdicts)

    def watch(pr, **kwargs):
        seen.append(kwargs)
        return queue.pop(0) if len(queue) > 1 else queue[0]

    watch.seen = seen  # type: ignore[attr-defined]
    return watch


def _ready(*, head=SHA, checks=2, status="ready", state="green"):
    return {"status": status, "head_oid": head, "checks_observed": checks,
            "seen_names": [f"check{i}" for i in range(checks)],
            "readiness": {"state": state, "checks_observed": checks, "reason": "ok"}}


def _behind(*, head=SHA, checks=2):
    """The host says the branch is behind or conflicted — only a refresh clears it."""
    return _ready(head=head, checks=checks, status="refresh_needed",
                  state="refresh_needed")


def _open_pr(*, head=HEAD, base=BASE, oid=SHA, state="OPEN", repo=REPO):
    return {"state": state, "headRefName": head, "baseRefName": base,
            "headRefOid": oid, "url": f"https://github.com/{repo}/pull/7"}
