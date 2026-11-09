"""Small helpers shared by the ``test_ac_*`` modules (the autouse environment fixture is ``ac_hermetic.py``)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from lib import ac_catalog as cat
from lib import ac_decision as ad

SPEC = ".shipwright/planning/01-adopted/spec.md"
BASE_SPEC = "### FR-01.03 - Saving drafts\n\n- (E) [AC05] Given a draft, when saved, then it is kept.\n\n### FR-01.04 - Sharing drafts\n\n- (E) [AC01] Given a link, when opened, then the draft shows.\n"
PROMISE = "A saved draft survives a restart"


def ans(question: dict, choice: str, text: str = "") -> dict:
    """An (unsigned) file answer to ``question`` exactly as the answer tool stores it: bound to its sha, carrying the options it was shown."""
    return {"item": question["item"], "question_sha256": question["question_sha256"], "options": question["options"], "choice": choice, "text": text}


def git(root: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@t", *args], capture_output=True, text=True, check=True).stdout.strip()


def repo(tmp_path: Path, spec: str = BASE_SPEC) -> Path:
    root = tmp_path / "repo"
    (root / SPEC).parent.mkdir(parents=True)
    (root / SPEC).write_text(spec, encoding="utf-8")
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    git(root, "add", "-A")
    git(root, "commit", "-qm", "base")
    return root


def commit(root: Path, files: dict[str, str], amend: bool = False) -> str:
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")
    git(root, "add", "-A")
    git(root, *(["commit", "-q", "--amend", "--no-edit"] if amend else ["commit", "-qm", "work"]))
    return git(root, "rev-parse", "HEAD")


def cat_of(spec: str) -> dict:
    acs, frs = cat.parse_catalog(spec)
    return {"acs": acs, "frs": set(frs), "titles": frs, "unparsed": False}


def decided(items: list[dict], catalog: dict | None = None, **kw) -> dict:
    return ad.decide(items, catalog or cat_of(BASE_SPEC), **kw)
