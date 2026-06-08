"""Scaffold + self-heal the append-log ``merge=union`` driver into managed repos.

The monorepo root ``.gitattributes`` declares ``merge=union`` for the two
append-only JSONL logs (``shipwright_events.jsonl``, ``.shipwright/triage.jsonl``)
so concurrent iterate appends auto-line-union instead of producing conflict
markers. That protection was **monorepo-local** — so every adopted repo (WebUI,
leadwright, any end-user project) fell back to git's default conflict behavior.
This module is the single source of merge logic that lands it everywhere:

* :func:`merge_into` — pure, idempotent merge of the union fragment into an
  existing ``.gitattributes`` (never clobbers user entries). Consumed by the
  adopt scaffolder (``gitattributes_scaffolder.py``, loaded by file path to dodge
  the adopt-``lib`` / shared-``lib`` collision) and by the self-heal below.
* :func:`self_heal_gitattributes` — a guarded git commit-path (modeled on
  ``reconcile_main_triage``) that backfills the union lines into an
  already-adopted repo on its next iterate, as one ``chore`` commit on the
  current branch. No-op in the monorepo (lines already exist) — dogfood-safe.

Module top-level is import-pure (stdlib only): the adopt scaffolder loads this
file by absolute path, so it must not ``from lib.* import`` at module scope. The
git helper is imported lazily inside :func:`self_heal_gitattributes`, which only
runs where ``shared/scripts`` is on ``sys.path``.
"""

from __future__ import annotations

import contextlib
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

# Layout (identical in the dev repo and the ~/.claude marketplace cache):
#   <root>/shared/scripts/lib/gitattributes_union.py   ← this file
#   <root>/shared/templates/gitattributes-union.template
# parents[0]=lib, [1]=scripts, [2]=shared, [3]=<root>.
_REPO_ROOT = Path(__file__).resolve().parents[3]

#: Where the rendered driver lives in a managed repo (repo root).
GITATTRIBUTES_PATH = ".gitattributes"
#: SSoT for the fragment content. The drift test pins its shape to UNION_PATHS.
TEMPLATE_PATH = "shared/templates/gitattributes-union.template"

#: The tracked append-log artifacts that need the line-union merge driver.
#: HARD-CODED here (not imported from ``lib.churn_merge``) so this module stays
#: import-pure for the file-path loader; the drift test asserts this equals
#: ``{churn_merge.EVENTS_LOG, churn_merge.TRIAGE_LOG}`` so the two cannot diverge.
UNION_PATHS: tuple[str, ...] = ("shipwright_events.jsonl", ".shipwright/triage.jsonl")

#: First line of the template — the sentinel that marks our managed block, so a
#: partial backfill appends only the missing lines without a duplicate header.
MANAGED_MARKER = (
    "# Shipwright append-log union merge driver (managed block — do not hand-edit)."
)

#: Truthy spellings of ``$CI`` that disable the auto-commit unless ``allow_ci``.
_CI_TRUTHY = frozenset({"1", "true", "yes", "on"})


def load_fragment() -> str:
    """Return the canonical fragment text (LF-normalised, trailing newline).

    Raises ``FileNotFoundError`` loudly if the template is missing — that is a
    development-time bug (a managed repo never reaches this code path), mirroring
    ``gitleaks_config_scaffolder``'s loud-failure contract.
    """
    template = _REPO_ROOT / TEMPLATE_PATH
    if not template.exists():
        raise FileNotFoundError(
            f"gitattributes union template missing at {template}. "
            f"shared/scripts/lib/gitattributes_union.py declares "
            f"TEMPLATE_PATH={TEMPLATE_PATH!r} but no such file exists in the tree."
        )
    text = template.read_text(encoding="utf-8").replace("\r\n", "\n")
    if not text.endswith("\n"):
        text += "\n"
    return text


def _union_line(path: str) -> str:
    return f"{path} merge=union"


def _declares_union(text: str, path: str) -> bool:
    """True when ``text`` already declares ``merge=union`` for ``path``.

    Tolerant of extra attributes / surrounding whitespace; ignores comments. A
    user line like ``shipwright_events.jsonl merge=union -text`` counts as present.
    """
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        toks = line.split()
        if toks and toks[0] == path and "merge=union" in toks[1:]:
            return True
    return False


def missing_union_paths(text: str | None) -> list[str]:
    """The subset of :data:`UNION_PATHS` not yet declared in ``text``."""
    body = text or ""
    return [p for p in UNION_PATHS if not _declares_union(body, p)]


def merge_into(existing_text: str | None) -> tuple[str, bool]:
    """Idempotently merge the union fragment into ``existing_text``.

    Returns ``(merged_text, changed)``. ``changed`` is False when every union
    line is already present (round-trip stable: ``merge_into(merge_into(x)[0])``
    reports ``changed=False``). An empty / whitespace-only / ``None`` input is
    treated as "no file" → the full template is returned. An existing file with
    user entries is preserved verbatim; only the missing union lines (under the
    managed marker, added once) are appended, with the file's existing EOL style.
    """
    if not existing_text or not existing_text.strip():
        return load_fragment(), True

    missing = missing_union_paths(existing_text)
    if not missing:
        return existing_text, False

    eol = "\r\n" if "\r\n" in existing_text else "\n"
    block_lines: list[str] = []
    if MANAGED_MARKER not in existing_text:
        block_lines.append(MANAGED_MARKER)
    block_lines.extend(_union_line(p) for p in missing)

    core = existing_text.rstrip("\r\n")
    merged = core + eol + eol + eol.join(block_lines) + eol
    return merged, True


# --- self-heal commit-path (git side) ---------------------------------------


@dataclass
class HealResult:
    """Outcome of :func:`self_heal_gitattributes`.

    ``status`` ∈ {``committed``, ``no_change``, ``skipped``, ``error``}.
    ``reason`` carries the guard name for ``skipped`` / ``error``; ``added`` lists
    the union paths newly declared in a ``committed`` run.
    """

    status: str
    reason: str = ""
    added: list[str] = field(default_factory=list)
    commit_subject: str = ""

    def to_dict(self) -> dict:
        return {
            "status": self.status,
            "reason": self.reason,
            "added": self.added,
            "commit_subject": self.commit_subject,
        }


def _ci_active() -> bool:
    return os.environ.get("CI", "").strip().lower() in _CI_TRUTHY


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` verbatim (UTF-8, no newline translation) via tempfile +
    os.replace so a concurrent reader never sees a torn file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _restore_gitattributes(ga_path: Path, original: str | None, unstage) -> None:
    """Best-effort rollback after a failed/timed-out commit, so the contract
    ('guarded no-op rather than ever corrupting git state') holds on failure:
    unstage the path, then restore (or delete) the working-tree file. Never
    raises — there is already a real error to report."""
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        unstage("reset", "-q", "--", GITATTRIBUTES_PATH)
    with contextlib.suppress(OSError):
        if original is None:
            ga_path.unlink(missing_ok=True)
        else:
            _atomic_write(ga_path, original)


def self_heal_gitattributes(
    project_root: Path | str,
    *,
    allow_ci: bool = False,
) -> HealResult:
    """Backfill the union ``.gitattributes`` lines into ``project_root`` as one
    ``chore`` commit on the current branch.

    Acts ONLY on a Shipwright-managed repo (tracks at least one append-log
    artifact) that is missing union lines. A batch of guards make it a structured
    no-op rather than ever corrupting git state. Never raises for an expected
    condition — returns a structured :class:`HealResult`.
    """
    # Lazy import of the lib.* git helper only: the adopt scaffolder loads this
    # module by file path (no shared/scripts on sys.path), so a module-level
    # ``from lib...`` would crash that import. Stdlib imports stay at the top.
    _scripts_root = Path(__file__).resolve().parents[1]  # shared/scripts
    if str(_scripts_root) not in sys.path:
        sys.path.insert(0, str(_scripts_root))
    from lib.worktree_isolation import GitError, run_git  # noqa: E402

    root = Path(project_root)

    def _git(*args: str):
        # Swallow a hung-git timeout into a non-zero result so no guard probe can
        # propagate TimeoutExpired (honors "never raises"); the commit itself uses
        # run_git directly with a generous timeout + explicit catch.
        try:
            return run_git(list(args), cwd=repo_root, check=False)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess(args, 124, "", "git timed out")

    # --- resolve repo root (also the not-a-git-repo probe) -----------------
    try:
        top = run_git(
            ["rev-parse", "--show-toplevel"], cwd=root, check=True
        ).stdout.strip()
    except GitError:
        return HealResult("skipped", "not_a_git_repo")
    except (OSError, subprocess.TimeoutExpired) as exc:
        return HealResult("error", f"git_probe_failed: {exc}")
    repo_root = Path(top)

    # --- cheap guards -------------------------------------------------------
    if _ci_active() and not allow_ci:
        return HealResult("skipped", "ci_without_optin")
    # op-in-progress before detached-HEAD (a rebase detaches HEAD, so the
    # in-progress reason is the more actionable one).
    for ref in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD"):
        if _git("rev-parse", "--verify", "--quiet", ref).returncode == 0:
            return HealResult("skipped", "op_in_progress")
    for rel in ("rebase-merge", "rebase-apply", "BISECT_LOG"):
        probe = _git("rev-parse", "--git-path", rel)
        if probe.returncode != 0:
            continue
        p = Path(probe.stdout.strip())
        if (p if p.is_absolute() else repo_root / p).exists():
            return HealResult("skipped", "op_in_progress")
    if _git("symbolic-ref", "--quiet", "HEAD").returncode != 0:
        return HealResult("skipped", "detached_head")

    # --- only act on Shipwright-managed append-log repos -------------------
    tracked = _git("ls-files", "--", *UNION_PATHS).stdout.strip()
    if not tracked:
        return HealResult("skipped", "no_tracked_append_log")

    # --- compute the merge --------------------------------------------------
    ga_path = repo_root / GITATTRIBUTES_PATH
    # errors="replace": a non-UTF-8 file must not raise UnicodeDecodeError (uncaught by setup.main) — fail-soft, congruent with gitignore_selfheal.
    existing = ga_path.read_text("utf-8", errors="replace") if ga_path.exists() else None
    merged, changed = merge_into(existing)
    if not changed:
        return HealResult("no_change")

    # Skip rather than risk a partial ``git commit -- <path>`` interacting with a
    # user's staged WIP. The backfill is always an unstaged absence → non-empty index = no-op.
    if _git("diff", "--cached", "--quiet").returncode != 0:
        return HealResult("skipped", "staged_changes")

    added = missing_union_paths(existing)
    _atomic_write(ga_path, merged)
    subject = "chore: scaffold append-log union merge driver into .gitattributes"

    # Stage then commit ONLY .gitattributes (handles both the new-file and
    # modified-file cases; an untracked new file needs the explicit add). On ANY
    # failure, roll back so a rejected/timed-out commit leaves git state clean.
    # The commit fires the bloat pre-commit hook, whose cold `uv run` routinely
    # exceeds run_git's 15s default — and this runs on a brand-new worktree, the
    # most likely place for a cold env — so give it a generous timeout and treat
    # a timeout as a structured error rather than letting it crash the caller.
    try:
        add = _git("add", "--", GITATTRIBUTES_PATH)
        if add.returncode != 0:
            _restore_gitattributes(ga_path, existing, _git)
            return HealResult("error", f"add_failed: {add.stderr.strip()[:300]}")
        commit = run_git(
            ["commit", "-m", subject, "--", GITATTRIBUTES_PATH],
            cwd=repo_root, check=False, timeout=120.0,
        )
    except subprocess.TimeoutExpired:
        _restore_gitattributes(ga_path, existing, _git)
        return HealResult("error", "commit_timeout")
    if commit.returncode != 0:
        _restore_gitattributes(ga_path, existing, _git)
        return HealResult("error", f"commit_failed: {commit.stderr.strip()[:300]}")
    return HealResult("committed", added=added, commit_subject=subject)
