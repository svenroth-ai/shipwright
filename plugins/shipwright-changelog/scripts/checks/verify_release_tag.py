#!/usr/bin/env python3
"""The release's tag and CHANGELOG check, run in a process of its own (second pass B4, operator decision F7).

``orchestrator.py update-step`` used to be the only caller of ``check_git_tag_exists`` and ``check_changelog_version_matches_tag``
(through ``_validate_changelog``). The release code asks the same two verifiers itself, for the version it just cut, so a
tag or CHANGELOG mismatch is refused without any run-state write. A process of its own because the shared verifiers import
the shared ``lib`` package, and this plugin has a ``lib`` of its own.

    uv run verify_release_tag.py --shared-root <shared> --project-root . --version X.Y.Z

Prints ``{"ok": bool, "checks": {...}, "advisory": {...}}``; exit 0 when the tag exists and the CHANGELOG's top version is this release, 1 otherwise.
The latest-tag comparison is only reported (``advisory``): it would refuse a final over its own ``-rc`` tag and a backport.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shared-root", required=True)
    parser.add_argument("--project-root", default=".")
    parser.add_argument("--version", required=True)
    args = parser.parse_args(argv)
    sys.path.insert(0, str(Path(args.shared_root) / "scripts"))
    from tools.verifiers import changelog_checks as cc  # noqa: E402

    result = cc.check_release_tag(Path(args.project_root).resolve(), args.version)  # the public entry: never a `_` helper of the shared module
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
