"""A stand-in for ``gh`` that talks to a LOCAL bare repository, for the golden-trace harness.

Wired in through the argv-prefix seam (``SHIPWRIGHT_TEST_GH_ARGV_PREFIX``, ``shared/scripts/release_seams.py``):
``["<python>", "<this file>"]`` replaces the leading ``gh`` of the release scripts. Standard library only (ADR-044):
it runs in a scratch project's environment, not the repo's. No environment guessing, no network: the state lives in
``SHIPWRIGHT_GH_STUB_STATE`` (``state.json``, ``argv.jsonl``; unset: exit 3, it never pretends to succeed), the remote is
``git remote get-url --push origin`` of the current directory (the scratch's bare repository; its fetch URL is fake).

**Contract** (what the stub refuses or does, from the brief, section 5 P2a):

* ``pr create``: refuses (exit 1) unless the head branch (``--head``, else the current branch) is on the bare remote, the
  base (``--base``, else the remote's default branch) is there too and no open PR has the same head and base. Records the
  PR (title, body, base, head) and prints its URL.
* ``pr merge``: really merges the head into the remote's base branch: ``--merge`` a merge commit, ``--squash`` one commit
  with the merged tree on the base, ``--rebase`` each head commit replayed onto the base (always new commits, as GitHub
  does; unit U3, FINDINGS D114). It keeps the head and the merge commit for ``pr view``. ``--delete-branch`` deletes the
  head on the remote; when the LOCAL checkout is on the PR's head it also does what the real ``gh`` does: check out the
  base, fast-forward it from the push URL and delete the local head. Refuses without exactly one merge flag (as ``gh``
  does when it cannot prompt), when no open PR matches, and on a merge conflict.
* ``pr view <url|number|branch> --json <fields>``: ``state`` (``OPEN``/``MERGED``/``CLOSED``), ``mergeCommit``
  (``{"oid": ...}`` or null), ``headRefOid`` (the head at the merge, else the remote's), ``baseRefName``,
  ``headRefName``, ``number``; another field is exit 1, no ``--json`` exit 2.
* ``release create``: refuses unless the tag is on the remote, or the release exists already; otherwise persists it.
  ``release view`` then reports it (``--json url`` prints ``{"url": ...}``), or exits 1 with ``release not found``.
* ``--version`` and ``auth status`` succeed. Anything else: exit 2. A BARE gh (the shim sets SHIPWRIGHT_GH_STUB_UNSEAMED=1) is
  logged out: ``auth status`` exits 1, anything but ``--version`` exits 4, and it is logged to ``unseamed.jsonl``, not ``argv.jsonl``.
* ``--repo`` / ``-R`` is accepted and ignored (only the URL of the PR and release comes from it): the repository is always
  the one in the current directory, so the cwd MUST be the scratch repository.
* Short flags map per command (``_SHORT``); any other short flag, a bundled one (``-md``), a valued flag without a value
  and a long flag the contract does not list are refused (exit 2). A crash inside the stub exits 4 and is logged like any
  call; a call killed by a timeout is the one case that writes no log line.

**Fidelity limits, on purpose:** the local checkout is touched only as described under ``pr merge``; no auth, no merge
queue, one repository. ``release create`` refuses an unpushed tag even without ``--verify-tag`` (the release script always
passes it), and a missing notes file is exit 4 where the real ``gh`` exits 1. A scenario that depends on those has no oracle.

**The argv log is part of the trace:** every call appends ``{"argv": [...], "exit": n}`` to ``argv.jsonl`` in the state
directory, refusals included, in call order.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

STATE_ENV = "SHIPWRIGHT_GH_STUB_STATE"
VERSION_TEXT = "gh version 2.60.0 (2026-01-01)\nhttps://github.com/cli/cli/releases/tag/v2.60.0 (shipwright test stub)\n"
_GIT = ["git", "-c", "user.name=gh-stub", "-c", "user.email=gh-stub@example.invalid", "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]

_SHORT: dict[tuple[str, str], dict[str, str]] = {
    ("pr", "create"): {"-t": "--title", "-b": "--body", "-B": "--base", "-H": "--head", "-F": "--body-file", "-R": "--repo"},
    ("pr", "merge"): {"-m": "--merge", "-d": "--delete-branch", "-s": "--squash", "-r": "--rebase", "-R": "--repo"},
    ("pr", "view"): {"-R": "--repo"},
    ("release", "create"): {"-t": "--title", "-n": "--notes", "-F": "--notes-file", "-d": "--draft", "-p": "--prerelease", "-R": "--repo"},
    ("release", "view"): {"-R": "--repo"},
}

_GIT_ENV_DROP = ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL")


def _env() -> dict[str, str]:
    """The stub's merge commit is authored by the stub, not by the scenario's identity."""
    return {k: v for k, v in os.environ.items() if k not in _GIT_ENV_DROP}


class Refusal(Exception):
    def __init__(self, message: str, code: int = 1):
        super().__init__(message)
        self.code = code


def _git(*args: str, cwd: Path | str, check: bool = True) -> str:
    done = subprocess.run([*_GIT, *args], cwd=str(cwd), env=_env(), capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=120)
    if check and done.returncode != 0:
        raise Refusal(f"git {' '.join(args)} failed: {(done.stderr or done.stdout).strip()}")
    return done.stdout.strip()


def _flags(argv: list[str], valued: tuple[str, ...], bare_ok: tuple[str, ...] = (),
           short: dict[str, str] | None = None) -> tuple[list[str], dict[str, str], set[str]]:
    """Split ``argv`` into positionals, ``--name value`` pairs and bare flags. ``short`` is the command's own map."""
    positional, values, bare = [], {}, set()  # type: tuple[list[str], dict[str, str], set[str]]
    it = iter(argv)
    for arg in it:
        if arg.startswith("-") and not arg.startswith("--") and len(arg) > 1:
            if arg not in (short or {}):
                raise Refusal(f"gh-stub: unsupported flag {arg}", 2)  # a difference to recognise, not to guess at
            arg = short[arg]
        name, eq, inline = arg.partition("=")
        if name in valued:
            value = inline if eq else next(it, "")
            if not value or (not eq and value.startswith("--")):
                raise Refusal(f"gh-stub: flag {name} needs a value", 2)
            values[name] = value
        elif arg.startswith("--"):
            if arg not in bare_ok:
                raise Refusal(f"gh-stub: unsupported flag {name}", 2)  # a long flag the contract does not list
            bare.add(arg)
        else:
            positional.append(arg)
    return positional, values, bare


class Stub:
    def __init__(self, state_dir: Path, cwd: Path):
        self.state_dir = state_dir
        self.cwd = cwd
        self.state_file = state_dir / "state.json"
        try:
            self.state = (json.loads(self.state_file.read_text(encoding="utf-8")) if self.state_file.is_file()
                          else {"prs": [], "releases": {}})
        except ValueError as exc:
            raise Refusal(f"gh-stub: the state file is corrupt: {exc}", 3) from exc

    def save(self) -> None:
        self.state_file.write_text(json.dumps(self.state, indent=2, sort_keys=True), encoding="utf-8")

    def remote(self) -> str:
        url = _git("remote", "get-url", "--push", "origin", cwd=self.cwd, check=False)
        if not url:
            raise Refusal("gh-stub: no origin push URL here; run it inside the scratch project")
        return url

    def current_branch(self) -> str:
        return _git("rev-parse", "--abbrev-ref", "HEAD", cwd=self.cwd)

    def remote_has(self, ref: str) -> bool:
        return bool(_git("ls-remote", "--exit-code", self.remote(), ref, cwd=self.cwd, check=False))

    def default_branch(self) -> str:
        head = _git("ls-remote", "--symref", self.remote(), "HEAD", cwd=self.cwd, check=False)
        first = head.splitlines()[0] if head else ""
        return first.split()[1].removeprefix("refs/heads/") if first.startswith("ref:") else "main"

    def repo_slug(self, given: str | None) -> str:
        if given:
            return given
        url = _git("remote", "get-url", "origin", cwd=self.cwd, check=False)
        return url.removesuffix(".git").split("github.com/")[-1].split("github.com:")[-1]

    # ---- commands -------------------------------------------------------------------------
    def pr_create(self, argv: list[str]) -> str:
        _, v, _ = _flags(argv, ("--title", "--body", "--base", "--head", "--repo", "--body-file"),
                         short=_SHORT[("pr", "create")])
        head = v.get("--head") or self.current_branch()
        if not self.remote_has(f"refs/heads/{head}"):
            raise Refusal(f"gh-stub: aborted: head branch '{head}' is not on the remote; push it first")
        base = v.get("--base") or self.default_branch()
        if not self.remote_has(f"refs/heads/{base}"):
            raise Refusal(f"gh-stub: base branch '{base}' is not on the remote")
        if any(p["state"] == "open" and (p["head"], p["base"]) == (head, base) for p in self.state["prs"]):
            raise Refusal(f"gh-stub: a pull request for branch '{head}' into '{base}' already exists")
        number = len(self.state["prs"]) + 1
        body = v.get("--body", "")
        if "--body-file" in v:
            body = Path(v["--body-file"]).read_text(encoding="utf-8")
        self.state["prs"].append({"number": number, "head": head, "base": base,
                                  "title": v.get("--title", ""), "body": body, "state": "open"})
        return f"https://github.com/{self.repo_slug(v.get('--repo'))}/pull/{number}\n"

    def pr_merge(self, argv: list[str]) -> str:
        pos, v, bare = _flags(argv, ("--repo",), ("--merge", "--squash", "--rebase", "--delete-branch"),
                              short=_SHORT[("pr", "merge")])
        method = [m for m in ("--merge", "--squash", "--rebase") if m in bare]
        if len(method) != 1:
            raise Refusal("gh-stub: --merge, --rebase, or --squash required when not running interactively")
        key = pos[0] if pos else self.current_branch()
        pr = next((p for p in self.state["prs"] if p["state"] == "open"
                   and (str(p["number"]) == key or p["head"] == key)), None)
        if pr is None:
            raise Refusal(f"gh-stub: no open pull request found for '{key}'")
        head = f"origin/{pr['head']}"
        steps = {"--merge": [["merge", "--no-ff", "-m", f"Merge pull request #{pr['number']} from {pr['head']}", head]],
                 "--squash": [["merge", "--squash", head], ["commit", "-m", f"{pr['title']} (#{pr['number']})"]],
                 "--rebase": [["rebase", "--force-rebase", pr["base"], "stub-rebase"], ["checkout", "--quiet", pr["base"]],
                              ["merge", "--ff-only", "stub-rebase"]]}[method[0]]
        with tempfile.TemporaryDirectory(dir=self.state_dir) as work:
            _git("clone", "--quiet", self.remote(), work, cwd=self.state_dir)
            _git("checkout", "--quiet", pr["base"], cwd=work)
            _git("branch", "stub-rebase", head, cwd=work)
            for step in steps:
                merged = subprocess.run([*_GIT, *step], cwd=work, env=_env(), capture_output=True, text=True,
                                        encoding="utf-8", errors="replace", timeout=120)
                if merged.returncode != 0:
                    raise Refusal(f"gh-stub: pull request #{pr['number']} is not mergeable: {merged.stdout.strip()[-200:]}")
            _git("push", "--quiet", "origin", pr["base"], cwd=work)
            pr.update(state="merged", head_oid=_git("rev-parse", head, cwd=work), merge_commit=_git("rev-parse", "HEAD", cwd=work))
            self.save()  # the remote is merged now, whatever the branch delete does
            if "--delete-branch" in bare:
                _git("push", "--quiet", "origin", "--delete", pr["head"], cwd=work)
        if "--delete-branch" in bare and self.current_branch() == pr["head"]:
            try:
                self._leave_merged_head(pr)
            except Refusal as exc:  # the remote is merged already: the real gh warns about its local cleanup, it does not fail
                sys.stderr.write(f"gh-stub: warning: the merge succeeded but the local checkout was not moved: {exc}\n")
        return f"Merged pull request #{pr['number']}\n"

    def _leave_merged_head(self, pr: dict) -> None:
        """What the real ``gh pr merge --delete-branch`` does to a checkout that is on the merged head."""
        base = pr["base"]
        if os.environ.get("GIT_ALLOW_PROTOCOL") != "file":  # only ever inside a scratch: never a real checkout
            raise Refusal("gh-stub: refusing to move a checkout outside a scratch (GIT_ALLOW_PROTOCOL is not 'file')", 3)
        _git("checkout", "--quiet", base, cwd=self.cwd)
        _git("fetch", "--quiet", self.remote(), base, cwd=self.cwd)
        _git("merge", "--quiet", "--ff-only", "FETCH_HEAD", cwd=self.cwd)
        _git("branch", "-D", pr["head"], cwd=self.cwd)

    def pr_view(self, argv: list[str]) -> str:
        pos, v, _ = _flags(argv, ("--repo", "--json"), short=_SHORT[("pr", "view")])
        key = (pos[0] if pos else self.current_branch()).rstrip("/").rsplit("/", 1)[-1]
        pr = next((p for p in reversed(self.state["prs"]) if key in (str(p["number"]), p["head"])), None)
        if pr is None:
            raise Refusal(f"gh-stub: no pull requests found for '{key}'")
        merged = pr["state"] == "merged"
        head = pr.get("head_oid") if merged else _git("ls-remote", self.remote(), f"refs/heads/{pr['head']}", cwd=self.cwd, check=False)[:40]
        facts = {"state": pr["state"].upper(), "mergeCommit": {"oid": pr["merge_commit"]} if merged and pr.get("merge_commit") else None,
                 "headRefOid": head or None, "baseRefName": pr["base"], "headRefName": pr["head"], "number": pr["number"]}
        wanted = [f for f in v.get("--json", "").split(",") if f]
        if not wanted or any(f not in facts for f in wanted):
            raise Refusal(f"gh-stub: pr view needs --json with fields from {', '.join(facts)}", 2 if not wanted else 1)
        return json.dumps({f: facts[f] for f in wanted}) + "\n"

    def release_create(self, argv: list[str]) -> str:
        pos, v, _ = _flags(argv, ("--notes-file", "--title", "--repo", "--notes", "--target"),
                             ("--verify-tag", "--draft", "--prerelease"), short=_SHORT[("release", "create")])
        tag = pos[0] if pos else ""
        if not tag:
            raise Refusal("gh-stub: a tag name is required", 2)
        if tag in self.state["releases"]:
            raise Refusal(f"gh-stub: a release with the tag '{tag}' already exists")
        if not self.remote_has(f"refs/tags/{tag}"):
            raise Refusal(f"gh-stub: tag '{tag}' was not found on the remote; push the tag first")
        notes = Path(v["--notes-file"]).read_text(encoding="utf-8") if "--notes-file" in v else v.get("--notes", "")
        url = f"https://github.com/{self.repo_slug(v.get('--repo'))}/releases/tag/{tag}"
        self.state["releases"][tag] = {"title": v.get("--title", tag), "notes": notes, "url": url}
        return url + "\n"

    def release_view(self, argv: list[str]) -> str:
        pos, v, _ = _flags(argv, ("--repo", "--json"), short=_SHORT[("release", "view")])
        release = self.state["releases"].get(pos[0] if pos else "")
        if release is None:
            raise Refusal("release not found")
        return json.dumps({"url": release["url"]}) + "\n" if "--json" in v else release["url"] + "\n"


UNSEAMED_ENV = "SHIPWRIGHT_GH_STUB_UNSEAMED"  # set by the shim: a bare ``gh`` that no seam routed here


def dispatch(stub: Stub, argv: list[str], *, unseamed: bool = False) -> str:
    if argv[:1] == ["--version"]:
        return VERSION_TEXT
    if argv[:2] == ["auth", "status"]:
        if unseamed:  # a bare gh is "not logged in": on Windows no bare gh reaches the stub at all, so Linux must agree
            raise Refusal("You are not logged into any GitHub hosts.", 1)
        return "github.com\n  Logged in to github.com (shipwright test stub)\n"
    if unseamed:  # a bare gh is logged out: it may probe (--version, auth status above) but never act
        raise Refusal("To get started with GitHub CLI, please run:  gh auth login", 4)
    table = {("pr", "create"): stub.pr_create, ("pr", "merge"): stub.pr_merge, ("pr", "view"): stub.pr_view,
             ("release", "create"): stub.release_create, ("release", "view"): stub.release_view}
    handler = table.get(tuple(argv[:2]))
    if handler is None:
        raise Refusal(f"gh-stub: unsupported command: gh {' '.join(argv)}", 2)
    return handler(argv[2:])


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    raw = os.environ.get(STATE_ENV)
    if not raw:
        sys.stderr.write(f"gh-stub: {STATE_ENV} is not set; refusing to pretend\n")
        return 3
    state_dir = Path(raw)
    state_dir.mkdir(parents=True, exist_ok=True)
    code, out = 0, ""
    unseamed = os.environ.get(UNSEAMED_ENV) == "1"
    try:
        stub = Stub(state_dir, Path.cwd())
        out = dispatch(stub, argv, unseamed=unseamed)
        stub.save()
    except Refusal as exc:
        sys.stderr.write(f"{exc}\n")
        code = exc.code
    except Exception as exc:  # noqa: BLE001 - a crash is still a call: it must reach the log
        sys.stderr.write(f"gh-stub: internal error: {type(exc).__name__}: {exc}\n")
        code = 4
    # a bare gh is logged apart: the trace holds the calls a seam routed, the same on every OS
    with (state_dir / ("unseamed.jsonl" if unseamed else "argv.jsonl")).open("a", encoding="utf-8") as log:
        log.write(json.dumps({"argv": argv, "exit": code}) + "\n")
    sys.stdout.write(out)
    return code


if __name__ == "__main__":
    sys.exit(main())
