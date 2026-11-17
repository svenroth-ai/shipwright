"""Golden traces: what a scenario leaves behind, normalized so two runs of the same behaviour compare equal.

Standard library only (ADR-044). Three parts:

1. **The trace** (:func:`collect`): per commit the changed paths and the normalized changed
   blobs, commit subjects in order, refs (tags to their target, branch heads, the refs of the
   bare ``origin``), the final ``git status --porcelain``, the normalized files a scenario
   names, the WHITELISTED values of each step's output, every step's exit code, and the
   ordered argv log of the stubbed external binary.
2. **The normalizer contract** (:func:`normalize_text`): timestamps, dates, SHAs, UUIDs and
   absolute paths become placeholders; ids the scenario names (run ids, session ids) become
   ``<name>``. **Judgement output is masked** (:data:`MASK`): the files matching
   ``judgement_globs``, the ``notes`` of every stubbed release, the title and body of every stubbed PR
   and the ``--notes``/``--body``/``--body-file`` values of the argv log keep their path and existence
   but not their text, because a model wrote them. A ref target is ``"<subject>@<depth>"``
   (first-parent depth), never a SHA.
3. **The driver interface** (programme P7): a scenario calls :class:`Driver` per step. The replay
   driver (today's prose) is frozen with the traces; each extraction unit adds a CLI driver
   for the steps it moves, and :class:`CompositeDriver` falls back to the replay for the rest.
   A scenario is green when the traces of two drivers are equal.

**The freeze** (programme P9): :func:`freeze_problems` compares the files named in a lock
(path -> sha256 of the LF-normalized bytes) with the tree, and accepts a difference only when
an ``approved_deltas`` entry (``scenario``, ``field`` = ``"sha256"``, ``before``, ``after``,
``approver``, ``date``) names exactly that change.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

SCHEMA_VERSION = 1
MASK = "<masked:judgement>"
# `git status` lines left out of a trace: the audit files an advisory finding (an untracked triage.jsonl) on some systems
# and not on others. A collect option, so a scenario of another plugin can mask its own.
ADVISORY_STATUS = ("?? .shipwright/triage.jsonl",)
OUTPUT_WHITELIST = ("status", "reason", "section_action", "changelog_updated", "version", "pathspec")

_SHA = re.compile(r"\b[0-9a-f]{40}\b")
_UUID = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", re.IGNORECASE)
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
_COMPACT = re.compile(r"\b\d{8}-\d{6,12}\b")  # run ids like project-20261117-125101955883
_AFTER_LABEL = re.compile(r"(<(?:repo|origin|root)>)([\\/][^\s\"'<>]*)")  # the rest of a path after its label
_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


def normalize_text(text: str, *, paths: Mapping[str, Path | str] | None = None,
                   literals: Mapping[str, str] | None = None) -> str:
    """Placeholders for what differs between two runs of the same behaviour."""
    text = text.replace("\r\n", "\n")
    for label, path in sorted((paths or {}).items(), key=lambda kv: -len(str(kv[1]))):  # longest first: a repo inside the root keeps its own label
        posix = Path(path).as_posix()
        msys = "/" + posix[0].lower() + posix[2:] if len(posix) > 2 and posix[1] == ":" else posix  # Git Bash: /c/Users/..
        forms = {posix, str(path), str(path).replace("\\", "\\\\"), Path(path).as_uri(), msys}
        for form in sorted(forms, key=len, reverse=True):
            text = text.replace(form, f"<{label}>")
    text = _AFTER_LABEL.sub(lambda m: m.group(1) + re.sub(r"\\+", "/", m.group(2)), text)  # one separator on every OS
    for literal, name in sorted((literals or {}).items(), key=lambda kv: -len(kv[0])):
        text = text.replace(literal, f"<{name}>")
    text = _COMPACT.sub("<stamp>", _STAMP.sub("<ts>", text))
    text = _DATE.sub("<date>", text)
    return _UUID.sub("<uuid>", _SHA.sub("<sha>", text))


def _git_env() -> dict[str, str]:
    """The recorder reads git under a hermetic environment: no inherited GIT_DIR, no user or system config."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT="0")
    return env


def _git(repo: Path, *args: str, check: bool = True) -> str:
    done = subprocess.run(["git", "-c", "core.quotePath=false", *args], cwd=str(repo), env=_git_env(),
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120)
    if check and done.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed in {repo}: {done.stderr.strip()}")
    return done.stdout


def _name_status(repo: Path, sha: str) -> list[tuple[str, str]]:
    parents = _git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]
    base = [parents[0]] if parents else ["--root"]
    rows = _git(repo, "diff-tree", "--no-commit-id", "--name-status", "-r", "--no-renames", *base, sha).splitlines()
    return sorted((r.split("\t")[0], r.split("\t", 1)[1]) for r in rows if "\t" in r)


def describe(repo: Path, rev: str) -> str:
    """A commit as ``"<subject>@<first-parent depth>#<digest>"``: stable across runs, unlike a SHA.

    The digest is of the commit's changed paths and statuses, so a commit amended after it was tagged
    (same subject, same depth) is a different commit here."""
    subject = _git(repo, "log", "-1", "--format=%s", rev).strip()
    depth = _git(repo, "rev-list", "--first-parent", "--count", rev).strip()
    sha = _git(repo, "rev-parse", f"{rev}^{{commit}}").strip()
    listing = "|".join(f"{status}:{path}" for status, path in _name_status(repo, sha))
    return f"{subject}@{depth}#{hashlib.sha256(listing.encode('utf-8')).hexdigest()[:8]}"


def _all_commits(repo: Path) -> list[str]:
    """Every commit reachable from any ref (a commit on a merged and deleted branch included), as a sorted list."""
    return sorted(describe(repo, sha) for sha in _git(repo, "rev-list", "--all").split())


def _blob(repo: Path, rev: str, path: str, norm) -> str | None:
    done = subprocess.run(["git", "-c", "core.quotePath=false", "show", f"{rev}:{path}"], cwd=str(repo),
                          env=_git_env(), capture_output=True, timeout=60)
    return None if done.returncode != 0 else norm(done.stdout.decode("utf-8", errors="replace"))


def _commits(repo: Path, norm, masked) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for sha in _git(repo, "rev-list", "--first-parent", "--reverse", "HEAD").split():
        parents = _git(repo, "rev-list", "--parents", "-n", "1", sha).split()[1:]
        changes = _name_status(repo, sha)
        out.append({"subject": _git(repo, "log", "-1", "--format=%s", sha).strip(), "parents": len(parents),
                    "changes": [{"status": s, "path": p} for s, p in changes],
                    "blobs": {p: (MASK if masked(p) else _blob(repo, sha, p, norm)) for s, p in changes if s != "D"}})
    return out


def _refs(repo: Path) -> dict[str, Any]:
    tags: dict[str, Any] = {}
    heads: dict[str, str] = {}
    fmt = "%(refname)\t%(objecttype)\t%(contents:subject)"
    for line in _git(repo, "for-each-ref", f"--format={fmt}", "refs/tags", "refs/heads").splitlines():
        ref, kind, subject = line.split("\t", 2)
        if ref.startswith("refs/tags/"):
            tags[ref[10:]] = {"target": describe(repo, f"{ref}^{{commit}}"), "type": kind,
                              "message": subject if kind == "tag" else None}
        else:
            heads[ref[11:]] = describe(repo, ref)
    return {"tags": tags, "branches": heads}


def _expand(repo: Path, patterns: Sequence[str]) -> list[str]:
    found = {p.relative_to(repo).as_posix() for pat in patterns for p in repo.glob(pat) if p.is_file()}
    return sorted(f for f in found if not f.startswith(".git/"))


def _is_judgement(path: str, patterns: Sequence[str]) -> bool:
    """Matched on the path alone, so a judgement file committed and later deleted is still masked."""
    return any(fnmatch.fnmatchcase(path, pat) for pat in patterns)


def _norm_value(norm, value: Any) -> Any:
    if isinstance(value, str):
        return norm(value)
    if isinstance(value, Mapping):
        return {k: _norm_value(norm, v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_norm_value(norm, v) for v in value]
    return value


_MASKED_FLAGS = ("--notes", "-n", "--body", "-b", "--body-file")  # a model wrote the value (notes, PR body)


def _mask_inline_notes(argv: Sequence[str]) -> list[str]:
    """Release notes and PR body flags carry model prose: keep the flag, mask the text (``--flag value`` and ``--flag=value``)."""
    out: list[str] = []
    for i, arg in enumerate(argv):
        flag = arg.partition("=")[0]
        if flag.startswith("--") and "=" in arg and flag in _MASKED_FLAGS:
            out.append(flag + "=" + MASK)
        elif i and argv[i - 1] in _MASKED_FLAGS:
            out.append(MASK)
        else:
            out.append(arg)
    return out


def _known_shas(*repos: Path) -> list[str]:
    return sorted({sha for r in repos for sha in _git(r, "rev-list", "--all").split()})


def _fields(output: Mapping[str, Any], whitelist: Sequence[str]) -> dict[str, Any]:
    kept = {k: output[k] for k in whitelist if k in output}
    if isinstance(kept.get("reason"), str):
        kept["reason"] = kept["reason"].split(":", 1)[0]  # the prefix is behaviour, the tail is detail
    return kept


def collect(scratch: Any, steps: Sequence["StepResult"] = (), *, files: Sequence[str] = (),
            judgement_globs: Sequence[str] = (), literals: Mapping[str, str] | None = None,
            whitelist: Sequence[str] = OUTPUT_WHITELIST, masked_status: Sequence[str] = ADVISORY_STATUS) -> dict[str, Any]:
    """The trace of one scenario. ``scratch`` needs ``repo``, ``origin``, ``root`` and ``gh_argv_log()``/``gh_state()``."""
    repo, origin = Path(scratch.repo), Path(scratch.origin)
    paths = {"repo": repo, "origin": origin, "root": Path(scratch.root)}
    known = _known_shas(repo, origin)
    short = re.compile(r"\b[0-9a-f]{7,39}\b")

    def norm(text: str) -> str:
        text = normalize_text(text, paths=paths, literals=literals)  # paths first: a hex run inside one is not a sha
        return short.sub(lambda m: "<sha>" if any(k.startswith(m.group(0)) for k in known) else m.group(0), text)

    def masked(path: str) -> bool:
        return _is_judgement(path, judgement_globs)

    tree = {p: (MASK if masked(p) else norm((repo / p).read_text(encoding="utf-8", errors="replace")))
            for p in _expand(repo, files)}
    state = scratch.gh_state()
    releases = {t: {"title": r.get("title"), "notes": MASK} for t, r in sorted(state.get("releases", {}).items())}
    prs = [{k: (MASK if k in ("title", "body") else norm(str(p.get(k)))) for k in ("number", "head", "base", "title", "body", "state")}
           for p in state.get("prs", [])]
    return {
        "schema": SCHEMA_VERSION,
        "steps": [{"step": s.step, "exit_code": s.exit_code, "fields": _norm_value(norm, _fields(s.output, whitelist))} for s in steps],
        "commits": _commits(repo, norm, masked),
        "refs": _refs(repo),
        "origin": _refs(origin),
        "all_commits": {"repo": _all_commits(repo), "origin": _all_commits(origin)},
        # the audit files an advisory finding (untracked triage.jsonl) on some systems and not on others: not part of the trace
        "status": [s for s in norm(_git(repo, "status", "--porcelain")).splitlines() if s not in masked_status],
        "files": tree,
        "stub": {"argv": [{"argv": [norm(a) for a in _mask_inline_notes(e["argv"])], "exit": e["exit"]} for e in scratch.gh_argv_log()],
                 "prs": prs, "releases": releases},
    }


def dumps(trace: Mapping[str, Any]) -> str:
    """The one on-disk form: sorted keys, two-space indent, LF, trailing newline."""
    return json.dumps(trace, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


# ---- the driver interface (programme P7) ------------------------------------------------------

@dataclass
class StepResult:
    step: str
    exit_code: int
    output: dict[str, Any] = field(default_factory=dict)


class Driver(Protocol):
    """Runs ONE step of a flow against a scratch project. ``steps`` is what it implements."""
    name: str
    steps: frozenset[str]

    def run_step(self, step: str, scratch: Any, **params: Any) -> StepResult: ...


class CompositeDriver:
    """A CLI driver for the steps it moved, the replay driver for the rest."""

    def __init__(self, primary: Driver, fallback: Driver):
        self.primary, self.fallback = primary, fallback
        self.name = f"{primary.name}+{fallback.name}"
        self.steps = frozenset(primary.steps | fallback.steps)

    def run_step(self, step: str, scratch: Any, **params: Any) -> StepResult:
        driver = self.primary if step in self.primary.steps else self.fallback
        return driver.run_step(step, scratch, **params)


def run_scenario(driver: Driver, scratch: Any, plan: Sequence[tuple[str, Mapping[str, Any]]]) -> list[StepResult]:
    """Run ``plan`` (step name, params) in order. An unknown step is an error, never a skip."""
    unknown = [step for step, _ in plan if step not in driver.steps]
    if unknown:
        raise KeyError(f"driver {driver.name!r} has no step {unknown[0]!r}")
    return [driver.run_step(step, scratch, **dict(params)) for step, params in plan]


# ---- the freeze (programme P9) -----------------------------------------------------------------

def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def freeze_problems(root: Path, lock: Mapping[str, str], deltas: Sequence[Mapping[str, Any]]) -> list[str]:
    """Paths in ``lock`` (relative to ``root``) whose bytes differ and are not covered by an approved delta."""
    problems: list[str] = []
    for rel, locked in sorted(lock.items()):
        path = root / rel
        if not path.is_file():
            problems.append(f"{rel}: frozen file is missing")
            continue
        now = file_sha256(path)
        if now == locked:
            continue
        covered = any(d.get("scenario") == rel and d.get("field") == "sha256" and d.get("before") == locked
                      and d.get("after") == now and d.get("approver") and d.get("date") for d in deltas)
        if not covered:
            problems.append(f"{rel}: changed since the freeze and no approved delta names this change")
    return problems
